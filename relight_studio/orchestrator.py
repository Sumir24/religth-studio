"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Asynchronous Rendering Orchestrator
Manages non-blocking render queues, worker threads, request debouncing,
stale-frame cancellation, and dual preview/final mode dispatch.
"""

from __future__ import annotations

import os
import time
import queue
import threading
from typing import Dict, Any, Optional, Callable, Tuple
import numpy as np
import cv2

from studio3a.scene import StudioScene, RenderQuality
from studio3a.renderer import RenderBackend

try:
    from metal2.renderer import MetalRenderBackend
    _HAS_METAL2 = True
except Exception:
    _HAS_METAL2 = False


class RenderRequest:
    """Encapsulates a snapshot render request with monotonic ID."""
    def __init__(
        self,
        request_id: int,
        scene: StudioScene,
        image_orig_srgb: np.ndarray,
        depth_map: np.ndarray,
        normals_map: np.ndarray,
        fg_mask: np.ndarray,
        quality: RenderQuality,
        protected_mask: Optional[np.ndarray] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.request_id = request_id
        self.scene = scene
        self.image_orig_srgb = image_orig_srgb
        self.depth_map = depth_map
        self.normals_map = normals_map
        self.fg_mask = fg_mask
        self.quality = quality
        self.protected_mask = protected_mask
        self.callback = callback
        self.timestamp = time.time()


class RenderingOrchestrator:
    """
    Asynchronous rendering manager ensuring the UI main thread never blocks.
    Features:
      • Non-blocking render request queue.
      • Dedicated worker thread for GPU/CPU execution.
      • Stale-frame cancellation: drops obsolete in-flight requests during rapid drags.
      • Dual-mode dispatch: Preview ($1024 \times 576$) vs Final (native resolution).
      • Thread-safe latest-result container.
    """
    def __init__(self, use_metal: bool = True):
        self.use_metal = use_metal and _HAS_METAL2
        self.cpu_backend = RenderBackend()
        self.metal_backend = MetalRenderBackend() if _HAS_METAL2 else None
        self.backend = self.metal_backend if self.use_metal else self.cpu_backend

        self._request_lock = threading.Lock()
        self._request_counter: int = 0
        self._latest_dispatched_id: int = 0
        self._latest_completed_id: int = 0

        self._work_queue: queue.Queue[Optional[RenderRequest]] = queue.Queue(maxsize=4)
        self._latest_result_lock = threading.Lock()
        self._latest_result: Optional[Dict[str, Any]] = None

        self._running: bool = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="RenderWorker")
        self._worker_thread.start()

    def set_backend(self, use_metal: bool) -> str:
        """Switches compute backend dynamically."""
        with self._request_lock:
            if use_metal and _HAS_METAL2:
                self.use_metal = True
                self.backend = self.metal_backend
                return "Active Backend: Native Metal GPU (Apple Silicon)"
            else:
                self.use_metal = False
                self.backend = self.cpu_backend
                return "Active Backend: CPU Reference Renderer"

    def submit_request(
        self,
        scene: StudioScene,
        image_orig_srgb: np.ndarray,
        depth_map: np.ndarray,
        normals_map: np.ndarray,
        fg_mask: np.ndarray,
        quality: RenderQuality = RenderQuality.PREVIEW,
        protected_mask: Optional[np.ndarray] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> int:
        """
        Submits an asynchronous render request.
        Debounces obsolete pending preview requests.
        """
        with self._request_lock:
            self._request_counter += 1
            req_id = self._request_counter
            self._latest_dispatched_id = req_id

        # Copy scene to decouple from mutation during drag
        scene_copy = StudioScene.from_dict(scene.to_dict())

        # If preview quality, resize inputs to preview resolution (1024x576) for responsive interactivity
        if quality == RenderQuality.PREVIEW:
            target_w, target_h = 1024, 576
            orig_h, orig_w = image_orig_srgb.shape[:2]
            if orig_w != target_w or orig_h != target_h:
                im_render = cv2.resize(image_orig_srgb, (target_w, target_h), interpolation=cv2.INTER_AREA)
                d_render = cv2.resize(depth_map, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                n_render = cv2.resize(normals_map, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                fg_render = cv2.resize(fg_mask.astype(np.uint8), (target_w, target_h), interpolation=cv2.INTER_NEAREST) > 0
                prot_render = cv2.resize(protected_mask.astype(np.uint8), (target_w, target_h), interpolation=cv2.INTER_NEAREST) > 0 if protected_mask is not None else None
                scene_copy.camera.width = target_w
                scene_copy.camera.height = target_h
            else:
                im_render = image_orig_srgb
                d_render = depth_map
                n_render = normals_map
                fg_render = fg_mask
                prot_render = protected_mask
        else:
            im_render = image_orig_srgb
            d_render = depth_map
            n_render = normals_map
            fg_render = fg_mask
            prot_render = protected_mask

        req = RenderRequest(
            request_id=req_id,
            scene=scene_copy,
            image_orig_srgb=im_render,
            depth_map=d_render,
            normals_map=n_render,
            fg_mask=fg_render,
            quality=quality,
            protected_mask=prot_render,
            callback=callback
        )

        # Clear older pending preview requests from queue
        try:
            while not self._work_queue.empty():
                pending = self._work_queue.get_nowait()
                if pending and pending.quality == RenderQuality.FINAL:
                    # Put final requests back
                    self._work_queue.put_nowait(pending)
                    break
        except Exception:
            pass

        try:
            self._work_queue.put(req, block=False)
        except queue.Full:
            pass

        return req_id

    def render_sync(
        self,
        scene: StudioScene,
        image_orig_srgb: np.ndarray,
        depth_map: np.ndarray,
        normals_map: np.ndarray,
        fg_mask: np.ndarray,
        quality: RenderQuality = RenderQuality.PREVIEW,
        protected_mask: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """Executes a synchronous render pass on the caller's thread."""
        t0 = time.perf_counter()
        res = self.backend.render(
            scene=scene,
            image_orig_srgb=image_orig_srgb,
            depth_map=depth_map,
            normals_map=normals_map,
            fg_mask=fg_mask,
            quality=quality,
            protected_mask=protected_mask
        )
        res["orchestrator_wall_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
        with self._latest_result_lock:
            self._latest_result = res
        return res

    def get_latest_result(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent completed render output."""
        with self._latest_result_lock:
            return self._latest_result

    def _worker_loop(self):
        """Dedicated background execution loop."""
        while self._running:
            try:
                req = self._work_queue.get(timeout=0.1)
                if req is None:
                    break

                # Stale frame cancellation: skip if a newer request was dispatched
                with self._request_lock:
                    if req.request_id < self._latest_dispatched_id and req.quality == RenderQuality.PREVIEW:
                        continue

                t0 = time.perf_counter()
                out = self.backend.render(
                    scene=req.scene,
                    image_orig_srgb=req.image_orig_srgb,
                    depth_map=req.depth_map,
                    normals_map=req.normals_map,
                    fg_mask=req.fg_mask,
                    quality=req.quality,
                    protected_mask=req.protected_mask
                )
                wall_ms = (time.perf_counter() - t0) * 1000.0
                out["request_id"] = req.request_id
                out["orchestrator_wall_ms"] = round(wall_ms, 2)
                out["quality"] = req.quality.value

                with self._request_lock:
                    self._latest_completed_id = req.request_id

                with self._latest_result_lock:
                    self._latest_result = out

                if req.callback:
                    try:
                        req.callback(out)
                    except Exception as e:
                        print(f"[Orchestrator] Callback exception: {e}")

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Orchestrator Worker Error]: {e}")

    def shutdown(self):
        """Stops worker thread gracefully."""
        self._running = False
        self._work_queue.put(None)
        self._worker_thread.join(timeout=1.0)
