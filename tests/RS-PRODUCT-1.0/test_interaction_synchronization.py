"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Integration Tests: Dual-Viewport & API Synchronization
Verifies 3D stage projection with gizmo, camera orbit, and FastAPI REST endpoint integration.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from relight_studio.controller import StudioAppController
from relight_studio.server import create_app


@pytest.fixture
def test_app():
    img_path = "benchmarks/reference_ibl/diagnostic_boards/synthetic_studio_env_preview.png"
    ctrl = StudioAppController(sample_image_path=img_path, use_metal=False)
    app = create_app(ctrl)
    client = TestClient(app)
    return client, ctrl


def test_3d_stage_canvas_generation(test_app):
    client, ctrl = test_app
    canvas = ctrl.render_3d_stage_canvas(width=640, height=480, draw_gizmo=True)
    assert canvas.shape == (480, 640, 3)
    assert canvas.dtype == np.uint8
    # Ensure canvas is not blank
    assert np.any(canvas > 30)


def test_api_full_state_endpoint(test_app):
    client, ctrl = test_app
    res = client.get("/api/state/full")
    assert res.status_code == 200
    data = res.json()
    assert "selected_id" in data
    assert "hierarchy" in data
    assert "inspector" in data
    assert "telemetry" in data


def test_api_light_mutation_sync(test_app):
    client, ctrl = test_app
    light_id = ctrl.current_scene.lights[0].id

    # Update transform via API
    res = client.post("/api/light/transform", json={
        "id": light_id,
        "pos": [1.8, 2.4, 1.2],
        "width": 0.9,
        "height": 0.9
    })
    assert res.status_code == 200

    # Verify controller scene updated
    l = ctrl.current_scene.get_light(light_id)
    assert np.allclose(l.position, [1.8, 2.4, 1.2])
    assert l.width == 0.9

    # Verify inspector endpoint reflects change
    insp_res = client.get("/api/state/full")
    insp_data = insp_res.json()["inspector"]
    assert np.allclose(insp_data["position"], [1.8, 2.4, 1.2])


def test_api_undo_redo(test_app):
    client, ctrl = test_app
    orig_yaw = ctrl.current_scene.lights[0].rotation_deg[1]

    # Mutate rotation
    client.post("/api/light/transform", json={
        "id": ctrl.current_scene.lights[0].id,
        "rot_deg": [-30.0, orig_yaw + 25.0, 0.0]
    })
    assert ctrl.current_scene.lights[0].rotation_deg[1] == orig_yaw + 25.0

    # Undo
    client.post("/api/undo")
    assert ctrl.current_scene.lights[0].rotation_deg[1] == orig_yaw

    # Redo
    client.post("/api/redo")
    assert ctrl.current_scene.lights[0].rotation_deg[1] == orig_yaw + 25.0


def test_api_image_streams(test_app):
    client, ctrl = test_app
    res_photo = client.get("/api/images/photo")
    assert res_photo.status_code == 200
    assert res_photo.headers["content-type"] == "image/jpeg"

    res_orig = client.get("/api/images/orig")
    assert res_orig.status_code == 200
    assert res_orig.headers["content-type"] == "image/jpeg"

    res_stage = client.get("/api/images/stage")
    assert res_stage.status_code == 200
    assert res_stage.headers["content-type"] == "image/png"
