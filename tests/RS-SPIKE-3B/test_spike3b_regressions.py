"""
Regression Test Suite for RS-SPIKE-3B: Geometric Lighting Fidelity & Scene Interaction
"""

import math
import numpy as np
import pytest

from studio3a.scene import StudioScene, ProxyType, ReceiverType, RenderQuality, EnergyConvention
from studio3a.geometry import SuperquadricEllipsoid, OrientedBoundingBox, LowPolyMesh
from studio3a.lighting import RectangularAreaLight, kelvin_to_linear_rgb
from studio3a.renderer import RenderBackend as CPURenderBackend
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture
from metal2.shadow_evaluation import compute_soft_iou, compute_continuous_sde


def test_superquadric_normalized_metric_stability():
    """Verifies that normalized metric G(p) avoids float overflow on sharp exponent objects."""
    sq = SuperquadricEllipsoid(
        position=(0.0, 0.35, 0.0),
        radii=(0.20, 0.40, 0.20),
        sq_exponents=(0.1, 0.1) # extremely sharp box-like
    )
    # Point at 5x radius
    p_far = np.array([[[1.0, 2.0, 1.0]]], dtype=np.float32)
    g_val = sq.eval_inside_outside(p_far)
    assert np.isfinite(g_val[0, 0])
    assert g_val[0, 0] > 0.0
    assert g_val[0, 0] < 50.0 # Well bounded, no 10^7 blowup


def test_area_light_inverse_square_and_energy_conventions():
    """Verifies 1/d^2 attenuation and FIXED_POWER vs FIXED_RADIANCE conventions."""
    l_rad = RectangularAreaLight(position=(0.0, 0.0, 0.0), rotation_euler=(0.0, 0.0, 0.0), width=0.1, height=0.1, intensity=10.0, energy_convention=EnergyConvention.FIXED_RADIANCE)
    l_pow = RectangularAreaLight(position=(0.0, 0.0, 0.0), rotation_euler=(0.0, 0.0, 0.0), width=0.1, height=0.1, intensity=10.0, energy_convention=EnergyConvention.FIXED_POWER)
    l_pow_large = RectangularAreaLight(position=(0.0, 0.0, 0.0), rotation_euler=(0.0, 0.0, 0.0), width=0.4, height=0.4, intensity=10.0, energy_convention=EnergyConvention.FIXED_POWER)
    
    p1 = np.array([[[0.0, 0.0, -1.0]]], dtype=np.float32)
    p2 = np.array([[[0.0, 0.0, -2.0]]], dtype=np.float32)
    n = np.array([[[0.0, 0.0, 1.0]]], dtype=np.float32)
    
    irr1 = l_rad.evaluate_unshadowed_irradiance(p1, n, n_samples=32)[0, 0, 0]
    irr2 = l_rad.evaluate_unshadowed_irradiance(p2, n, n_samples=32)[0, 0, 0]
    ratio = irr1 / max(irr2, 1e-6)
    assert abs(ratio - 4.0) < 0.20
    
    irr_p1 = l_pow.evaluate_unshadowed_irradiance(p2, n, n_samples=32)[0, 0, 0]
    irr_p2 = l_pow_large.evaluate_unshadowed_irradiance(p2, n, n_samples=32)[0, 0, 0]
    assert abs(irr_p1 - irr_p2) / max(irr_p1, 1e-6) < 0.05


def test_metal_bitwise_zero_mutation():
    """Verifies exact bitwise immutability on protected regions."""
    metal_b = MetalRenderBackend()
    scene, img, depth, normals, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE)
    
    H, W = fg.shape
    prot_mask = np.zeros((H, W), dtype=bool)
    prot_mask[:, :W // 2] = True
    
    res = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.PREVIEW, protected_mask=prot_mask)
    max_diff = float(np.max(np.abs(res["relit_srgb"][prot_mask] - img[prot_mask])))
    assert max_diff == 0.0


def test_canonical_superquadric_parity():
    """Verifies that M2_03 cosmetic bottle achieves >= 0.93 Soft IoU on GPU."""
    cpu_b = CPURenderBackend()
    metal_b = MetalRenderBackend()
    scene, img, depth, normals, fg, rec, _ = generate_scene_fixture("cat2_cosmetic_bottle", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA)
    
    scene.render_settings.final_samples = 32
    r_cpu = cpu_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)
    r_metal = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)
    
    soft_iou = compute_soft_iou(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
    sde = compute_continuous_sde(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
    irr_mae = float(np.mean(np.abs(r_metal["direct_irradiance"][fg] - r_cpu["direct_irradiance"][fg])))
    
    assert soft_iou >= 0.93
    assert sde <= 1.0
    assert irr_mae <= 0.001
