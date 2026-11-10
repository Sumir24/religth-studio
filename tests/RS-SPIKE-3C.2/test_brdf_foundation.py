"""
Unit Tests for Cook-Torrance BRDF Foundation
Relight Studio — RS-SPIKE-3C.2
"""

import numpy as np
import pytest
from studio3a.brdf import (
    distribution_ggx,
    fresnel_schlick,
    visibility_smith_ggx_correlated,
    cook_torrance_specular_brdf,
    evaluate_diffuse_specular_brdf,
    roughness_to_alpha,
    MIN_ROUGHNESS
)


def test_ggx_distribution_properties():
    """Validates GGX NDF at normal incidence and off-axis."""
    alpha = 0.25
    # Normal incidence: n . h = 1.0 -> D = alpha^2 / (pi * (alpha^2)^2) = 1 / (pi * alpha^2)
    expected_peak = 1.0 / (np.pi * alpha * alpha)
    nh_normal = np.array([1.0])
    d_normal = distribution_ggx(nh_normal, alpha)
    assert np.isclose(d_normal[0], expected_peak, rtol=1e-5)

    # Off-axis: n . h = 0.0 -> D = alpha^2 / pi
    nh_zero = np.array([0.0])
    d_zero = distribution_ggx(nh_zero, alpha)
    assert np.isclose(d_zero[0], (alpha * alpha) / np.pi, rtol=1e-5)

    # Monotonic decrease with angle
    angles = np.linspace(1.0, 0.0, 50)
    d_vals = distribution_ggx(angles, alpha)
    assert np.all(np.diff(d_vals) <= 1e-6), "GGX distribution must decrease monotonically as angle increases."


def test_fresnel_schlick_properties():
    """Validates Schlick Fresnel at normal incidence and grazing angle."""
    f0 = 0.04
    # Normal incidence: v . h = 1.0 -> F = F0
    vh_one = np.array([1.0])
    f_one = fresnel_schlick(vh_one, f0)
    assert np.isclose(f_one[0], f0, rtol=1e-5)

    # Grazing angle: v . h = 0.0 -> F = 1.0
    vh_zero = np.array([0.0])
    f_zero = fresnel_schlick(vh_zero, f0)
    assert np.isclose(f_zero[0], 1.0, rtol=1e-5)

    # RGB F0 support
    f0_rgb = np.array([1.0, 0.71, 0.29])  # Gold
    f_rgb_one = fresnel_schlick(vh_one, f0_rgb)
    assert np.allclose(f_rgb_one[0], f0_rgb, rtol=1e-5)
    f_rgb_zero = fresnel_schlick(vh_zero, f0_rgb)
    assert np.allclose(f_rgb_zero[0], [1.0, 1.0, 1.0], rtol=1e-5)


def test_helmholtz_reciprocity():
    """
    Verifies Helmholtz Reciprocity: f_r(l, v) == f_r(v, l).
    This is a fundamental physical law of light transport for symmetric surfaces.
    """
    n = np.array([0.0, 1.0, 0.0])
    l = np.array([0.5, 0.7071, 0.5])
    l = l / np.linalg.norm(l)
    v = np.array([-0.3, 0.8, 0.52])
    v = v / np.linalg.norm(v)

    roughnesses = [0.05, 0.1, 0.3, 0.5, 0.8, 1.0]
    f0 = 0.04

    for r in roughnesses:
        brdf_lv = cook_torrance_specular_brdf(n, l, v, r, f0)
        brdf_vl = cook_torrance_specular_brdf(n, v, l, r, f0)
        assert np.isclose(brdf_lv, brdf_vl, rtol=1e-5), f"Reciprocity violated at roughness={r}"


def test_backfacing_and_grazing_cutoff():
    """Verifies that light or viewer below horizon produces exactly zero reflection."""
    n = np.array([0.0, 1.0, 0.0])
    # Light below horizon: n . l < 0
    l_below = np.array([0.5, -0.2, 0.5])
    l_below = l_below / np.linalg.norm(l_below)
    v = np.array([0.0, 1.0, 0.0])

    brdf_below = cook_torrance_specular_brdf(n, l_below, v, 0.3, 0.04)
    assert brdf_below == 0.0, "Reflection must be 0 when light is below horizon"

    # Viewer below horizon: n . v < 0
    l = np.array([0.0, 1.0, 0.0])
    v_below = np.array([0.5, -0.5, 0.0])
    v_below = v_below / np.linalg.norm(v_below)
    brdf_v_below = cook_torrance_specular_brdf(n, l, v_below, 0.3, 0.04)
    assert brdf_v_below == 0.0, "Reflection must be 0 when viewer is below horizon"


def test_roughness_clamping_and_non_negativity():
    """Verifies that extreme roughness (0.0 and 1.0) does not produce NaNs or Infs."""
    n = np.array([0.0, 1.0, 0.0])
    l = np.array([0.0, 1.0, 0.0])
    v = np.array([0.0, 1.0, 0.0])

    # Zero roughness clamped to safe minimum
    brdf_zero = cook_torrance_specular_brdf(n, l, v, 0.0, 0.04)
    assert not np.isnan(brdf_zero)
    assert not np.isinf(brdf_zero)
    assert brdf_zero > 0.0

    # Roughness = 1.0
    brdf_one = cook_torrance_specular_brdf(n, l, v, 1.0, 0.04)
    assert not np.isnan(brdf_one)
    assert not np.isinf(brdf_one)
    assert brdf_one > 0.0


def test_energy_conserving_diffuse_specular_split():
    """Verifies that diffuse + specular does not fabricate energy for metals vs dielectrics."""
    n = np.array([0.0, 1.0, 0.0])
    l = np.array([0.0, 1.0, 0.0])
    v = np.array([0.0, 1.0, 0.0])
    albedo = np.array([0.8, 0.8, 0.8])

    # Pure metal: metallic=1.0 -> f_diffuse must be exactly 0.0
    f_diff_metal, f_spec_metal = evaluate_diffuse_specular_brdf(
        n, l, v, albedo, roughness=0.2, metallic=1.0, specular_f0=0.04
    )
    assert np.allclose(f_diff_metal, 0.0), "Pure metals must have 0 diffuse reflection."
    assert np.all(f_spec_metal > 0.0), "Pure metals must have specular reflection."

    # Pure dielectric: metallic=0.0 -> f_diffuse is present, modulated by (1 - F)
    f_diff_dielectric, f_spec_dielectric = evaluate_diffuse_specular_brdf(
        n, l, v, albedo, roughness=0.2, metallic=0.0, specular_f0=0.04
    )
    assert np.all(f_diff_dielectric > 0.0)
    assert np.all(f_spec_dielectric > 0.0)
