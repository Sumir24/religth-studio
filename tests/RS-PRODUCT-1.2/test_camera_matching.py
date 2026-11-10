"""
RS-PRODUCT-1.2 Test Suite: Camera Matching & Lens Presets
=========================================================
Validates bidirectional mathematical coupling between vertical FOV and 35mm full-frame
focal length, standard photographer presets (24mm, 35mm, 50mm, 85mm, 105mm),
automatic framing (fit_camera_to_subject), and camera pose manipulation.
"""

import math
import numpy as np
import pytest

from studio3a.camera import Camera3D, fov_to_focal_length_mm, focal_length_to_fov_deg
from studio3a.scene import StudioScene, CameraData
from relight_studio.controller import StudioAppController


def test_focal_length_fov_bidirectional_math():
    """Verify exact pinhole trigonometric relationship: f = (sensor_h / 2) / tan(fov / 2)."""
    sensor_h = 24.0

    # 50mm normal lens
    fov_50 = focal_length_to_fov_deg(50.0, sensor_height_mm=sensor_h)
    assert 26.5 <= fov_50 <= 27.5, f"Unexpected 50mm FOV: {fov_50}"
    fl_roundtrip = fov_to_focal_length_mm(fov_50, sensor_height_mm=sensor_h)
    assert abs(fl_roundtrip - 50.0) < 0.2, f"Roundtrip failure: {fl_roundtrip}"

    # Extreme focal lengths
    for fl in [14.0, 24.0, 35.0, 50.0, 85.0, 105.0, 200.0, 400.0]:
        fov = focal_length_to_fov_deg(fl, sensor_height_mm=sensor_h)
        fl_rec = fov_to_focal_length_mm(fov, sensor_height_mm=sensor_h)
        assert abs(fl - fl_rec) <= 0.2, f"Failed roundtrip for {fl}mm: got {fl_rec}"


def test_standard_camera_lens_presets():
    """Verify that all standard photographer lens presets apply correctly to scene camera."""
    ctrl = StudioAppController()

    presets_expected = {
        "24mm": (24.0, 53.13),
        "35mm": (35.0, 37.85),
        "50mm": (50.0, 27.00),
        "85mm": (85.0, 16.08),
        "105mm": (105.0, 13.04)
    }

    for preset_name, (expected_fl, expected_fov) in presets_expected.items():
        fl = ctrl.apply_camera_preset(preset_name)
        cam = ctrl.current_scene.camera
        assert abs(fl - expected_fl) < 1e-3
        assert abs(cam.focal_length_mm - expected_fl) < 1e-3
        assert abs(cam.fov_deg - expected_fov) < 0.2, f"Preset {preset_name} FOV {cam.fov_deg} != {expected_fov}"


def test_camera_params_updates():
    """Verify direct camera pose updates (elevation, distance, pitch/yaw)."""
    ctrl = StudioAppController()

    # Update position and target
    ctrl.update_camera_params(pos=[1.0, 2.0, 3.0], target=[0.0, 0.5, 0.0])
    assert np.allclose(ctrl.current_scene.camera.pos, [1.0, 2.0, 3.0])
    assert np.allclose(ctrl.current_scene.camera.target, [0.0, 0.5, 0.0])

    # Update elevation
    ctrl.update_camera_params(elevation=1.85)
    assert abs(ctrl.current_scene.camera.pos[1] - 1.85) < 1e-4

    # Update distance while keeping target
    ctrl.update_camera_params(distance=4.0)
    cur_dist = float(np.linalg.norm(np.array(ctrl.current_scene.camera.pos) - np.array(ctrl.current_scene.camera.target)))
    assert abs(cur_dist - 4.0) < 0.05

    # Update focal length
    ctrl.update_camera_params(focal_length_mm=85.0)
    assert abs(ctrl.current_scene.camera.focal_length_mm - 85.0) < 0.1
    assert abs(ctrl.current_scene.camera.fov_deg - 16.07) < 0.2


def test_fit_camera_to_subject():
    """Verify automatic camera framing adjusts distance according to subject proxy size."""
    ctrl = StudioAppController()
    ctrl.update_subject_proxy_params(position=[0.0, 0.5, 0.0], dimensions=[0.4, 0.5, 0.4])
    ctrl.apply_camera_preset("50mm")

    # Framing ratio 0.65
    dist = ctrl.fit_camera_to_subject(frame_ratio=0.65)
    h_total = 1.0
    fov_rad = math.radians(ctrl.current_scene.camera.fov_deg)
    expected_dist = h_total / (2.0 * 0.65 * math.tan(fov_rad / 2.0))
    assert abs(dist - expected_dist) < 0.05

    # Verify target matches subject center
    assert np.allclose(ctrl.current_scene.camera.target, ctrl.current_scene.subject.position)


def test_reset_camera_photo():
    """Verify reset_camera_photo restores standard defaults."""
    ctrl = StudioAppController()
    ctrl.update_camera_params(pos=[5.0, 8.0, 10.0], fov_deg=80.0)

    ctrl.reset_camera_photo()
    cam = ctrl.current_scene.camera
    assert np.allclose(cam.pos, [0.0, 1.2, 2.5])
    assert np.allclose(cam.target, [0.0, 0.35, 0.0])
    assert abs(cam.fov_deg - 26.99) < 0.2
    assert abs(cam.focal_length_mm - 50.0) < 0.2
