"""
RELIGHT STUDIO — RS-PRODUCT-1.1
Unit & Integration Tests: 3D Gizmo Projection, Hit-Testing, and Drag Mapping
"""

import pytest
import numpy as np
from relight_studio.controller import StudioAppController
from studio3a.scene import RenderQuality


@pytest.fixture
def controller():
    # Initialize controller with dummy/sample image
    ctrl = StudioAppController()
    return ctrl


def test_stage_projection_meta_structure(controller):
    """Verifies that get_stage_projection_meta returns complete 3D-to-2D projected points."""
    meta = controller.get_stage_projection_meta(width=640, height=480)
    assert "selected_id" in meta
    assert "lights" in meta
    assert len(meta["lights"]) >= 1
    
    # Active light gizmo
    assert "gizmo" in meta
    gizmo = meta["gizmo"]
    assert gizmo is not None
    assert "center" in gizmo
    assert "axis_x" in gizmo
    assert "axis_y" in gizmo
    assert "axis_z" in gizmo
    assert "rot_pitch" in gizmo
    assert "rot_yaw" in gizmo

    # Screen coordinates within canvas bounds or valid integers
    cx, cy = gizmo["center"]
    assert isinstance(cx, (int, float)) and isinstance(cy, (int, float))

    # Subject & camera projection
    assert "subject" in meta
    assert "center" in meta["subject"]
    assert "camera" in meta


def test_project_drag_to_3d_translation(controller):
    """Verifies screen pixel drag maps directly and predictably to world coordinates."""
    scene = controller.current_scene
    light = scene.get_light(controller.selected_object_id)
    assert light is not None
    orig_pos = list(light.position)

    # Drag X positive
    controller.project_drag_to_3d(axis="X", delta_screen_x=50.0, delta_screen_y=0.0)
    assert light.position[0] != orig_pos[0]
    x_after_drag = light.position[0]

    # Drag Y positive (screen Y goes down, so negative delta_y is upward in 3D)
    controller.project_drag_to_3d(axis="Y", delta_screen_x=0.0, delta_screen_y=-50.0)
    assert light.position[1] != orig_pos[1]

    # Drag Z positive
    controller.project_drag_to_3d(axis="Z", delta_screen_x=30.0, delta_screen_y=30.0)
    assert light.position[2] != orig_pos[2]


def test_project_drag_to_3d_rotation(controller):
    """Verifies dragging rotational handles updates pitch and yaw angles."""
    scene = controller.current_scene
    light = scene.get_light(controller.selected_object_id)
    orig_rot = list(light.rotation_deg)

    # Pitch drag
    controller.project_drag_to_3d(axis="PITCH", delta_screen_x=0.0, delta_screen_y=20.0)
    assert light.rotation_deg[0] != orig_rot[0]

    # Yaw drag
    controller.project_drag_to_3d(axis="YAW", delta_screen_x=30.0, delta_screen_y=0.0)
    assert light.rotation_deg[1] != orig_rot[1]


def test_project_drag_to_3d_dimensions(controller):
    """Verifies dragging size handles modifies area light width and height."""
    scene = controller.current_scene
    light = scene.get_light(controller.selected_object_id)
    orig_w = light.width
    orig_h = light.height

    # Width drag
    controller.project_drag_to_3d(axis="WIDTH", delta_screen_x=25.0, delta_screen_y=0.0)
    assert light.width > orig_w

    # Height drag
    controller.project_drag_to_3d(axis="HEIGHT", delta_screen_x=0.0, delta_screen_y=-25.0)
    assert light.height > orig_h


def test_camera_navigation_isolation(controller):
    """Verifies camera orbit and pan do NOT alter scene object transforms."""
    scene = controller.current_scene
    light = scene.get_light(controller.selected_object_id)
    initial_light_pos = list(light.position)

    # Orbit camera
    controller.stage_orbit_yaw_deg += 45.0
    controller.stage_orbit_pitch_deg += 15.0
    controller.stage_orbit_dist = 5.0
    controller.stage_pan_offset = [0.5, -0.5]

    # Check light pos completely untouched
    assert list(light.position) == initial_light_pos

    # Test Focus and Reset
    controller.focus_selected_object()
    assert controller.stage_orbit_dist == 3.2
    assert controller.stage_pan_offset == [light.position[0], light.position[2]]

    controller.reset_camera_stage()
    assert controller.stage_orbit_yaw_deg == 35.0
    assert controller.stage_orbit_pitch_deg == 25.0
    assert controller.stage_orbit_dist == 3.8
    assert controller.stage_pan_offset == [0.0, 0.0]
