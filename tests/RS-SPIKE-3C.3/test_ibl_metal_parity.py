"""
RS-SPIKE-3C.3 — Phase C Verification: CPU–Metal Parity with Image-Based Lighting
================================================================================
Verifies that the native Metal GPU renderer reproduces the CPU reference implementation
under environment-only and hybrid direct + environment lighting across materials.
"""

import math
import pytest
import numpy as np

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData, AreaLightData,
    ProxyType, ReceiverType, RenderSettingsData, RenderQuality, EnergyConvention
)
from studio3a.material import MaterialData
from studio3a.environment import EnvironmentData
from studio3a.renderer import RenderBackend as CPURenderBackend
from metal2.renderer import MetalRenderBackend


@pytest.fixture(scope="module")
def synthetic_scene_fixtures():
    """Generates standard test scene buffers at 320x240."""
    H, W = 240, 320
    
    # Simple synthetic sphere depth & normals
    cx, cy = W / 2.0, H / 2.0
    radius = 60.0
    
    y_coords, x_coords = np.mgrid[0:H, 0:W]
    dx = (x_coords - cx)
    dy = (y_coords - cy)
    r2 = dx * dx + dy * dy
    sphere_mask = r2 <= (radius * radius)
    
    depth_map = np.full((H, W), 2.5, dtype=np.float32)
    normals_map = np.zeros((H, W, 3), dtype=np.float32)
    normals_map[:, :, 2] = 1.0  # background pointing towards camera
    
    dz = np.sqrt(np.maximum(radius * radius - r2[sphere_mask], 0.0))
    nx = dx[sphere_mask] / radius
    ny = -dy[sphere_mask] / radius
    nz = dz / radius
    
    normals_map[sphere_mask, 0] = nx
    normals_map[sphere_mask, 1] = ny
    normals_map[sphere_mask, 2] = nz
    depth_map[sphere_mask] = 2.0 - (dz / radius) * 0.3
    
    image_orig = np.full((H, W, 3), 0.5, dtype=np.float32)
    fg_mask = sphere_mask
    prot_mask = np.zeros((H, W), dtype=bool)
    
    return {
        "H": H, "W": W,
        "depth_map": depth_map,
        "normals_map": normals_map,
        "image_orig": image_orig,
        "fg_mask": fg_mask,
        "prot_mask": prot_mask
    }


def create_test_scene(material: MaterialData, env_intensity: float = 1.0, env_rot: float = 45.0, add_lights: int = 0) -> StudioScene:
    lights = []
    if add_lights >= 1:
        lights.append(AreaLightData(
            id="key_light",
            position=[1.2, 1.5, 1.2],
            rotation_deg=[-30.0, 45.0, 0.0],
            width=0.4,
            height=0.4,
            intensity=3.0,
            color_rgb=[1.0, 0.95, 0.9],
            cast_shadows=True,
            enabled=True
        ))
    if add_lights >= 4:
        lights.append(AreaLightData(
            id="fill_light",
            position=[-1.2, 0.8, 1.0],
            rotation_deg=[-15.0, -45.0, 0.0],
            width=0.6,
            height=0.6,
            intensity=1.5,
            color_rgb=[0.9, 0.95, 1.0],
            cast_shadows=False,
            enabled=True
        ))
        lights.append(AreaLightData(
            id="rim_light",
            position=[0.0, 1.8, -1.0],
            rotation_deg=[-45.0, 180.0, 0.0],
            width=0.3,
            height=0.3,
            intensity=2.0,
            color_rgb=[1.0, 1.0, 1.0],
            cast_shadows=True,
            enabled=True
        ))
        lights.append(AreaLightData(
            id="accent_light",
            position=[0.8, -0.5, 0.8],
            rotation_deg=[15.0, 30.0, 0.0],
            width=0.2,
            height=0.2,
            intensity=1.0,
            color_rgb=[1.0, 0.8, 0.6],
            cast_shadows=False,
            enabled=True
        ))

    scene = StudioScene(
        camera=CameraData(pos=[0.0, 0.0, 2.0], target=[0.0, 0.0, 0.0], fov_deg=45.0),
        subject=SubjectProxyData(
            proxy_type=ProxyType.SPHERE,
            position=[0.0, 0.0, 0.0],
            dimensions=[0.3, 0.3, 0.3],
            material=material
        ),
        receiver=ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=-0.35),
        lights=lights,
        environment=EnvironmentData(
            enabled=True,
            intensity=env_intensity,
            rotation_deg=env_rot,
            diffuse_weight=1.0,
            specular_weight=1.0,
            tint_rgb=[1.0, 1.0, 1.0]
        ),
        render_settings=RenderSettingsData(
            quality=RenderQuality.PREVIEW,
            preview_samples=16,
            enable_specular=True,
            enable_contact_grounding=True
        )
    )
    return scene


@pytest.mark.parametrize("material_fn", [
    MaterialData.plastic,
    MaterialData.rough_metal,
    MaterialData.polished_metal,
    MaterialData.marble,
    MaterialData.fabric
])
def test_cpu_metal_ibl_alone_parity(synthetic_scene_fixtures, material_fn):
    """Verifies CPU–Metal numerical parity for pure environment lighting across material presets."""
    f = synthetic_scene_fixtures
    mat = material_fn()
    scene = create_test_scene(material=mat, env_intensity=1.2, env_rot=60.0, add_lights=0)

    cpu_backend = CPURenderBackend()
    metal_backend = MetalRenderBackend()

    cpu_res = cpu_backend.render(
        scene=scene,
        image_orig_srgb=f["image_orig"],
        depth_map=f["depth_map"],
        normals_map=f["normals_map"],
        fg_mask=f["fg_mask"],
        quality=RenderQuality.PREVIEW
    )

    metal_res = metal_backend.render(
        scene=scene,
        image_orig_srgb=f["image_orig"],
        depth_map=f["depth_map"],
        normals_map=f["normals_map"],
        fg_mask=f["fg_mask"],
        quality=RenderQuality.PREVIEW
    )

    # 1. Diffuse Irradiance Parity
    cpu_irr = cpu_res["direct_irradiance"]
    metal_irr = metal_res["direct_irradiance"]
    mae_irr = np.mean(np.abs(cpu_irr - metal_irr))
    assert mae_irr < 0.005, f"Diffuse Irradiance MAE exceeded threshold: {mae_irr:.6f}"

    # 2. Specular Radiance Parity
    cpu_spec = cpu_res["specular_radiance"]
    metal_spec = metal_res["specular_radiance"]
    mae_spec = np.mean(np.abs(cpu_spec - metal_spec))
    assert mae_spec < 0.005, f"Specular Radiance MAE exceeded threshold: {mae_spec:.6f}"

    # 3. Final Relit Image Parity
    cpu_relit = cpu_res["relit_srgb"]
    metal_relit = metal_res["relit_srgb"]
    mae_relit = np.mean(np.abs(cpu_relit - metal_relit))
    assert mae_relit < 0.005, f"Relit sRGB MAE exceeded threshold: {mae_relit:.6f}"


def test_cpu_metal_hybrid_direct_plus_ibl_parity(synthetic_scene_fixtures):
    """Verifies CPU–Metal numerical parity for combined Direct Area Light + IBL."""
    f = synthetic_scene_fixtures
    mat = MaterialData.plastic()
    scene = create_test_scene(material=mat, env_intensity=1.0, env_rot=30.0, add_lights=4)

    cpu_backend = CPURenderBackend()
    metal_backend = MetalRenderBackend()

    cpu_res = cpu_backend.render(
        scene=scene,
        image_orig_srgb=f["image_orig"],
        depth_map=f["depth_map"],
        normals_map=f["normals_map"],
        fg_mask=f["fg_mask"],
        quality=RenderQuality.PREVIEW
    )

    metal_res = metal_backend.render(
        scene=scene,
        image_orig_srgb=f["image_orig"],
        depth_map=f["depth_map"],
        normals_map=f["normals_map"],
        fg_mask=f["fg_mask"],
        quality=RenderQuality.PREVIEW
    )

    cpu_relit = cpu_res["relit_srgb"]
    metal_relit = metal_res["relit_srgb"]
    mae_relit = np.mean(np.abs(cpu_relit - metal_relit))
    mae_irr = np.mean(np.abs(cpu_res["direct_irradiance"] - metal_res["direct_irradiance"]))
    mae_spec = np.mean(np.abs(cpu_res["specular_radiance"] - metal_res["specular_radiance"]))
    mae_vis = np.mean(np.abs(cpu_res["direct_visibility"] - metal_res["direct_visibility"]))
    print(f"\n[HYBRID] IRR MAE: {mae_irr:.6f}, SPEC MAE: {mae_spec:.6f}, VIS MAE: {mae_vis:.6f}, RELIT MAE: {mae_relit:.6f}")
    assert mae_relit < 0.005, f"Hybrid Relit sRGB MAE exceeded threshold: {mae_relit:.6f}"
