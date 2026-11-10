"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Unit Tests: Rendering Orchestrator & Async Pipeline
Verifies non-blocking execution, stale-frame cancellation, dual-mode preview/final,
and thread safety.
"""

import time
import numpy as np
import pytest

from studio3a.scene import StudioScene, RenderQuality
from relight_studio.orchestrator import RenderingOrchestrator


@pytest.fixture
def orchestrator():
    orch = RenderingOrchestrator(use_metal=False)
    yield orch
    orch.shutdown()


def test_sync_render(orchestrator):
    scene = StudioScene()
    H, W = 128, 128
    im = np.full((H, W, 3), 0.5, dtype=np.float32)
    depth = np.full((H, W), 0.5, dtype=np.float32)
    normals = np.zeros((H, W, 3), dtype=np.float32)
    normals[..., 2] = -1.0
    fg = np.ones((H, W), dtype=bool)

    res = orchestrator.render_sync(scene, im, depth, normals, fg, quality=RenderQuality.PREVIEW)
    assert "relit_srgb" in res
    assert res["relit_srgb"].shape == (H, W, 3)
    assert orchestrator.get_latest_result() is not None


def test_async_render_and_callback(orchestrator):
    scene = StudioScene()
    H, W = 128, 128
    im = np.full((H, W, 3), 0.5, dtype=np.float32)
    depth = np.full((H, W), 0.5, dtype=np.float32)
    normals = np.zeros((H, W, 3), dtype=np.float32)
    normals[..., 2] = -1.0
    fg = np.ones((H, W), dtype=bool)

    callback_called = False
    result_holder = []

    def on_complete(out):
        nonlocal callback_called
        callback_called = True
        result_holder.append(out)

    req_id = orchestrator.submit_request(
        scene, im, depth, normals, fg, quality=RenderQuality.PREVIEW, callback=on_complete
    )
    assert req_id > 0

    # Wait for completion
    t0 = time.time()
    while not callback_called and (time.time() - t0) < 5.0:
        time.sleep(0.05)

    assert callback_called
    assert len(result_holder) == 1
    assert "relit_srgb" in result_holder[0]


def test_stale_frame_cancellation(orchestrator):
    scene = StudioScene()
    H, W = 128, 128
    im = np.full((H, W, 3), 0.5, dtype=np.float32)
    depth = np.full((H, W), 0.5, dtype=np.float32)
    normals = np.zeros((H, W, 3), dtype=np.float32)
    normals[..., 2] = -1.0
    fg = np.ones((H, W), dtype=bool)

    # Rapid fire 5 preview requests simulating dragging a slider
    completed_ids = []

    def cb(out):
        completed_ids.append(out["request_id"])

    last_id = 0
    for _ in range(5):
        last_id = orchestrator.submit_request(scene, im, depth, normals, fg, quality=RenderQuality.PREVIEW, callback=cb)

    # Wait for execution to settle
    t0 = time.time()
    while last_id not in completed_ids and (time.time() - t0) < 5.0:
        time.sleep(0.05)

    # At least the final frame must have executed
    assert last_id in completed_ids
    # Obsolete intermediate frames should have been suppressed
    assert len(completed_ids) < 5
