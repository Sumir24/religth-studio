"""
Area-Light Specular Integration Investigation
Relight Studio — RS-SPIKE-3C.2

Compares:
  1. High-sample-count reference (1024 stratified samples)
  2. Stochastic Stratified sampling (4 samples [Preview], 32 samples [Final])
  3. Karis Most Representative Point (MRP) approximation
"""

import time
import json
import numpy as np
from typing import Tuple, Dict, Any

from studio3a.brdf import (
    cook_torrance_specular_brdf,
    roughness_to_alpha,
    safe_normalize,
    clamp_dot
)


def sample_rectangular_light_grid(
    light_pos: np.ndarray,
    light_rot_deg: np.ndarray,
    width: float,
    height: float,
    n_samples: int
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Generates stratified sample points and normal on rectangular emitter."""
    grid_size = max(1, int(np.floor(np.sqrt(n_samples))))
    total_pts = grid_size * grid_size

    # Local coordinates [-w/2, w/2] x [-h/2, h/2]
    u = (np.arange(grid_size) + 0.5) / grid_size - 0.5
    v = (np.arange(grid_size) + 0.5) / grid_size - 0.5
    uu, vv = np.meshgrid(u * width, v * height)
    local_pts = np.stack([uu.flatten(), vv.flatten(), np.zeros(total_pts)], axis=-1)

    # Rotation matrix (Euler ZYX)
    rx, ry, rz = np.radians(light_rot_deg)
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    R_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    R_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    R_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    R = R_z @ R_y @ R_x

    world_pts = (R @ local_pts.T).T + light_pos
    light_normal = R @ np.array([0.0, 0.0, -1.0])  # Emits along -Z local
    light_normal = light_normal / np.linalg.norm(light_normal)
    area = width * height
    return world_pts, light_normal, area


def evaluate_specular_stochastic(
    surface_pos: np.ndarray,
    surface_norm: np.ndarray,
    view_dir: np.ndarray,
    world_pts: np.ndarray,
    light_normal: np.ndarray,
    area: float,
    emission_radiance: float,
    roughness: float,
    f0: float
) -> float:
    """Stochastically integrates specular radiance across light sample points."""
    n_pts = len(world_pts)
    weight = area / n_pts
    total_spec = 0.0

    for pt in world_pts:
        diff = pt - surface_pos
        dist_sq = max(np.sum(diff * diff), 1e-4)
        dist = np.sqrt(dist_sq)
        l = diff / dist

        # Emitter cosine
        cos_e = max(0.0, np.dot(light_normal, -l))
        n_dot_l = max(0.0, np.dot(surface_norm, l))
        if cos_e <= 0.0 or n_dot_l <= 0.0:
            continue

        # Solid angle differential: d_omega = (area / N) * cos_e / dist_sq
        d_omega = (weight * cos_e) / dist_sq

        # Specular BRDF
        f_spec = cook_torrance_specular_brdf(surface_norm, l, view_dir, roughness, f0)
        total_spec += emission_radiance * f_spec * n_dot_l * d_omega

    return float(total_spec)


def evaluate_specular_mrp(
    surface_pos: np.ndarray,
    surface_norm: np.ndarray,
    view_dir: np.ndarray,
    light_pos: np.ndarray,
    light_rot_deg: np.ndarray,
    width: float,
    height: float,
    emission_radiance: float,
    roughness: float,
    f0: float
) -> float:
    """
    Karis Most Representative Point (MRP) approximation:
    Finds closest point on rectangular light to reflection ray and broadens roughness.
    """
    # Reflection ray r = 2 * (n . v) * n - v
    n_dot_v = max(0.0, np.dot(surface_norm, view_dir))
    if n_dot_v <= 0.0:
        return 0.0
    r = 2.0 * n_dot_v * surface_norm - view_dir
    r = r / np.linalg.norm(r)

    # Light coordinate system
    rx, ry, rz = np.radians(light_rot_deg)
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    R = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ \
        np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]) @ \
        np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    
    right = R @ np.array([1.0, 0.0, 0.0])
    up = R @ np.array([0.0, 1.0, 0.0])
    forward = R @ np.array([0.0, 0.0, -1.0])

    # Ray-plane intersection: (p - light_pos) . forward = 0
    diff = light_pos - surface_pos
    denom = np.dot(r, forward)
    if abs(denom) > 1e-5:
        t = np.dot(diff, forward) / denom
        if t > 0.0:
            hit = surface_pos + t * r
            # Project hit into light local coords
            rel = hit - light_pos
            u = np.clip(np.dot(rel, right), -width / 2.0, width / 2.0)
            v = np.clip(np.dot(rel, up), -height / 2.0, height / 2.0)
            closest_pt = light_pos + u * right + v * up
        else:
            closest_pt = light_pos
    else:
        closest_pt = light_pos

    l_diff = closest_pt - surface_pos
    dist_sq = max(np.sum(l_diff * l_diff), 1e-4)
    dist = np.sqrt(dist_sq)
    l = l_diff / dist

    cos_e = max(0.0, np.dot(forward, -l))
    n_dot_l = max(0.0, np.dot(surface_norm, l))
    if cos_e <= 0.0 or n_dot_l <= 0.0:
        return 0.0

    # Solid angle of light
    area = width * height
    solid_angle = (area * cos_e) / dist_sq

    # Roughness expansion: alpha' = clamp(alpha + light_radius / (2 * dist), alpha, 1.0)
    light_radius = 0.5 * np.sqrt(width * width + height * height)
    alpha = roughness_to_alpha(roughness)
    alpha_prime = np.clip(alpha + light_radius / (2.0 * dist), alpha, 1.0)
    r_expanded = np.sqrt(alpha_prime)

    f_spec = cook_torrance_specular_brdf(surface_norm, l, view_dir, r_expanded, f0)
    return float(emission_radiance * f_spec * n_dot_l * solid_angle)


def run_investigation():
    print("=" * 80)
    print("RS-SPIKE-3C.2: AREA-LIGHT SPECULAR INTEGRATION INVESTIGATION")
    print("=" * 80)

    # Scene setup
    light_pos = np.array([1.2, 1.8, 1.5])
    light_rot = np.array([-35.0, 30.0, 0.0])
    width, height = 0.60, 0.60
    emission = 1.0
    f0 = 0.04

    # Setup light samples
    pts_1024, norm_1024, area = sample_rectangular_light_grid(light_pos, light_rot, width, height, 1024)
    pts_32, norm_32, _ = sample_rectangular_light_grid(light_pos, light_rot, width, height, 32)
    pts_4, norm_4, _ = sample_rectangular_light_grid(light_pos, light_rot, width, height, 4)

    # Grid of surface points on sphere / proxy
    n_eval = 100
    phi = np.linspace(-0.5, 0.5, 10)
    theta = np.linspace(0.1, 0.8, 10)
    pp, tt = np.meshgrid(phi, theta)
    normals = np.stack([np.sin(pp)*np.cos(tt), np.sin(tt), np.cos(pp)*np.cos(tt)], axis=-1).reshape(-1, 3)
    normals = normals / np.linalg.norm(normals, axis=-1, keepdims=True)
    positions = normals * 0.35  # proxy radius 0.35m
    cam_pos = np.array([0.0, 1.2, 2.5])

    roughnesses = [0.05, 0.10, 0.25, 0.50, 0.75, 1.00]
    results = {}

    for r in roughnesses:
        ref_vals = []
        stoch32_vals = []
        stoch4_vals = []
        mrp_vals = []

        t0 = time.perf_counter()
        for pos, norm in zip(positions, normals):
            v = cam_pos - pos
            v = v / np.linalg.norm(v)

            ref = evaluate_specular_stochastic(pos, norm, v, pts_1024, norm_1024, area, emission, r, f0)
            s32 = evaluate_specular_stochastic(pos, norm, v, pts_32, norm_32, area, emission, r, f0)
            s4 = evaluate_specular_stochastic(pos, norm, v, pts_4, norm_4, area, emission, r, f0)
            mrp = evaluate_specular_mrp(pos, norm, v, light_pos, light_rot, width, height, emission, r, f0)

            ref_vals.append(ref)
            stoch32_vals.append(s32)
            stoch4_vals.append(s4)
            mrp_vals.append(mrp)

        ref_arr = np.array(ref_vals)
        s32_arr = np.array(stoch32_vals)
        s4_arr = np.array(stoch4_vals)
        mrp_arr = np.array(mrp_vals)

        # MAE and relative error vs reference
        mae_s32 = float(np.mean(np.abs(s32_arr - ref_arr)))
        mae_s4 = float(np.mean(np.abs(s4_arr - ref_arr)))
        mae_mrp = float(np.mean(np.abs(mrp_arr - ref_arr)))

        # PSNR vs ref
        max_val = max(float(np.max(ref_arr)), 1e-4)
        mse_s32 = max(float(np.mean((s32_arr - ref_arr)**2)), 1e-10)
        mse_s4 = max(float(np.mean((s4_arr - ref_arr)**2)), 1e-10)
        mse_mrp = max(float(np.mean((mrp_arr - ref_arr)**2)), 1e-10)

        psnr_s32 = 10.0 * np.log10(max_val**2 / mse_s32)
        psnr_s4 = 10.0 * np.log10(max_val**2 / mse_s4)
        psnr_mrp = 10.0 * np.log10(max_val**2 / mse_mrp)

        results[f"roughness_{r}"] = {
            "roughness": r,
            "ref_peak": float(np.max(ref_arr)),
            "stoch_32": {"mae": mae_s32, "psnr_db": float(psnr_s32)},
            "stoch_4": {"mae": mae_s4, "psnr_db": float(psnr_s4)},
            "mrp": {"mae": mae_mrp, "psnr_db": float(psnr_mrp)}
        }

        print(f"Roughness {r:.2f}: Ref Peak={np.max(ref_arr):.4f}")
        print(f"  Stoch-32 (Final):   MAE={mae_s32:.6f}, PSNR={psnr_s32:.1f} dB")
        print(f"  Stoch-4  (Preview): MAE={mae_s4:.6f}, PSNR={psnr_s4:.1f} dB")
        print(f"  Karis MRP:          MAE={mae_mrp:.6f}, PSNR={psnr_mrp:.1f} dB")

    with open("metal2/benchmark_results/area_specular_investigation.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved investigation to metal2/benchmark_results/area_specular_investigation.json")


if __name__ == "__main__":
    run_investigation()
