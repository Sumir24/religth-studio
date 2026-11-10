"""
RS-SPIKE-3C.3 — Phase F: Uncertainty and Artist Controls Tests
=============================================================
Validates:
  • Environment intensity control response and monotonicity
  • Environment azimuthal rotation and reflection orientation
  • Decoupled diffuse / specular environment weighting
  • Deterministic scene JSON serialization / replay
  • Multi-channel environment uncertainty assessment
"""

import json
import pytest
import numpy as np

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, RenderSettingsData, RenderQuality
)
from studio3a.material import MaterialData
from studio3a.environment import EnvironmentData
from studio3a.uncertainty import UncertaintySupervisor
from metal2.renderer import MetalRenderBackend


@pytest.fixture(scope="module")
def control_test_fixtures():
    H, W = 128, 128
    cx, cy, radius = 64.0, 64.0, 45.0
    y_coords, x_coords = np.mgrid[0:H, 0:W]
    dx, dy = (x_coords - cx), (y_coords - cy)
    r2 = dx * dx + dy * dy
    sphere_mask = r2 <= (radius * radius)

    depth_map = np.full((H, W), 2.5, dtype=np.float32)
    normals_map = np.zeros((H, W, 3), dtype=np.float32)
    normals_map[:, :, 2] = 1.0
    dz = np.sqrt(np.maximum(radius * radius - r2[sphere_mask], 0.0))
    normals_map[sphere_mask, 0] = dx[sphere_mask] / radius
    normals_map[sphere_mask, 1] = -dy[sphere_mask] / radius
    normals_map[sphere_mask, 2] = dz / radius
    depth_map[sphere_mask] = 2.0 - (dz / radius) * 0.3

    image_orig = np.full((H, W, 3), 0.5, dtype=np.float32)
    fg_mask = sphere_mask

    return {
        "H": H, "W": W,
        "depth_map": depth_map,
        "normals_map": normals_map,
        "image_orig": image_orig,
        "fg_mask": fg_mask
    }


def make_artist_scene(intensity: float = 1.0, rotation_deg: float = 0.0, diff_w: float = 1.0, spec_w: float = 1.0, mat: MaterialData = None) -> StudioScene:
    if mat is None:
        mat = MaterialData.polished_metal()
    return StudioScene(
        camera=CameraData(pos=[0.0, 0.0, 2.0], target=[0.0, 0.0, 0.0], fov_deg=45.0),
        subject=SubjectProxyData(
            proxy_type=ProxyType.SPHERE,
            position=[0.0, 0.0, 0.0],
            dimensions=[0.25, 0.25, 0.25],
            material=mat
        ),
        receiver=ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=-0.35),
        lights=[],
        environment=EnvironmentData(
            enabled=True,
            intensity=intensity,
            rotation_deg=rotation_deg,
            diffuse_weight=diff_w,
            specular_weight=spec_w,
            tint_rgb=[1.0, 1.0, 1.0]
        ),
        render_settings=RenderSettingsData(
            quality=RenderQuality.PREVIEW,
            preview_samples=16,
            enable_specular=True,
            enable_contact_grounding=False
        )
    )


def test_environment_intensity_control_monotonicity(control_test_fixtures):
    """Verifies that increasing environment intensity increases foreground specular radiance monotonically."""
    f = control_test_fixtures
    backend = MetalRenderBackend()
    intensities = [0.0, 0.5, 1.0, 2.0]
    spec_means = []

    for intens in intensities:
        scene = make_artist_scene(intensity=intens)
        res = backend.render(scene, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])
        fg_spec = res["specular_radiance"][f["fg_mask"]]
        spec_means.append(float(np.mean(fg_spec)))

    # Assert strictly non-decreasing
    for i in range(len(spec_means) - 1):
        assert spec_means[i+1] > spec_means[i], f"Non-monotonic specular radiance: {spec_means}"


def test_environment_rotation_controls(control_test_fixtures):
    """Verifies that rotating environment changes reflection coordinates deterministically."""
    f = control_test_fixtures
    backend = MetalRenderBackend()

    scene_0 = make_artist_scene(intensity=1.0, rotation_deg=0.0)
    res_0 = backend.render(scene_0, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    scene_90 = make_artist_scene(intensity=1.0, rotation_deg=90.0)
    res_90 = backend.render(scene_90, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    scene_360 = make_artist_scene(intensity=1.0, rotation_deg=360.0)
    res_360 = backend.render(scene_360, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    # 90-degree rotation must produce distinct reflection pattern
    diff_0_90 = np.mean(np.abs(res_0["specular_radiance"] - res_90["specular_radiance"]))
    assert diff_0_90 > 0.05, f"Rotation by 90 degrees did not change reflection: diff = {diff_0_90}"

    # 360-degree rotation must match 0-degree rotation within numerical error
    diff_0_360 = np.mean(np.abs(res_0["specular_radiance"] - res_360["specular_radiance"]))
    assert diff_0_360 < 1e-4, f"360-degree rotation did not match 0 degrees: diff = {diff_0_360}"


def test_diffuse_specular_weight_decoupling(control_test_fixtures):
    """Verifies that diffuse_weight and specular_weight can be adjusted independently."""
    f = control_test_fixtures
    backend = MetalRenderBackend()
    dielectric_mat = MaterialData.plastic()

    # Specular weight 0 -> zero specular
    scene_nospec = make_artist_scene(intensity=1.0, diff_w=1.0, spec_w=0.0, mat=dielectric_mat)
    res_nospec = backend.render(scene_nospec, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])
    assert np.max(res_nospec["specular_radiance"]) == 0.0
    assert np.mean(res_nospec["direct_irradiance"][f["fg_mask"]]) > 0.0

    # Diffuse weight 0 -> zero diffuse
    scene_nodiff = make_artist_scene(intensity=1.0, diff_w=0.0, spec_w=1.0, mat=dielectric_mat)
    res_nodiff = backend.render(scene_nodiff, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])
    assert np.max(res_nodiff["direct_irradiance"]) == 0.0
    assert np.mean(res_nodiff["specular_radiance"][f["fg_mask"]]) > 0.0


def test_json_replay_determinism(control_test_fixtures):
    """Verifies that scene with environment serializes to JSON and produces identical renders after replay."""
    f = control_test_fixtures
    backend = MetalRenderBackend()

    scene_orig = make_artist_scene(intensity=1.4, rotation_deg=65.0, diff_w=0.8, spec_w=1.2)
    res_orig = backend.render(scene_orig, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    # Serialize to JSON and reload
    json_str = json.dumps(scene_orig.to_dict())
    scene_loaded = StudioScene.from_dict(json.loads(json_str))

    res_loaded = backend.render(scene_loaded, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    mae_relit = np.mean(np.abs(res_orig["relit_srgb"] - res_loaded["relit_srgb"]))
    assert mae_relit == 0.0, f"JSON serialization replay mismatch: {mae_relit}"


def test_uncertainty_supervisor_environment_channels():
    """Verifies that UncertaintySupervisor correctly categorizes environment metadata."""
    # 1. Disabled
    env_dis = EnvironmentData(enabled=False)
    u_dis = UncertaintySupervisor.evaluate_environment_uncertainty(env_dis)
    assert u_dis["status"] == "DISABLED"
    assert u_dis["confidence"] == 0.0

    # 2. Synthetic Default
    env_syn = EnvironmentData(enabled=True, asset_path=None)
    u_syn = UncertaintySupervisor.evaluate_environment_uncertainty(env_syn)
    assert u_syn["status"] == "SYNTHETIC_DEFAULT"
    assert u_syn["confidence"] == 0.80
    assert u_syn["is_physically_calibrated"] is True

    # 3. Known HDR
    env_hdr = EnvironmentData(enabled=True, asset_path="studio.exr", is_hdr=True)
    u_hdr = UncertaintySupervisor.evaluate_environment_uncertainty(env_hdr)
    assert u_hdr["status"] == "KNOWN_HDR"
    assert u_hdr["confidence"] == 0.95
    assert u_hdr["is_physically_calibrated"] is True

    # 4. Estimated SDR
    env_sdr = EnvironmentData(enabled=True, asset_path="room.jpg", is_hdr=False)
    u_sdr = UncertaintySupervisor.evaluate_environment_uncertainty(env_sdr)
    assert u_sdr["status"] == "ESTIMATED_SDR"
    assert u_sdr["confidence"] == 0.50
    assert u_sdr["is_physically_calibrated"] is False
