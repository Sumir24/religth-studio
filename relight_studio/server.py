"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Local Application HTTP & WebSocket Server
Connects the professional Studio Workspace web frontend to the authoritative
StudioAppController and async RenderingOrchestrator.
"""

from __future__ import annotations

import os
import io
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import numpy as np
from PIL import Image
import cv2

from fastapi import FastAPI, Request, Response, Body, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
import uvicorn

from studio3a.scene import RenderQuality
from relight_studio.controller import StudioAppController


def create_app(controller: Optional[StudioAppController] = None) -> FastAPI:
    """Factory function creating the Relight Studio FastAPI web application."""
    ctrl = controller or StudioAppController()

    app = FastAPI(title="Relight Studio — Virtual 3D Lighting Studio", version="1.0.0")

    web_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index_page():
        index_file = web_dir / "index.html"
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    # -----------------------------------------------------------------------
    # STATE & TELEMETRY
    # -----------------------------------------------------------------------

    @app.get("/api/state/full")
    async def get_full_state():
        latest = ctrl.orchestrator.get_latest_result() or {}
        diag = latest.get("diagnostics", {})

        gpu_ms = diag.get("gpu_time_ms", 2.41)
        wall_ms = latest.get("orchestrator_wall_ms", 5.25)
        fps = round(1000.0 / max(wall_ms, 1.0), 1)

        return {
            "selected_id": ctrl.selected_object_id,
            "hierarchy": ctrl.get_scene_hierarchy(),
            "inspector": ctrl.get_inspector_data(),
            "telemetry": {
                "gpu_time_ms": gpu_ms,
                "wall_time_ms": wall_ms,
                "fps": fps
            },
            "is_missing_assets": getattr(ctrl.project, "is_missing_assets", False) if ctrl.project else False,
            "missing_assets": getattr(ctrl.project, "missing_assets", []) if ctrl.project else [],
            "photo_image_url": "/api/images/photo",
            "orig_image_url": "/api/images/orig",
            "stage_image_url": "/api/images/stage"
        }

    # -----------------------------------------------------------------------
    # IMAGE BUFFER STREAMS & ALIGNMENT OVERLAYS
    # -----------------------------------------------------------------------

    @app.get("/api/images/photo")
    async def get_photo_image(mode: str = "relit", opacity: float = 0.6):
        m = str(mode).lower().strip()
        if m in ("wireframe", "silhouette", "guides", "mismatch"):
            u8 = ctrl.render_photograph_with_overlay(mode=m, opacity=opacity)
        elif m == "original":
            u8 = ctrl.render_photograph_with_overlay(mode="original")
        else:
            latest = ctrl.orchestrator.get_latest_result()
            if latest and "relit_srgb" in latest:
                arr = latest["relit_srgb"]
            elif ctrl.project and ctrl.project.img_orig_srgb is not None:
                arr = ctrl.project.img_orig_srgb
            else:
                arr = np.zeros((384, 512, 3), dtype=np.float32)
            u8 = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)

        _, buf = cv2.imencode(".jpg", cv2.cvtColor(u8, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
        return Response(content=buf.tobytes(), media_type="image/jpeg")

    @app.get("/api/images/orig")
    async def get_orig_image():
        if ctrl.project and ctrl.project.img_orig_srgb is not None:
            arr = ctrl.project.img_orig_srgb
        else:
            arr = np.zeros((384, 512, 3), dtype=np.float32)

        u8 = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
        _, buf = cv2.imencode(".jpg", cv2.cvtColor(u8, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
        return Response(content=buf.tobytes(), media_type="image/jpeg")

    @app.get("/api/images/stage")
    async def get_stage_image():
        canvas = ctrl.render_3d_stage_canvas(width=640, height=480, draw_gizmo=True)
        _, buf = cv2.imencode(".png", cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))
        return Response(content=buf.tobytes(), media_type="image/png")

    @app.get("/api/stage/projection_meta")
    async def get_stage_projection_meta(width: int = Query(640), height: int = Query(480)):
        meta = ctrl.get_stage_projection_meta(width=width, height=height)
        return meta

    @app.get("/api/camera/alignment_meta")
    async def get_camera_alignment_meta(width: Optional[int] = Query(None), height: Optional[int] = Query(None)):
        meta = ctrl.get_alignment_projection_meta(canvas_w=width, canvas_h=height)
        return meta

    @app.post("/api/stage/drag")
    async def stage_drag(payload: Dict[str, Any] = Body(...)):
        axis = payload.get("axis", "X")
        dx = float(payload.get("dx", 0.0))
        dy = float(payload.get("dy", 0.0))
        lid = payload.get("light_id")
        w = int(payload.get("width", 640))
        h = int(payload.get("height", 480))
        ctrl.project_drag_to_3d(axis=axis, delta_screen_x=dx, delta_screen_y=dy, light_id=lid, canvas_w=w, canvas_h=h)
        target = ctrl.current_scene.get_light(lid or ctrl.selected_object_id)
        return {
            "status": "ok",
            "position": target.position if target else [],
            "rotation_deg": target.rotation_deg if target else [],
            "width": target.width if target else 0.0,
            "height": target.height if target else 0.0
        }

    @app.post("/api/stage/focus")
    async def stage_focus():
        ctrl.focus_selected_object()
        return {
            "status": "ok",
            "yaw": ctrl.stage_orbit_yaw_deg,
            "pitch": ctrl.stage_orbit_pitch_deg,
            "dist": ctrl.stage_orbit_dist,
            "pan": ctrl.stage_pan_offset
        }

    @app.post("/api/stage/reset")
    async def stage_reset():
        ctrl.reset_camera_stage()
        return {
            "status": "ok",
            "yaw": ctrl.stage_orbit_yaw_deg,
            "pitch": ctrl.stage_orbit_pitch_deg,
            "dist": ctrl.stage_orbit_dist,
            "pan": ctrl.stage_pan_offset
        }

    @app.post("/api/interaction/begin")
    async def interaction_begin():
        ctrl.begin_interaction()
        return {"status": "ok"}

    @app.post("/api/interaction/end")
    async def interaction_end():
        ctrl.end_interaction()
        return {"status": "ok"}

    # -----------------------------------------------------------------------
    # SELECTION & SCENE ACTIONS
    # -----------------------------------------------------------------------

    @app.post("/api/select")
    async def select_object(id: str = Query(...)):
        ctrl.select_object(id)
        return {"status": "ok", "selected_id": ctrl.selected_object_id}

    @app.post("/api/light/add")
    async def add_light():
        new_id = ctrl.add_light()
        return {"status": "ok", "new_id": new_id}

    @app.post("/api/light/duplicate")
    async def duplicate_light(id: Optional[str] = Query(None)):
        new_id = ctrl.duplicate_light(id)
        return {"status": "ok", "new_id": new_id}

    @app.post("/api/light/delete")
    async def delete_light(id: Optional[str] = Query(None)):
        ctrl.delete_light(id)
        return {"status": "ok"}

    @app.post("/api/light/toggle")
    async def toggle_light(id: Optional[str] = Query(None)):
        en = ctrl.toggle_light_enabled(id)
        return {"status": "ok", "enabled": en}

    @app.post("/api/light/transform")
    async def update_light_transform(payload: Dict[str, Any] = Body(...)):
        lid = payload.get("id", ctrl.selected_object_id)
        ctrl.update_light_transform(
            light_id=lid,
            pos=payload.get("pos"),
            rot_deg=payload.get("rot_deg"),
            width=payload.get("width"),
            height=payload.get("height")
        )
        return {"status": "ok"}

    @app.post("/api/light/properties")
    async def update_light_properties(payload: Dict[str, Any] = Body(...)):
        lid = payload.get("id", ctrl.selected_object_id)
        ctrl.update_light_properties(
            light_id=lid,
            intensity=payload.get("intensity"),
            temperature_kelvin=payload.get("temperature_kelvin"),
            energy_convention=payload.get("energy_convention"),
            enabled=payload.get("enabled"),
            cast_shadows=payload.get("cast_shadows")
        )
        return {"status": "ok"}

    @app.post("/api/light/preset")
    async def apply_light_preset(payload: Dict[str, Any] = Body(...)):
        preset = payload.get("preset", "key_softbox")
        lid = payload.get("id")
        created_id = ctrl.apply_lighting_preset(preset_name=preset, light_id=lid)
        return {"status": "ok", "light_id": created_id}

    @app.post("/api/light/update")
    async def rename_light(payload: Dict[str, Any] = Body(...)):
        lid = payload.get("id", ctrl.selected_object_id)
        if "name" in payload:
            ctrl.rename_light(lid, payload["name"])
        return {"status": "ok"}

    @app.post("/api/subject/params")
    async def update_subject_params(payload: Dict[str, Any] = Body(...)):
        ctrl.update_subject_proxy_params(
            proxy_type=payload.get("proxy_type"),
            dimensions=payload.get("dimensions"),
            position=payload.get("position"),
            position_y=payload.get("position_y"),
            rotation_deg=payload.get("rotation_deg"),
            scale=payload.get("scale")
        )
        return {"status": "ok"}

    @app.post("/api/subject/snap_ground")
    async def snap_subject_ground():
        new_y = ctrl.snap_subject_to_ground()
        return {"status": "ok", "position_y": new_y}

    @app.post("/api/material/profile")
    async def set_material_profile(payload: Dict[str, Any] = Body(...)):
        prof = payload.get("profile", "Custom")
        ctrl.set_material_profile(prof)
        return {"status": "ok"}

    @app.post("/api/material/params")
    async def update_material_params(payload: Dict[str, Any] = Body(...)):
        ctrl.update_material_params(
            roughness=payload.get("roughness"),
            metallic=payload.get("metallic"),
            specular_f0=payload.get("specular_f0"),
            specular_intensity=payload.get("specular_intensity"),
            enable_specular=payload.get("enable_specular")
        )
        return {"status": "ok"}

    @app.post("/api/environment/params")
    async def update_environment_params(payload: Dict[str, Any] = Body(...)):
        ctrl.update_environment_params(
            enabled=payload.get("enabled"),
            intensity=payload.get("intensity"),
            rotation_deg=payload.get("rotation_deg"),
            diffuse_weight=payload.get("diffuse_weight"),
            specular_weight=payload.get("specular_weight")
        )
        return {"status": "ok"}

    @app.post("/api/receiver/params")
    async def update_receiver_params(payload: Dict[str, Any] = Body(...)):
        ctrl.update_receiver_params(
            receiver_type=payload.get("receiver_type", "CYCLORAMA"),
            ground_y=payload.get("ground_y"),
            cove_radius=payload.get("cove_radius"),
            wall_z=payload.get("wall_z")
        )
        return {"status": "ok"}

    @app.post("/api/camera/params")
    async def update_camera_params(payload: Dict[str, Any] = Body(...)):
        ctrl.update_camera_params(
            pos=payload.get("pos"),
            target=payload.get("target"),
            fov_deg=payload.get("fov_deg"),
            focal_length_mm=payload.get("focal_length_mm"),
            elevation=payload.get("elevation"),
            distance=payload.get("distance"),
            pitch_deg=payload.get("pitch_deg"),
            yaw_deg=payload.get("yaw_deg")
        )
        return {"status": "ok"}

    @app.post("/api/camera/preset")
    async def apply_camera_preset(payload: Dict[str, Any] = Body(...)):
        preset = payload.get("preset", "50mm")
        fl = ctrl.apply_camera_preset(preset)
        return {
            "status": "ok",
            "focal_length_mm": fl,
            "fov_deg": ctrl.current_scene.camera.fov_deg
        }

    @app.post("/api/camera/fit")
    async def fit_camera_subject():
        dist = ctrl.fit_camera_to_subject()
        return {"status": "ok", "distance": dist}

    @app.post("/api/camera/reset")
    async def reset_camera():
        ctrl.reset_camera_photo()
        return {"status": "ok"}

    @app.post("/api/stage/orbit")
    async def update_stage_orbit(
        yaw: Optional[float] = Query(None),
        pitch: Optional[float] = Query(None),
        dist: Optional[float] = Query(None),
        pan_x: Optional[float] = Query(None),
        pan_y: Optional[float] = Query(None)
    ):
        if yaw is not None: ctrl.stage_orbit_yaw_deg = float(yaw)
        if pitch is not None: ctrl.stage_orbit_pitch_deg = float(pitch)
        if dist is not None: ctrl.stage_orbit_dist = float(dist)
        if pan_x is not None: ctrl.stage_pan_offset[0] = float(pan_x)
        if pan_y is not None: ctrl.stage_pan_offset[1] = float(pan_y)
        return {"status": "ok"}

    @app.post("/api/undo")
    async def undo_action():
        ctrl.undo()
        return {"status": "ok"}

    @app.post("/api/redo")
    async def redo_action():
        ctrl.redo()
        return {"status": "ok"}

    @app.post("/api/backend")
    async def switch_backend(use_metal: bool = Query(...)):
        msg = ctrl.orchestrator.set_backend(use_metal)
        ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
        return {"status": "ok", "message": msg}

    @app.post("/api/render/final")
    async def render_final():
        res = ctrl.request_render(quality=RenderQuality.FINAL, async_mode=False)
        return {"status": "ok", "wall_ms": res.get("orchestrator_wall_ms", 0.0)}

    # -----------------------------------------------------------------------
    # PROJECT OPERATIONS
    # -----------------------------------------------------------------------

    @app.post("/api/project/new")
    async def new_project(payload: Dict[str, Any] = Body(...)):
        name = payload.get("name", "Untitled")
        path = payload.get("image_path", "demo_output/nike_sample.jpg")
        ctrl.new_project(name=name, image_path=path)
        return {"status": "ok", "project_name": ctrl.project.name}

    @app.post("/api/project/save")
    async def save_project(payload: Optional[Dict[str, Any]] = Body(None)):
        save_path = (payload or {}).get("path", "demo_output/studio_session.relight")
        saved_bundle = ctrl.save_project(save_path)
        return {"status": "ok", "path": saved_bundle}

    @app.post("/api/project/export")
    async def export_relit(payload: Optional[Dict[str, Any]] = Body(None)):
        out_path = (payload or {}).get("path", "demo_output/relit_export.png")
        latest = ctrl.orchestrator.get_latest_result()
        if latest and "relit_srgb" in latest:
            arr = (np.clip(latest["relit_srgb"], 0.0, 1.0) * 255.0).astype(np.uint8)
            cv2.imwrite(out_path, cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        return {"status": "ok", "path": out_path}

    return app
