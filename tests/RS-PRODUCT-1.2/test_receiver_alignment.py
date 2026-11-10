"""
RS-PRODUCT-1.2 Test Suite: Receiver & Ground-Contact Alignment
=============================================================
Validates ground plane elevation, cyclorama cove fillet parameters,
ground contact marker calculation, and receiver property updates.
"""

import numpy as np
import pytest

from studio3a.geometry import compute_proxy_geometry_meta
from studio3a.scene import ReceiverType
from relight_studio.controller import StudioAppController


def test_receiver_type_and_cove_updates():
    """Verify updating receiver parameters modifies scene state and inspector representation."""
    ctrl = StudioAppController()

    # Cyclorama with custom cove radius and ground_y
    ctrl.update_receiver_params(receiver_type="CYCLORAMA", ground_y=0.15, cove_radius=0.60, wall_z=-1.5)
    rec = ctrl.current_scene.receiver
    assert rec.receiver_type == ReceiverType.CYCLORAMA
    assert abs(rec.ground_y - 0.15) < 1e-4
    assert abs(rec.cove_radius - 0.60) < 1e-4
    assert abs(rec.wall_z - (-1.5)) < 1e-4

    # Plane receiver
    ctrl.update_receiver_params(receiver_type="PLANE", ground_y=-0.20)
    assert ctrl.current_scene.receiver.receiver_type == ReceiverType.PLANE
    assert abs(ctrl.current_scene.receiver.ground_y - (-0.20)) < 1e-4


def test_ground_contact_line_calculation():
    """Verify ground marker matches the footprint of the lowest point on the ground plane."""
    ctrl = StudioAppController()
    subj = ctrl.current_scene.subject
    subj.position = [0.2, 0.8, -0.1]
    subj.dimensions = [0.3, 0.4, 0.3]
    subj.rotation_deg = [0.0, 0.0, 0.0]

    pmeta = compute_proxy_geometry_meta(
        proxy_type="OBB",
        position=subj.position,
        dimensions=subj.dimensions,
        rotation_euler=subj.rotation_deg,
        scale=subj.scale,
        ground_y=0.0
    )

    # For unrotated OBB, lowest point is at position[1] - dimensions[1] = 0.8 - 0.4 = 0.4
    assert abs(pmeta["lowest_y"] - 0.40) < 1e-4
    assert abs(pmeta["ground_gap_m"] - 0.40) < 1e-4
    assert pmeta["contact_state"] == "hovering"

    # Ground marker world Y should be exactly receiver ground_y
    assert abs(pmeta["ground_marker_world"][1] - 0.0) < 1e-4
    assert abs(pmeta["ground_marker_world"][0] - pmeta["contact_point_world"][0]) < 1e-4
    assert abs(pmeta["ground_marker_world"][2] - pmeta["contact_point_world"][2]) < 1e-4


def test_receiver_inspector_data():
    """Verify receiver inspector data accurately exposes all parametric controls."""
    ctrl = StudioAppController()
    ctrl.select_object("receiver")
    ctrl.update_receiver_params(receiver_type="CYCLORAMA", ground_y=0.05, cove_radius=0.45, wall_z=-1.35)

    data = ctrl.get_inspector_data()
    assert data["type"] == "receiver"
    assert data["receiver_type"] == "CYCLORAMA"
    assert abs(data["ground_y"] - 0.05) < 1e-4
    assert abs(data["cove_radius"] - 0.45) < 1e-4
    assert abs(data["wall_z"] - (-1.35)) < 1e-4

