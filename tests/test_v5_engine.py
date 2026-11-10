"""
Test Suite for Relight Studio Engine v5 (Master Photometric PBR Relighter)
Verifies:
1. Polar coordinates and distance normalization (|v| == 1.0, hemisphere correctness).
2. Screen-Space Ambient Occlusion (HBAO) bounded in [0, 1] with crevice darkening.
3. Exposure compensation and soft-clamp bounds (no NaN, no Inf, smooth saturation).
4. Albedo regularization and edge preservation via masked guided filter.
5. End-to-end real photograph relighting (Nike sneaker) with texture preservation.
"""

import math
import numpy as np
import pytest
from PIL import Image

from engine.relighter_v5 import (
    polar, compute_hbao, soft_clamp_log, masked_guided, decompose,
    prepare_scene, relight_scene, L, Params, srgb_to_linear, linear_to_srgb
)
from studio3a.reconstruction import compute_DCI


def test_v5_polar_coordinates_and_distance_normalization():
    """Verifies that polar(az, el) produces unit vectors with correct geometric signs."""
    test_angles = [
        (0.0, 0.0),    # front
        (90.0, 0.0),   # right key
        (-90.0, 0.0),  # left key
        (0.0, 90.0),   # top
        (0.0, -45.0),  # below
        (45.0, 45.0),  # top-right 45
    ]
    for az, el in test_angles:
        v = polar(az, el)
        norm = np.linalg.norm(v)
        assert abs(norm - 1.0) < 1e-5, f"Vector for az={az}, el={el} not unit length: norm={norm}"
        assert not np.isnan(v).any()
        assert not np.isinf(v).any()

    # Specific geometric directional assertions
    v_right = polar(90.0, 0.0)
    assert v_right[0] > 0.99, f"Expected +X for az=90, got {v_right}"

    v_left = polar(-90.0, 0.0)
    assert v_left[0] < -0.99, f"Expected -X for az=-90, got {v_left}"

    v_top = polar(0.0, 90.0)
    assert v_top[2] > 0.99, f"Expected +Z for el=90, got {v_top}"


def test_v5_hbao_crevice_occlusion():
    """Verifies HBAO crevice darkening and flat plane neutrality."""
    p = Params()
    H, W = 64, 64
    mask = np.ones((H, W), dtype=bool)

    # 1. Perfectly flat surface -> HBAO should be unoccluded (~1.0)
    h_flat = np.full((H, W), 0.5, dtype=np.float32)
    ao_flat = compute_hbao(h_flat, mask, p)
    assert np.all(ao_flat >= 0.0) and np.all(ao_flat <= 1.0)
    assert np.mean(ao_flat) > 0.90, f"Expected flat plane AO ~ 1.0, got {np.mean(ao_flat)}"

    # 2. Surface with a deep crevice in the middle
    h_crevice = np.full((H, W), 0.5, dtype=np.float32)
    h_crevice[:, 30:34] = 0.0 # Deep canyon / tread trench
    ao_crevice = compute_hbao(h_crevice, mask, p)
    assert np.all(ao_crevice >= 0.0) and np.all(ao_crevice <= 1.0)
    assert np.mean(ao_crevice[:, 31:33]) < np.mean(ao_flat), "Crevice should be darkened by HBAO"


def test_v5_exposure_compensation_bounds():
    """Verifies that soft_clamp_log prevents exponential blowout across extreme exposure deltas."""
    lo, hi = 0.25, 4.0
    x_extremes = np.array([-10.0, -5.0, -1.0, 0.0, 1.0, 5.0, 10.0], dtype=np.float32)

    clamped = soft_clamp_log(x_extremes, lo, hi)
    assert np.all(np.isfinite(clamped)), "Soft clamp produced non-finite values"
    assert np.all(clamped >= -lo * 1.001) and np.all(clamped <= hi * 1.001)
    # Monotonicity check
    assert np.all(np.diff(clamped) >= 0), "Soft clamp must be monotonic"


def test_v5_albedo_regularization_edge_preservation():
    """Verifies that masked guided filter preserves sharp edges without leakage."""
    H, W = 64, 64
    mask = np.ones((H, W), dtype=bool)
    # Create step edge image
    guide = np.zeros((H, W), dtype=np.float32)
    guide[:, 32:] = 1.0

    src = guide.copy()
    filtered = masked_guided(guide, src, mask, radius=8, eps=1e-3)
    assert np.all(np.isfinite(filtered))

    # Center step should remain sharp (edge preservation)
    step_jump = filtered[32, 33] - filtered[32, 30]
    assert step_jump > 0.85, f"Edge was blurred excessively: step_jump={step_jump}"


def test_v5_real_photographs():
    """Verifies v5 pipeline on real photograph of Nike sneaker."""
    img_pil = Image.open("demo_output/nike_sample.jpg").convert("RGB")
    img_np = np.array(img_pil, dtype=np.float32) / 255.0

    scene = prepare_scene(img_np)
    assert scene is not None
    assert scene.mask.any()

    # Shade with warm key and cool rim lights
    lights = [
        L("directional", az=45.0, el=30.0, intensity=1.5, kelvin=3200.0),
        L("directional", az=-135.0, el=20.0, intensity=0.8, kelvin=7500.0)
    ]
    p = Params()
    res = relight_scene(scene, lights, p=p)

    relit_srgb = res.relit_srgb
    assert relit_srgb.shape == img_np.shape
    assert not np.isnan(relit_srgb).any()
    assert not np.isinf(relit_srgb).any()
    assert relit_srgb.min() >= 0.0 and relit_srgb.max() <= 1.0

    # High-frequency detail conservation
    dci = compute_DCI(img_np, relit_srgb, mask=scene.mask)
    assert dci >= 0.85, f"Expected DCI >= 0.85 on real photo, got {dci:.4f}"
    print(f"\n[PASS] v5 Real Photo Relight: Foreground DCI = {dci:.4f}")
