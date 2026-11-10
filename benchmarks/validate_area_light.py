"""
RELIGHT STUDIO — RS-SPIKE-3B: AREA LIGHT & ILLUMINATION FIDELITY VALIDATION
===========================================================================
Workstream B Verification Suite:
  1. Stratified Monte Carlo Convergence (4, 16, 64, 256 samples vs 1024-sample reference)
  2. Inverse-Square Law (1/d^2) Radiometric Attenuation Consistency
  3. Radiant Power (Flux) vs Radiance Dimension Scaling Consistency
  4. Kelvin Blackbody Color Temperature Verification (2000K - 10000K)
  5. Penumbra Width Geometric Scaling (Emitter Size & Distance)
"""

import math
import json
import os
import numpy as np
from studio3a.lighting import RectangularAreaLight, kelvin_to_linear_rgb
from studio3a.scene import EnergyConvention, StudioScene, CameraData, ProxyType, ReceiverType, RenderQuality
from studio3a.geometry import OrientedBoundingBox, GroundPlaneReceiver
from studio3a.shadows import ShadowEngine
from studio3a.renderer import RenderBackend as CPURenderBackend
from metal2.renderer import MetalRenderBackend


def test_stratified_mc_convergence():
    """Evaluates convergence rate of stratified area light sampling against 1024-sample baseline."""
    light = RectangularAreaLight(
        position=(0.0, 2.0, 0.0),
        rotation_euler=(-90.0, 0.0, 0.0), # pointing down along -Y
        width=0.6,
        height=0.6,
        intensity=10.0
    )
    
    # Ground surface patch at y = 0.0, normal = [0, 1, 0]
    X, Z = np.meshgrid(np.linspace(-1.0, 1.0, 50), np.linspace(-1.0, 1.0, 50))
    H, W = X.shape
    surf_pos = np.stack([X, np.zeros_like(X), Z], axis=-1).astype(np.float32)
    surf_norm = np.zeros_like(surf_pos)
    surf_norm[..., 1] = 1.0
    
    # Reference at 1024 samples
    irr_ref = light.evaluate_unshadowed_irradiance(surf_pos, surf_norm, n_samples=1024)
    
    results = {}
    for n in [4, 16, 64, 256]:
        irr_n = light.evaluate_unshadowed_irradiance(surf_pos, surf_norm, n_samples=n)
        mae = float(np.mean(np.abs(irr_n - irr_ref)))
        rmse = float(np.sqrt(np.mean((irr_n - irr_ref)**2)))
        max_err = float(np.max(np.abs(irr_n - irr_ref)))
        results[n] = {"mae": mae, "rmse": rmse, "max_err": max_err}
        
    return results


def test_inverse_square_falloff():
    """Verifies that irradiance follows 1/d^2 law at increasing distances along optical axis."""
    light = RectangularAreaLight(
        position=(0.0, 0.0, 0.0),
        rotation_euler=(0.0, 0.0, 0.0), # normal = [0, 0, -1]
        width=0.1,
        height=0.1,
        intensity=10.0,
        energy_convention=EnergyConvention.FIXED_RADIANCE
    )
    
    distances = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]
    irradiances = []
    
    for d in distances:
        p = np.array([[[0.0, 0.0, -d]]], dtype=np.float32)
        n = np.array([[[0.0, 0.0, 1.0]]], dtype=np.float32)
        irr = light.evaluate_unshadowed_irradiance(p, n, n_samples=64)[0, 0, 0]
        irradiances.append(float(irr))
        
    # Check E(d) * d^2 constancy (for small emitter, should approach constant)
    e_d2 = [float(irr * (d**2)) for irr, d in zip(irradiances, distances)]
    # As d increases from 1.0 to 5.0, variation in E*d^2 should be < 2%
    rel_dev_far = abs(e_d2[-1] - e_d2[1]) / e_d2[1]
    
    return {
        "distances": distances,
        "irradiances": irradiances,
        "e_d2_products": e_d2,
        "relative_deviation_far": float(rel_dev_far)
    }


def test_energy_convention_scaling():
    """Verifies radiant power (flux) vs radiance scaling when light size is varied."""
    base_dim = 0.2
    scaled_dim = 0.8 # 4x dimension -> 16x area
    
    # 1. FIXED_POWER convention: total flux Phi is held constant
    lp_small = RectangularAreaLight(width=base_dim, height=base_dim, intensity=10.0, energy_convention=EnergyConvention.FIXED_POWER)
    lp_large = RectangularAreaLight(width=scaled_dim, height=scaled_dim, intensity=10.0, energy_convention=EnergyConvention.FIXED_POWER)
    
    # Distant receiver point along axis (d = 3.0m >> light size)
    p = np.array([[[0.0, 0.0, -3.0]]], dtype=np.float32)
    n = np.array([[[0.0, 0.0, 1.0]]], dtype=np.float32)
    
    irr_p_small = float(lp_small.evaluate_unshadowed_irradiance(p, n, n_samples=64)[0, 0, 0])
    irr_p_large = float(lp_large.evaluate_unshadowed_irradiance(p, n, n_samples=64)[0, 0, 0])
    power_ratio = irr_p_large / max(irr_p_small, 1e-6)
    
    # 2. FIXED_RADIANCE convention: surface radiance Le is held constant
    lr_small = RectangularAreaLight(width=base_dim, height=base_dim, intensity=10.0, energy_convention=EnergyConvention.FIXED_RADIANCE)
    lr_large = RectangularAreaLight(width=scaled_dim, height=scaled_dim, intensity=10.0, energy_convention=EnergyConvention.FIXED_RADIANCE)
    
    irr_r_small = float(lr_small.evaluate_unshadowed_irradiance(p, n, n_samples=64)[0, 0, 0])
    irr_r_large = float(lr_large.evaluate_unshadowed_irradiance(p, n, n_samples=64)[0, 0, 0])
    radiance_ratio = irr_r_large / max(irr_r_small, 1e-6)
    expected_radiance_ratio = (scaled_dim / base_dim)**2 # 16.0
    
    return {
        "fixed_power_ratio": power_ratio, # Should be ~1.0
        "fixed_radiance_ratio": radiance_ratio, # Should be ~16.0
        "expected_radiance_ratio": expected_radiance_ratio
    }


def test_kelvin_blackbody_table():
    """Generates blackbody color temperature spectrum and verifies Planckian locus monotonic shifts."""
    temperatures = [2000, 2700, 3200, 4000, 5000, 5600, 6500, 8000, 10000]
    table = []
    
    for K in temperatures:
        rgb = kelvin_to_linear_rgb(float(K))
        table.append({
            "kelvin": K,
            "R": round(float(rgb[0]), 4),
            "G": round(float(rgb[1]), 4),
            "B": round(float(rgb[2]), 4),
            "R_to_B_ratio": round(float(rgb[0] / max(rgb[2], 1e-6)), 4)
        })
        
    # Check monotonicity: R/B ratio must strictly decrease as temperature increases
    r_b_ratios = [entry["R_to_B_ratio"] for entry in table]
    is_monotonic = all(x > y for x, y in zip(r_b_ratios[:-1], r_b_ratios[1:]))
    
    return {
        "table": table,
        "is_r_b_monotonic_decreasing": is_monotonic
    }


def test_penumbra_width_scaling():
    """
    Measures soft shadow penumbra width across varying emitter sizes and distances.
    Analytical optical geometry:
      w_penumbra = s_emitter * (d_receiver / d_occluder)
    """
    # Occluder at y = 1.0 (thin box proxy), Receiver ground at y = 0.0 -> d_receiver = 1.0m
    # Light at y = 3.0 -> d_occluder = 2.0m -> Ratio (d_rec / d_occ) = 1.0 / 2.0 = 0.5
    # Therefore, theoretical penumbra width = 0.5 * emitter_width
    proxy = OrientedBoundingBox(position=(0.0, 1.0, 0.0), half_extents=(0.2, 0.05, 0.2))
    receiver = GroundPlaneReceiver(ground_y=0.0)
    shadow_engine = ShadowEngine(proxy=proxy, receiver=receiver)
    
    # 1D line of receiver points along X at y = 0.0, z = 0.0
    x_coords = np.linspace(-1.0, 1.0, 400, dtype=np.float32)
    surf_pos = np.stack([x_coords, np.zeros_like(x_coords), np.zeros_like(x_coords)], axis=-1)[:, None, :]
    surf_norm = np.zeros_like(surf_pos)
    surf_norm[..., 1] = 1.0
    
    widths_to_test = [0.2, 0.4, 0.8]
    scaling_data = []
    
    for w in widths_to_test:
        light = RectangularAreaLight(
            position=(0.0, 3.0, 0.0),
            rotation_euler=(-90.0, 0.0, 0.0),
            width=w,
            height=w,
            intensity=10.0
        )
        
        vis = shadow_engine.compute_direct_visibility(
            surface_pos=surf_pos,
            surface_norm=surf_norm,
            light=light,
            n_samples=64,
            seed=42
        )[:, 0]
        
        # Penumbra is region between V = 0.10 and V = 0.90
        in_penumbra = (vis >= 0.10) & (vis <= 0.90)
        if np.any(in_penumbra):
            # Left penumbra edge
            left_half = x_coords < 0.0
            left_pen = in_penumbra & left_half
            if np.any(left_pen):
                x_left_pen = x_coords[left_pen]
                measured_width = float(np.max(x_left_pen) - np.min(x_left_pen))
            else:
                measured_width = 0.0
        else:
            measured_width = 0.0
            
        theoretical_width = 0.5 * w
        scaling_data.append({
            "emitter_width": w,
            "theoretical_penumbra_width": theoretical_width,
            "measured_penumbra_width": round(measured_width, 4),
            "ratio_measured_to_theoretical": round(measured_width / max(theoretical_width, 1e-4), 3)
        })
        
    return scaling_data


def run_all_area_light_validations():
    print("="*80)
    print("RS-SPIKE-3B: AREA LIGHT & ILLUMINATION FIDELITY VALIDATION")
    print("="*80)
    
    print("\n1. Running Stratified Monte Carlo Convergence Analysis...")
    mc_results = test_stratified_mc_convergence()
    for n, res in mc_results.items():
        print(f"  N = {n:3d} samples: MAE = {res['mae']:.6f}, RMSE = {res['rmse']:.6f}, Max Err = {res['max_err']:.6f}")
        
    print("\n2. Running Inverse-Square Law (1/d^2) Verification...")
    inv_sq = test_inverse_square_falloff()
    print(f"  Distances evaluated: {inv_sq['distances']}")
    print(f"  E * d^2 Products:    {[round(p, 4) for p in inv_sq['e_d2_products']]}")
    print(f"  Relative Deviation (d=1.0m to 5.0m): {inv_sq['relative_deviation_far']*100:.3f}%")
    
    print("\n3. Running Energy Convention Scaling Verification...")
    ec = test_energy_convention_scaling()
    print(f"  Fixed Power (Flux) Ratio (4x dimension change):    {ec['fixed_power_ratio']:.4f} (Target: ~1.0000)")
    print(f"  Fixed Radiance Ratio (4x dimension change):        {ec['fixed_radiance_ratio']:.4f} (Target: 16.0000)")
    
    print("\n4. Running Kelvin Blackbody Table Monotonicity Check...")
    kelvin_data = test_kelvin_blackbody_table()
    print(f"  Monotonic R/B decrease from 2000K to 10000K: {kelvin_data['is_r_b_monotonic_decreasing']}")
    for row in kelvin_data['table']:
        print(f"    {row['kelvin']:5d}K -> RGB=({row['R']:.3f}, {row['G']:.3f}, {row['B']:.3f}) | R/B Ratio={row['R_to_B_ratio']:.3f}")
        
    print("\n5. Running Penumbra Width vs Geometry Scaling...")
    penumbra_data = test_penumbra_width_scaling()
    for p in penumbra_data:
        print(f"  Emitter W={p['emitter_width']:.2f}m: Theo Width={p['theoretical_penumbra_width']:.3f}m, Measured={p['measured_penumbra_width']:.3f}m (Ratio: {p['ratio_measured_to_theoretical']})")
        
    summary = {
        "stratified_mc_convergence": mc_results,
        "inverse_square_law": inv_sq,
        "energy_convention_scaling": ec,
        "kelvin_blackbody": kelvin_data,
        "penumbra_scaling": penumbra_data
    }
    
    out_path = "docs/RS-SPIKE-3B/area_light_validation_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[SAVED] Area light validation results -> {out_path}")


if __name__ == "__main__":
    run_all_area_light_validations()
