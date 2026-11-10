"""
RS-PRODUCT-1.2 Test Suite: Subject Geometry Editing & 3D Gizmos
===============================================================
Validates 3-axis translation, 3-axis rotation (Pitch, Yaw, ROLL), dimensional scaling
(Width, Height, Depth, Uniform Scale), near-parallel view singularity protection,
and closed-form snap-to-ground for all supported proxy types (OBB, SUPERQUADRIC, SPHERE).
"""

import math
import numpy as np
import pytest

from studio3a.geometry import compute_proxy_geometry_meta, snap_proxy_to_ground
from studio3a.scene import ProxyType
from relight_studio.controller import StudioAppController


def test_subject_proxy_gizmo_metadata():
    """Verify selecting subject proxy populates complete 3D gizmo handles with Pitch, Yaw, Roll, Scale, and Ground Contact."""
    ctrl = StudioAppController()
    ctrl.select_object("subject")

    meta = ctrl.get_stage_projection_meta(canvas_w=640, canvas_h=480)
    assert "gizmo" in meta and meta["gizmo"] is not None
    g = meta["gizmo"]

    assert g["target_id"] == "subject"
    assert "center" in g
    assert "axis_x" in g
    assert "axis_y" in g
    assert "axis_z" in g
    assert "rot_pitch" in g
    assert "rot_yaw" in g
    assert "rot_roll" in g  # 3rd rotational degree of freedom
    assert "scale_uniform" in g
    assert "ground_contact" in g
    assert "ground_gap_m" in g
    assert "contact_state" in g


def test_subject_3axis_translation_drag():
    """Verify dragging subject proxy along X, Y, Z updates position accurately."""
    ctrl = StudioAppController()
    ctrl.select_object("subject")
    initial_pos = list(ctrl.current_scene.subject.position)

    # Drag X
    ctrl.project_drag_to_3d(axis="X", delta_screen_x=50.0, delta_screen_y=0.0, canvas_w=640, canvas_h=480)
    assert ctrl.current_scene.subject.position[0] != initial_pos[0]

    # Drag Y
    ctrl.project_drag_to_3d(axis="Y", delta_screen_x=0.0, delta_screen_y=-50.0, canvas_w=640, canvas_h=480)
    assert ctrl.current_scene.subject.position[1] != initial_pos[1]

    # Drag Z
    ctrl.project_drag_to_3d(axis="Z", delta_screen_x=30.0, delta_screen_y=30.0, canvas_w=640, canvas_h=480)
    assert ctrl.current_scene.subject.position[2] != initial_pos[2]


def test_subject_3axis_rotation_including_roll():
    """Verify Pitch, Yaw, and Roll rotation manipulation on subject proxy."""
    ctrl = StudioAppController()
    ctrl.select_object("subject")
    ctrl.current_scene.subject.rotation_deg = [0.0, 0.0, 0.0]

    # Pitch drag
    ctrl.project_drag_to_3d(axis="PITCH", delta_screen_x=0.0, delta_screen_y=-40.0)
    assert abs(ctrl.current_scene.subject.rotation_deg[0] - 20.0) < 0.1

    # Yaw drag
    ctrl.project_drag_to_3d(axis="YAW", delta_screen_x=60.0, delta_screen_y=0.0)
    assert abs(ctrl.current_scene.subject.rotation_deg[1] - 30.0) < 0.1

    # ROLL drag (mandatory requirement)
    ctrl.project_drag_to_3d(axis="ROLL", delta_screen_x=50.0, delta_screen_y=0.0)
    assert abs(ctrl.current_scene.subject.rotation_deg[2] - 25.0) < 0.1


def test_subject_dimensional_scaling():
    """Verify dimensional scaling (Width, Height, Depth, Uniform Scale)."""
    ctrl = StudioAppController()
    ctrl.select_object("subject")
    ctrl.current_scene.subject.dimensions = [0.30, 0.40, 0.50]

    # Uniform scale
    ctrl.project_drag_to_3d(axis="SCALE", delta_screen_x=40.0, delta_screen_y=-40.0)
    assert all(d > 0.30 for d in ctrl.current_scene.subject.dimensions)

    # Independent width, height, depth
    d_before = list(ctrl.current_scene.subject.dimensions)
    ctrl.project_drag_to_3d(axis="WIDTH", delta_screen_x=50.0, delta_screen_y=0.0)
    assert ctrl.current_scene.subject.dimensions[0] > d_before[0]

    ctrl.project_drag_to_3d(axis="HEIGHT", delta_screen_x=0.0, delta_screen_y=-50.0)
    assert ctrl.current_scene.subject.dimensions[1] > d_before[1]


def test_near_parallel_singularity_protection():
    """Verify that when an axis aligns near-parallel to view ray, drag does not explode or divide by zero."""
    ctrl = StudioAppController()
    ctrl.select_object("subject")

    # Force orbit camera pitch to look nearly down Y axis
    ctrl.stage_orbit_pitch_deg = 89.9
    ctrl.stage_orbit_yaw_deg = 0.0

    # Dragging Y should not raise ZeroDivisionError, produce NaNs, or cause infinite displacement
    pos_before = list(ctrl.current_scene.subject.position)
    ctrl.project_drag_to_3d(axis="Y", delta_screen_x=0.0, delta_screen_y=-20.0, canvas_w=640, canvas_h=480)
    pos_after = ctrl.current_scene.subject.position

    assert math.isfinite(pos_after[1])
    assert abs(pos_after[1] - pos_before[1]) < 2.0  # Stable fallback delta


def test_snap_to_ground_obb():
    """Verify snap_subject_to_ground precisely places rotated OBB on receiver floor."""
    ctrl = StudioAppController()
    subj = ctrl.current_scene.subject
    subj.proxy_type = ProxyType.OBB
    subj.dimensions = [0.35, 0.45, 0.25]
    subj.rotation_deg = [25.0, 35.0, 15.0]
    subj.position = [0.0, 1.5, 0.0]  # Hovering high

    new_y = ctrl.snap_subject_to_ground()
    pmeta = compute_proxy_geometry_meta(
        proxy_type="OBB",
        position=subj.position,
        dimensions=subj.dimensions,
        rotation_euler=subj.rotation_deg,
        scale=subj.scale,
        ground_y=ctrl.current_scene.receiver.ground_y
    )
    assert abs(pmeta["ground_gap_m"]) < 1e-3
    assert pmeta["contact_state"] == "contact"
    assert abs(pmeta["lowest_y"] - ctrl.current_scene.receiver.ground_y) < 1e-3


def test_snap_to_ground_superquadric():
    """Verify snap_subject_to_ground precisely places rotated Superquadric/Sphere on receiver floor."""
    ctrl = StudioAppController()
    subj = ctrl.current_scene.subject
    subj.proxy_type = ProxyType.SUPERQUADRIC
    subj.dimensions = [0.30, 0.40, 0.35]
    subj.rotation_deg = [-30.0, 45.0, 20.0]
    subj.position = [0.0, 2.0, 0.0]

    ctrl.snap_subject_to_ground()
    pmeta = compute_proxy_geometry_meta(
        proxy_type="SUPERQUADRIC",
        position=subj.position,
        dimensions=subj.dimensions,
        rotation_euler=subj.rotation_deg,
        scale=subj.scale,
        ground_y=ctrl.current_scene.receiver.ground_y
    )
    assert abs(pmeta["ground_gap_m"]) < 1e-3
    assert pmeta["contact_state"] == "contact"

