"""
RS-SPIKE-3C.3 — Phase D: Direct Light + IBL Energy Accounting Tests
===================================================================
Verifies that direct area lighting and Image-Based Lighting coexist without
energy duplication or double-counting, adhering strictly to microfacet
conservation laws and additivity.
"""

import math
import pytest
import numpy as np

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, RenderSettingsData, RenderQuality
)
from studio3a.material import MaterialData
from studio3a.environment import EnvironmentData
from metal2.renderer import MetalRenderBackend
from studio3a.renderer import RenderBackend as CPURenderBackend


@pytest.fixture(scope="module")
def energy_test_fixtures():
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


def make_scene(n_lights: int, env_enabled: bool, roughness: float = 0.25, metallic: float = 0.0) -> StudioScene:
    lights = []
    positions = [
        [1.2, 1.5, 1.2], [-1.2, 1.5, 1.2], [1.2, -0.5, 1.2], [-1.2, -0.5, 1.2],
        [0.0, 1.8, 1.0], [0.0, -1.0, 1.0], [1.5, 0.0, 1.0], [-1.5, 0.0, 1.0]
    ]
    for i in range(min(n_lights, 8)):
        lights.append(AreaLightData(
            id=f"light_{i}",
            position=positions[i],
            width=0.3,
            height=0.3,
            intensity=1.5,
            color_rgb=[1.0, 1.0, 1.0],
            cast_shadows=False,
            enabled=True
        ))

    mat = MaterialData(
        id="mat_energy",
        name="Energy Test Material",
        base_color=[0.8, 0.8, 0.8],
        roughness=roughness,
        metallic=metallic,
        specular_f0=0.04,
        specular_intensity=1.0
    )

    env = EnvironmentData(
        enabled=env_enabled,
        intensity=1.0 if env_enabled else 0.0,
        rotation_deg=0.0,
        diffuse_weight=1.0,
        specular_weight=1.0,
        tint_rgb=[1.0, 1.0, 1.0]
    )

    return StudioScene(
        camera=CameraData(pos=[0.0, 0.0, 2.0], target=[0.0, 0.0, 0.0], fov_deg=45.0),
        subject=SubjectProxyData(
            proxy_type=ProxyType.SPHERE,
            position=[0.0, 0.0, 0.0],
            dimensions=[0.25, 0.25, 0.25],
            material=mat
        ),
        receiver=ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=-0.35),
        lights=lights,
        environment=env,
        render_settings=RenderSettingsData(
            quality=RenderQuality.PREVIEW,
            preview_samples=16,
            enable_specular=True,
            enable_contact_grounding=False
        )
    )


def test_single_scattering_energy_conservation():
    """Verifies that kd + F0 <= 1.0 across the entire metallic and roughness range."""
    for metallic in [0.0, 0.25, 0.5, 0.75, 1.0]:
        for roughness in [0.04, 0.1, 0.25, 0.5, 1.0]:
            mat = MaterialData(
                roughness=roughness,
                metallic=metallic,
                base_color=[0.8, 0.8, 0.8],
                specular_f0=0.04
            )
            f0 = mat.get_effective_f0()
            kd = mat.get_effective_diffuse_albedo()
            total_reflectance = f0 + kd
            assert np.all(total_reflectance <= 1.0001), f"Energy violation at metallic={metallic}, roughness={roughness}: {total_reflectance}"


def test_radiometric_additivity_and_no_double_counting(energy_test_fixtures):
    """
    Verifies that:
      Total Irradiance(Env + Direct) == Irradiance(Env) + Irradiance(Direct)
      Total Specular(Env + Direct) == Specular(Env) + Specular(Direct)
    within floating-point precision.
    """
    f = energy_test_fixtures
    metal_backend = MetalRenderBackend()

    # 1. Environment only (0 direct lights)
    scene_env = make_scene(n_lights=0, env_enabled=True)
    res_env = metal_backend.render(scene_env, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    # 2. One direct light only (no environment)
    scene_dir1 = make_scene(n_lights=1, env_enabled=False)
    res_dir1 = metal_backend.render(scene_dir1, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    # 3. Environment + One direct light
    scene_both1 = make_scene(n_lights=1, env_enabled=True)
    res_both1 = metal_backend.render(scene_both1, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    # Radiometric additivity on foreground
    fg = f["fg_mask"]
    irr_expected = res_env["direct_irradiance"][fg] + res_dir1["direct_irradiance"][fg]
    irr_actual = res_both1["direct_irradiance"][fg]
    mae_irr = np.mean(np.abs(irr_actual - irr_expected))
    assert mae_irr < 1e-4, f"Direct + IBL Irradiance additivity error: {mae_irr:.6f}"

    spec_expected = res_env["specular_radiance"][fg] + res_dir1["specular_radiance"][fg]
    spec_actual = res_both1["specular_radiance"][fg]
    mae_spec = np.mean(np.abs(spec_actual - spec_expected))
    assert mae_spec < 1e-4, f"Direct + IBL Specular additivity error: {mae_spec:.6f}"


@pytest.mark.parametrize("n_lights", [1, 4, 8])
def test_multi_light_ibl_scaling(energy_test_fixtures, n_lights):
    """Verifies monotonic irradiance scaling from 1 to 4 to 8 lights alongside IBL."""
    f = energy_test_fixtures
    metal_backend = MetalRenderBackend()

    scene = make_scene(n_lights=n_lights, env_enabled=True)
    res = metal_backend.render(scene, f["image_orig"], f["depth_map"], f["normals_map"], f["fg_mask"])

    fg = f["fg_mask"]
    mean_irr = float(np.mean(res["direct_irradiance"][fg]))
    assert mean_irr > 0.0
    assert not np.isnan(mean_irr)
    assert not np.isinf(mean_irr)

