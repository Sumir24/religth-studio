"""
RELIGHT STUDIO — RS-PRODUCT-1.1
Integration Tests: Server REST Endpoints and Asynchronous Interaction APIs
"""

import pytest
from fastapi.testclient import TestClient
from relight_studio.controller import StudioAppController
from relight_studio.server import create_app


@pytest.fixture
def client():
    ctrl = StudioAppController()
    app = create_app(ctrl)
    return TestClient(app)


def test_projection_meta_endpoint(client):
    """Verifies GET /api/stage/projection_meta returns projected screen points."""
    resp = client.get("/api/stage/projection_meta?width=640&height=480")
    assert resp.status_code == 200
    data = resp.json()
    assert "lights" in data
    assert "selected_id" in data
    assert "gizmo" in data
    assert data["gizmo"] is not None
    assert "center" in data["gizmo"]
    assert "axis_x" in data["gizmo"]


def test_stage_drag_endpoint(client):
    """Verifies POST /api/stage/drag modifies light coordinates and returns updated position."""
    resp = client.post("/api/stage/drag", json={
        "axis": "X",
        "dx": 40.0,
        "dy": 0.0,
        "width": 640,
        "height": 480
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "position" in data
    assert len(data["position"]) == 3


def test_stage_focus_and_reset_endpoints(client):
    """Verifies POST /api/stage/focus and POST /api/stage/reset."""
    resp_focus = client.post("/api/stage/focus")
    assert resp_focus.status_code == 200
    assert resp_focus.json()["status"] == "ok"

    resp_reset = client.post("/api/stage/reset")
    assert resp_reset.status_code == 200
    data_reset = resp_reset.json()
    assert data_reset["status"] == "ok"
    assert data_reset["yaw"] == 35.0
    assert data_reset["pitch"] == 25.0
    assert data_reset["dist"] == 3.8


def test_light_preset_endpoint(client):
    """Verifies POST /api/light/preset applies starter lighting presets."""
    resp = client.post("/api/light/preset", json={"preset": "rim_strip"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "light_id" in data


def test_subject_params_endpoint(client):
    """Verifies POST /api/subject/params updates proxy dimensions and elevation."""
    resp = client.post("/api/subject/params", json={
        "proxy_type": "SPHERE",
        "dimensions": [0.45, 0.45, 0.45],
        "position_y": 0.05
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_interaction_lifecycle_endpoints(client):
    """Verifies POST /api/interaction/begin and /api/interaction/end."""
    resp_begin = client.post("/api/interaction/begin")
    assert resp_begin.status_code == 200
    assert resp_begin.json()["status"] == "ok"

    resp_end = client.post("/api/interaction/end")
    assert resp_end.status_code == 200
    assert resp_end.json()["status"] == "ok"
