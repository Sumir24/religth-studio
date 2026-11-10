"""
RS-PRODUCT-1.2 Test Suite: REST API Endpoints
=============================================
Validates all newly implemented HTTP endpoints for camera presets,
framing, ground snapping, alignment metadata, and overlay streaming.
"""

import pytest
from fastapi.testclient import TestClient

from relight_studio.server import create_app
from relight_studio.controller import StudioAppController


@pytest.fixture
def client():
    ctrl = StudioAppController()
    app = create_app(controller=ctrl)
    return TestClient(app)


def test_api_camera_alignment_meta(client):
    """Verify GET /api/camera/alignment_meta returns all required fields and diagnostics."""
    resp = client.get("/api/camera/alignment_meta?width=800&height=600")
    assert resp.status_code == 200
    data = resp.json()

    assert data["image_width"] == 800
    assert data["image_height"] == 600
    assert len(data["corners_screen"]) == 8
    assert len(data["edges"]) == 12
    assert "diagnostics" in data
    assert "silhouette_iou" in data["diagnostics"]


def test_api_camera_presets(client):
    """Verify POST /api/camera/preset applies standard focal lengths."""
    for preset in ["24mm", "35mm", "50mm", "85mm", "105mm"]:
        resp = client.post("/api/camera/preset", json={"preset": preset})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        expected_fl = float(preset.replace("mm", ""))
        assert abs(data["focal_length_mm"] - expected_fl) < 0.1


def test_api_camera_fit_and_reset(client):
    """Verify POST /api/camera/fit and POST /api/camera/reset."""
    fit_resp = client.post("/api/camera/fit")
    assert fit_resp.status_code == 200
    assert "distance" in fit_resp.json()

    reset_resp = client.post("/api/camera/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "ok"


def test_api_subject_params_and_snap_ground(client):
    """Verify POST /api/subject/params and POST /api/subject/snap_ground."""
    # Update subject params with 3-axis rotation and scale
    update_resp = client.post("/api/subject/params", json={
        "proxy_type": "SUPERQUADRIC",
        "position": [0.0, 1.2, 0.0],
        "rotation_deg": [15.0, 30.0, -10.0],
        "dimensions": [0.35, 0.40, 0.35],
        "scale": [1.0, 1.0, 1.0]
    })
    assert update_resp.status_code == 200

    # Snap to ground
    snap_resp = client.post("/api/subject/snap_ground")
    assert snap_resp.status_code == 200
    data = snap_resp.json()
    assert data["status"] == "ok"
    assert "position_y" in data
    assert data["position_y"] < 1.2  # Dropped towards ground


def test_api_receiver_params(client):
    """Verify POST /api/receiver/params."""
    resp = client.post("/api/receiver/params", json={
        "receiver_type": "CYCLORAMA",
        "ground_y": -0.05,
        "cove_radius": 0.50,
        "wall_z": -1.6
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_images_photo_overlay_modes(client):
    """Verify GET /api/images/photo with different overlay modes."""
    modes = ["wireframe", "silhouette", "guides", "mismatch", "original", "relit"]
    for m in modes:
        resp = client.get(f"/api/images/photo?mode={m}&opacity=0.65")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert len(resp.content) > 1000
