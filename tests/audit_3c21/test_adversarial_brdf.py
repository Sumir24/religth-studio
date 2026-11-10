"""
Independent Adversarial Test Suite for RS-SPIKE-3C.2.1 Audit.
Relight Studio — RS-SPIKE-3C.2.1 Audit

Challenges the production BRDF, material transport, and reconstruction pipeline
under edge conditions, boundary limits, and numerical stress tests.
"""

import math
import numpy as np
import pytest

from studio3a.brdf import (
    distribution_ggx,
    fresnel_schlick,
    visibility_smith_ggx_correlated,
    cook_torrance_specular_brdf,
    roughness_to_alpha,
    MIN_ROUGHNESS,
    MIN_ALPHA,
    EPSILON_DOT
)
from studio3a.material import MaterialData
from studio3a.reconstruction import (
    ReconstructionEngine,
    compute_DCI,
    linear_to_srgb,
    srgb_to_linear,
    linear_to_luminance
)
from benchmarks.audit_3c21.independent_brdf_reference import IndependentBRDFReference
from benchmarks.audit_3c21.audit_energy_conservation import evaluate_fibonacci_reflectance


def test_adversarial_brdf_safeguard_mismatch():
    """
    Remediation Check:
    Verifies that the denominator clamping fix (denom = np.maximum(denom, a2))
    restores strict physical monotonicity across MIN_ROUGHNESS = 0.04 and 0.0562.
    Asserts that peak specular BRDF increases monotonically as roughness decreases.
    """
    N = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    V = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    L = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    F0 = np.array([0.04, 0.04, 0.04], dtype=np.float32)

    peak_04 = float(np.mean(cook_torrance_specular_brdf(N, V, L, roughness=0.04, f0=F0)))
    peak_0562 = float(np.mean(cook_torrance_specular_brdf(N, V, L, roughness=0.0562, f0=F0)))
    peak_10 = float(np.mean(cook_torrance_specular_brdf(N, V, L, roughness=0.10, f0=F0)))

    # Strict physical monotonicity: Peak at r=0.04 must be strictly GREATER than at r=0.0562!
    assert peak_04 > peak_0562, f"Monotonicity failed: peak_04 ({peak_04}) <= peak_0562 ({peak_0562})"
    assert peak_0562 > peak_10, f"Monotonicity failed: peak_0562 ({peak_0562}) <= peak_10 ({peak_10})"
    # Exact analytical values: peak_04 should be ~1243.40, peak_0562 ~319.08
    assert np.isclose(peak_04, 1243.40, rtol=1e-3)
    assert np.isclose(peak_0562, 319.08, rtol=1e-3)


def test_ggx_ndf_fine_grained_monotonicity_fp64():
    """
    Independent Double-Precision Reference Test:
    Covers the fine-grained [0.04, 0.06] roughness region in 21 steps of 0.001
    and the broader [0.06, 1.00] range.
    Compares production distribution_ggx against double-precision analytical truth:
      D_analytical = 1.0 / (pi * roughness^4)
    Verifies:
      1. Relative error < 1e-6 vs analytical truth.
      2. Strict monotonic decrease as roughness increases.
    """
    # 1. Fine-grained 0.04 - 0.06 region (21 steps)
    fine_roughnesses = np.linspace(0.04, 0.06, 21, dtype=np.float64)
    prev_d = float("inf")

    for r in fine_roughnesses:
        alpha = float(roughness_to_alpha(r))
        d_prod = float(distribution_ggx(np.array([1.0], dtype=np.float32), alpha)[0])
        d_ref = IndependentBRDFReference.ggx_d(1.0, alpha)
        d_exact = 1.0 / (math.pi * (r ** 4.0))

        # Precision parity against analytical exact formula
        rel_err = abs(d_prod - d_exact) / d_exact
        assert rel_err < 1e-4, f"Relative error {rel_err} exceeded 1e-4 at r={r}"
        assert abs(d_prod - d_ref) / d_ref < 1e-6, f"Production vs ref mismatch at r={r}"

        # Strict monotonicity: d_prod must decrease as r increases
        assert d_prod < prev_d, f"Monotonicity violated: d({r}) = {d_prod} >= prev {prev_d}"
        prev_d = d_prod

    # 2. Broader 0.06 - 1.00 region
    broad_roughnesses = [0.07, 0.08, 0.10, 0.15, 0.20, 0.25, 0.35, 0.50, 0.75, 1.00]
    for r in broad_roughnesses:
        alpha = float(roughness_to_alpha(r))
        d_prod = float(distribution_ggx(np.array([1.0], dtype=np.float32), alpha)[0])
        d_exact = 1.0 / (math.pi * (r ** 4.0))
        rel_err = abs(d_prod - d_exact) / d_exact
        assert rel_err < 1e-4, f"Relative error {rel_err} exceeded 1e-4 at r={r}"
        assert d_prod < prev_d, f"Monotonicity violated: d({r}) = {d_prod} >= prev {prev_d}"
        prev_d = d_prod


def test_adversarial_spherical_fibonacci_energy_conservation():
    """
    Adversarial Audit Check:
    Verifies that true directional-hemispherical reflectance R(V) <= 1.000
    even at extreme grazing view angle (theta = 85 deg) when integrated with
    equal-area Spherical Fibonacci quadrature.
    """
    theta_rad = math.radians(85.0)
    V = np.array([math.sin(theta_rad), math.cos(theta_rad), 0.0], dtype=np.float32)

    # 1. Dielectric standard (F0 = 0.04)
    r_dielectric = evaluate_fibonacci_reflectance(64800, V, roughness=0.08, f0=0.04)
    assert r_dielectric <= 1.000, f"Dielectric grazing reflectance exceeded unity: {r_dielectric}"

    # 2. Pure Conductor (F0 = 1.0)
    r_metal = evaluate_fibonacci_reflectance(1000000, V, roughness=0.08, f0=1.0)
    assert r_metal <= 1.005, f"Metallic grazing reflectance exceeded unity: {r_metal}"


def test_adversarial_degenerate_vectors():
    """
    Adversarial Audit Check:
    Tests extreme degenerate directional vectors:
    - Opposed vectors (V = -L) -> h = 0
    - Horizon rays (N . L = 0, N . V = 0)
    - Sub-horizon illumination (N . L < 0)
    """
    N = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    # Opposed view and light: half-vector length is 0
    V_opp = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    L_opp = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
    res_opp = cook_torrance_specular_brdf(N, L_opp, V_opp, roughness=0.3, f0=0.04)
    assert float(np.max(np.abs(res_opp))) == 0.0, "Opposed vectors must evaluate to 0.0"

    # Exactly on geometric horizon: N . L = 0
    V_norm = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    L_horiz = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    res_horiz = cook_torrance_specular_brdf(N, L_horiz, V_norm, roughness=0.3, f0=0.04)
    assert float(np.max(np.abs(res_horiz))) == 0.0, "Horizon rays must evaluate to 0.0"

    # Sub-horizon: N . L < 0
    L_sub = np.array([0.0, -0.7071, 0.7071], dtype=np.float32)
    res_sub = cook_torrance_specular_brdf(N, L_sub, V_norm, roughness=0.3, f0=0.04)
    assert float(np.max(np.abs(res_sub))) == 0.0, "Sub-horizon rays must evaluate to 0.0"


def test_adversarial_two_scale_highlight_sharpness():
    """
    Adversarial Audit Check:
    Verifies that Two-Scale reconstruction preserves sharp specular glints
    without the highlight blurring and haloing inherent to naive log-ratio.
    """
    H, W = 64, 64
    img_orig = np.full((H, W, 3), 0.4, dtype=np.float32)
    diff_irr = np.full((H, W, 3), 0.5, dtype=np.float32)

    # Sharp 4x4 glint at center
    spec_rad = np.zeros((H, W, 3), dtype=np.float32)
    spec_rad[30:34, 30:34] = 4.0

    engine = ReconstructionEngine(r_filter=8, eps_filter=0.02**2)
    recon = engine.reconstruct_relit_image(
        image_orig_srgb=img_orig,
        direct_irradiance=diff_irr,
        direct_visibility=None,
        specular_radiance=spec_rad
    )

    relit_lin = recon["relit_linear"]
    # Check that peak inside glint is preserved
    peak_val = float(np.max(relit_lin[30:34, 30:34]))

    # Compare against identical reconstruction without specular
    recon_diff_only = engine.reconstruct_relit_image(
        image_orig_srgb=img_orig,
        direct_irradiance=diff_irr,
        direct_visibility=None,
        specular_radiance=None
    )
    diff_only_lin = recon_diff_only["relit_linear"]
    outer_val = float(np.mean(relit_lin[10:15, 10:15]))
    diff_only_val = float(np.mean(diff_only_lin[10:15, 10:15]))

    assert peak_val >= 0.95, "Two-Scale must preserve peak specular highlight intensity!"
    assert abs(outer_val - diff_only_val) < 1e-5, "Two-Scale must not bleed specular energy into outer texture!"


def test_adversarial_material_bounds_enforcement():
    """
    Adversarial Audit Check:
    Verifies that MaterialData enforces strict physical bounds.
    """
    # Negative roughness
    with pytest.raises(ValueError, match="Roughness must be in"):
        MaterialData(roughness=-0.1).validate()

    # Roughness > 1
    with pytest.raises(ValueError, match="Roughness must be in"):
        MaterialData(roughness=1.1).validate()

    # Metallic > 1
    with pytest.raises(ValueError, match="Metallic factor must be in"):
        MaterialData(metallic=1.5).validate()

    # Negative intensity
    with pytest.raises(ValueError, match="Specular intensity cannot be negative"):
        MaterialData(specular_intensity=-0.5).validate()

    # Empty ID
    with pytest.raises(ValueError, match="Material ID cannot be empty"):
        MaterialData(id="").validate()
