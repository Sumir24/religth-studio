"""
RELIGHT STUDIO — RS-SPIKE-3C.0: REGRESSION & VERIFICATION TEST SUITE
=====================================================================
Rigorous Automated Regression Suite for Single-Light Pipeline Completion:
  1. Metal E.1 Guided-Filter Regularization & Numerical Parity vs CPU
  2. Exact Analytical Sphere Geometry & Shadow Area Parity
  3. Persistent Buffer Pool Zero-Allocation Invariant in Steady State
  4. Photographic Detail Conservation Index (DCI >= 0.8800 on Foreground)
  5. Exact Bitwise Immutability (0.0000000000) on Protected Regions
  6. Independent Shadow Metric Separation (Implementation Parity vs Geometric Accuracy)
"""

import os
import math
import numpy as np
import pytest
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, ProxyType, ReceiverType,
    EnergyConvention, RenderQuality
)
from studio3a.camera import Camera3D
from studio3a.geometry import SphereProxy, OrientedBoundingBox, SuperquadricEllipsoid
from studio3a.lighting import RectangularAreaLight
from studio3a.renderer import RenderBackend as CPURenderBackend
from studio3a.reconstruction import (
    compute_DCI, srgb_to_linear, linear_to_srgb, ReconstructionEngine
)
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture
from metal2.shadow_evaluation import compute_soft_iou, compute_continuous_sde


# ===========================================================================
# 1. DETAIL PRESERVATION & METAL E.1 REGULARIZATION
# ===========================================================================

def test_metal_e1_guided_filter_parity_vs_cpu():
    """
    Verifies that the 8-pass separable GPU Guided Filter in renderer.metal
    matches CPU ReconstructionEngine numerical output within tight float bounds.
    """
    scene, img_orig, depth, normals, fg_mask, rec_mask, _ = generate_scene_fixture(
        "cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE
    )
    scene.render_settings.final_samples = 32

    cpu_b = CPURenderBackend()
    metal_b = MetalRenderBackend()

    r_cpu = cpu_b.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.FINAL)
    r_metal = metal_b.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.FINAL)

    # Foreground difference between CPU and Metal relit images
    diff_fg = np.abs(r_cpu["relit_srgb"][fg_mask] - r_metal["relit_srgb"][fg_mask])
    mean_diff = float(np.mean(diff_fg))
    max_diff = float(np.max(diff_fg))

    assert mean_diff < 0.002, f"Mean diff too high: {mean_diff}"
    assert max_diff < 0.010, f"Max diff too high: {max_diff}"


def test_metal_e1_restores_foreground_dci_on_photograph():
    """
    Verifies that Metal GPU with E.1 Guided-Filter achieves Foreground DCI >= 0.95
    on Nike Sneaker plate (restoring fidelity from the audited 0.8282 failure).
    """
    img_pil = Image.open("demo_output/nike_sample.jpg").convert("RGB")
    img_np = np.array(img_pil, dtype=np.float32) / 255.0
    H, W = img_np.shape[:2]

    depth = np.array(Image.open("demo_output/nike_test/depth.png").convert("L"), dtype=np.float32) / 255.0
    raw_norm = np.array(Image.open("demo_output/nike_test/normals.png").convert("RGB"), dtype=np.float32) / 255.0 * 2.0 - 1.0
    n_len = np.clip(np.linalg.norm(raw_norm, axis=2, keepdims=True), 1e-4, None)
    norm = raw_norm / n_len

    gray = np.mean(img_np, axis=-1)
    fg_mask = gray < 0.92

    scene = StudioScene()
    scene.camera = CameraData(width=W, height=H)
    scene.lights[0].position = [-1.0, 1.5, 1.5]
    scene.lights[0].intensity = 3.0

    metal_b = MetalRenderBackend()
    res = metal_b.render(scene, img_np, depth, norm, fg_mask, quality=RenderQuality.FINAL)

    dci_fg = compute_DCI(img_np, res["relit_srgb"], mask=fg_mask)
    dci_whole = compute_DCI(img_np, res["relit_srgb"])

    assert dci_fg >= 0.95, f"Expected FG DCI >= 0.95 with E.1 active, got {dci_fg:.5f}"
    assert dci_whole >= 0.95, f"Expected Whole DCI >= 0.95, got {dci_whole:.5f}"


# ===========================================================================
# 2. EXACT ANALYTICAL SPHERE GEOMETRY
# ===========================================================================

def test_exact_sphere_analytical_intersection_and_normals():
    """Verifies that SphereProxy solves quadratic ray intersection exactly."""
    sphere = SphereProxy(position=(0.0, 0.35, 0.0), radius=0.35)

    # 1. Frontal center ray
    ro_center = np.array([[0.0, 0.35, 2.0]], dtype=np.float32)
    rd_center = np.array([[0.0, 0.0, -1.0]], dtype=np.float32)
    hit, t, n = sphere.intersect_rays(ro_center, rd_center)
    assert hit[0]
    assert abs(t[0] - (2.0 - 0.35)) < 1e-5
    assert np.allclose(n[0], [0.0, 0.0, 1.0], atol=1e-5)

    # 2. Tangent grazing ray (miss)
    ro_miss = np.array([[0.36, 0.35, 2.0]], dtype=np.float32)
    hit_m, _, _ = sphere.intersect_rays(ro_miss, rd_center)
    assert not hit_m[0]


def test_sphere_shadow_area_error_vs_analytical_truth():
    """
    Verifies that SphereProxy eliminates OBB approximation error,
    achieving shadow area error < 1.0% vs analytical truth (pi * r^2).
    """
    r = 0.35
    sphere = SphereProxy(position=(0.0, 0.35, 0.0), radius=r)
    obb = OrientedBoundingBox(position=(0.0, 0.35, 0.0), half_extents=(r, r, r))

    y_L = 3.0
    sin_th = r / (y_L - 0.35)
    tan_th = sin_th / math.sqrt(1.0 - sin_th**2)
    R_shadow = y_L * tan_th
    A_gt = math.pi * (R_shadow ** 2)

    N = 800
    xs = np.linspace(-1.0, 1.0, N)
    zs = np.linspace(-1.0, 1.0, N)
    X, Z = np.meshgrid(xs, zs)
    pixel_area = (xs[1] - xs[0]) * (zs[1] - zs[0])
    pts = np.stack([X, np.zeros_like(X), Z], axis=-1)

    light_pos = np.array([0.0, y_L, 0.0], dtype=np.float32)
    L_vec = light_pos[None, None, :] - pts
    dist = np.linalg.norm(L_vec, axis=-1)
    L_dir = L_vec / dist[..., None]

    hit_s, t_s, _ = sphere.intersect_rays(pts, L_dir)
    shadow_s = hit_s & (t_s > 1e-3) & (t_s < dist - 1e-3)
    A_sphere = np.sum(shadow_s) * pixel_area
    err_sphere = abs(A_sphere - A_gt) / A_gt * 100.0

    hit_o, t_o, _ = obb.intersect_rays(pts, L_dir)
    shadow_o = hit_o & (t_o > 1e-3) & (t_o < dist - 1e-3)
    A_obb = np.sum(shadow_o) * pixel_area
    err_obb = abs(A_obb - A_gt) / A_gt * 100.0

    assert err_sphere < 1.0, f"Sphere shadow area error must be < 1.0%, got {err_sphere:.3f}%"
    assert err_obb > 20.0, f"OBB error must be > 20%, got {err_obb:.3f}%"


def test_sphere_cpu_metal_parity():
    """Verifies that Metal GPU Sphere matches CPU reference (Soft IoU >= 0.93, SDE <= 1.0 px)."""
    scene, img, depth, normals, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.SPHERE, ReceiverType.PLANE)
    scene.render_settings.final_samples = 32

    cpu_b = CPURenderBackend()
    metal_b = MetalRenderBackend()

    r_cpu = cpu_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)
    r_metal = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)

    soft_iou = compute_soft_iou(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
    sde = compute_continuous_sde(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
    irr_mae = float(np.mean(np.abs(r_metal["direct_irradiance"][fg] - r_cpu["direct_irradiance"][fg])))

    assert soft_iou >= 0.93, f"Soft IoU was {soft_iou:.4f}"
    assert sde <= 1.0, f"SDE was {sde:.3f} px"
    assert irr_mae <= 0.001, f"Irradiance MAE was {irr_mae:.6f}"


# ===========================================================================
# 3. PERSISTENT BUFFER POOL & LATENCY INVARIANTS
# ===========================================================================

def test_persistent_buffer_pool_zero_allocations_in_steady_state():
    """Verifies that buffer pool reallocations drop to 0 in steady state."""
    metal_b = MetalRenderBackend()
    metal_b.bridge.reset_buffer_pool()

    H, W = 128, 128
    img = np.zeros((H, W, 3), dtype=np.float32)
    depth = np.zeros((H, W), dtype=np.float32)
    norm = np.zeros((H, W, 3), dtype=np.float32)
    fg = np.zeros((H, W), dtype=bool)

    scene = StudioScene()
    scene.camera.width = W
    scene.camera.height = H

    # Frame 1: Initial allocation
    metal_b.render(scene, img, depth, norm, fg)
    stats1 = metal_b.bridge.get_buffer_pool_stats()
    assert stats1["alloc_count"] == 1
    assert stats1["steady_frames"] == 0

    # Frames 2-10: Steady state
    for f in range(1, 10):
        metal_b.render(scene, img, depth, norm, fg)
        stats = metal_b.bridge.get_buffer_pool_stats()
        assert stats["alloc_count"] == 1, f"Pool reallocated on frame {f+1}!"
        assert stats["steady_frames"] == f


# ===========================================================================
# 4. EXACT BITWISE ZERO-MUTATION ON PROTECTED REGION
# ===========================================================================

def test_exact_bitwise_zero_mutation_with_e1():
    """Verifies that protected regions undergo strictly 0.0000000000 mutation with E.1 active."""
    metal_b = MetalRenderBackend()
    scene, img, depth, normals, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE)

    H, W = fg.shape
    prot_mask = np.zeros((H, W), dtype=bool)
    prot_mask[:, :W // 2] = True

    res = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL, protected_mask=prot_mask)
    max_mutation = float(np.max(np.abs(res["relit_srgb"][prot_mask] - img[prot_mask])))

    assert max_mutation == 0.0, f"Protected region mutated! Max difference = {max_mutation:.10e}"
