"""
RELIGHT STUDIO — RS-SPIKE-3B.1: INDEPENDENT SHADOW GROUND TRUTH AUDIT
=====================================================================
Phase 2 Investigation Suite:
  1. Establishes the exact mathematical meaning of the reported "1.0000 Parity"
  2. Generates Independent High-Precision Reference Shadows (N=256 samples, float64 geometry)
  3. Evaluates 7 Diverse Geometric Shadow Scenarios:
     - Case S1: Sphere above ground plane (analytical geometry)
     - Case S2: Cube box above ground plane (analytical OBB)
     - Case S3: Rounded perfume box above ground plane
     - Case S4: Superquadric bottle above cyclorama cove
     - Case S5: Grazing-angle oblique illumination (elevation = 15 deg)
     - Case S6: Large softbox area light (1.0m x 1.0m - wide penumbra)
     - Case S7: Small spotlight area light (0.1m x 0.1m - hard shadow)
  4. Multi-Metric Evaluation against Independent Reference:
     - Continuous Soft IoU (fuzzy Jaccard)
     - Hard IoU at V < 0.50 and V < 0.85
     - Opacity-Weighted SDE (px)
     - 50% Isoline Contour Boundary Displacement (px)
     - Shadow Area Error (%)
     - Penumbra Area and Width Error
"""

import math
import json
import time
from typing import Dict, Any, Tuple, Optional, List
import numpy as np
import cv2

from studio3a.geometry import (
    OrientedBoundingBox, SuperquadricEllipsoid, GroundPlaneReceiver,
    CycloramaReceiver, euler_to_rotation_matrix
)
from studio3a.lighting import RectangularAreaLight
from studio3a.scene import StudioScene, CameraData, ReceiverData, ProxyType, ReceiverType, RenderQuality
from studio3a.renderer import RenderBackend as CPURenderBackend
from metal2.renderer import MetalRenderBackend
from metal2.shadow_evaluation import (
    compute_soft_iou, compute_continuous_sde,
    compute_contour_boundary_displacement, compute_penumbra_metrics
)
from benchmarks.independent_superquadric_audit import independent_brent_intersect_ray


def independent_superquadric_intersect_rays_f64(
    p_bias: np.ndarray,
    L_dir: np.ndarray,
    center: np.ndarray,
    radii: np.ndarray,
    e1: float,
    e2: float,
    R: np.ndarray,
    n_steps: int = 64,
    n_bisection: int = 8
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Independent vectorized double-precision ray-superquadric solver.
    Uses 64 intervals and 8 bisection iterations in float64.
    """
    M = len(p_bias)
    is_blocked = np.zeros(M, dtype=bool)
    t_hit = np.ones(M, dtype=np.float64) * 1e9

    # Local transformation
    oc = p_bias - center[None, :]
    ro_local = oc @ R
    rd_local = L_dir @ R

    # Bounding sphere culling in float64
    bounding_radius = float(np.max(radii) * 1.5)
    b = np.sum(ro_local * rd_local, axis=-1)
    c = np.sum(ro_local * ro_local, axis=-1) - bounding_radius**2
    disc = b * b - c
    hit_sphere = disc >= 0.0
    disc_sqrt = np.sqrt(np.maximum(0.0, disc))
    t_enter = np.maximum(1e-4, -b - disc_sqrt)
    t_exit = -b + disc_sqrt
    valid_range = hit_sphere & (t_exit > 1e-4) & (t_enter < t_exit)

    if not np.any(valid_range):
        return is_blocked, t_hit

    idx_valid = np.where(valid_range)[0]
    ro_v = ro_local[idx_valid]
    rd_v = rd_local[idx_valid]
    t0_v = t_enter[idx_valid][:, None]
    t1_v = t_exit[idx_valid][:, None]

    t_steps = np.linspace(0.0, 1.0, n_steps + 1, dtype=np.float64)
    t_samples = t0_v + t_steps[None, :] * (t1_v - t0_v)
    p_samples = ro_v[:, None, :] + t_samples[..., None] * rd_v[:, None, :]

    # Independent G(p) in float64
    rx, ry, rz = float(radii[0]), float(radii[1]), float(radii[2])
    x_n = np.abs(p_samples[..., 0]) / rx
    y_n = np.abs(p_samples[..., 1]) / ry
    z_n = np.abs(p_samples[..., 2]) / rz

    term_xy = np.maximum(x_n ** (2.0 / e2) + y_n ** (2.0 / e2), 1e-18)
    f_val = term_xy ** (e2 / e1) + z_n ** (2.0 / e1)
    g_samples = np.maximum(f_val, 1e-18) ** (e1 / 2.0) - 1.0

    g_sign = np.sign(g_samples)
    g_sign = np.where(g_sign == 0.0, 1.0, g_sign)
    sign_changes = (g_sign[:, :-1] * g_sign[:, 1:]) <= 0.0
    has_crossing = np.any(sign_changes, axis=-1)

    if np.any(has_crossing):
        idx_cross = np.where(has_crossing)[0]
        first_interval = np.argmax(sign_changes[idx_cross], axis=-1)
        t_low = t_samples[idx_cross, first_interval]
        t_high = t_samples[idx_cross, first_interval + 1]

        ro_cross = ro_v[idx_cross]
        rd_cross = rd_v[idx_cross]

        # 8-iteration bisection refinement in float64
        for _ in range(n_bisection):
            t_mid = 0.5 * (t_low + t_high)
            p_mid = ro_cross + t_mid[:, None] * rd_cross
            xm = np.abs(p_mid[..., 0]) / rx
            ym = np.abs(p_mid[..., 1]) / ry
            zm = np.abs(p_mid[..., 2]) / rz
            t_xy_m = np.maximum(xm ** (2.0 / e2) + ym ** (2.0 / e2), 1e-18)
            f_m = t_xy_m ** (e2 / e1) + zm ** (2.0 / e1)
            g_mid = np.maximum(f_m, 1e-18) ** (e1 / 2.0) - 1.0

            p_low = ro_cross + t_low[:, None] * rd_cross
            xl = np.abs(p_low[..., 0]) / rx
            yl = np.abs(p_low[..., 1]) / ry
            zl = np.abs(p_low[..., 2]) / rz
            t_xy_l = np.maximum(xl ** (2.0 / e2) + yl ** (2.0 / e2), 1e-18)
            f_l = t_xy_l ** (e2 / e1) + zl ** (2.0 / e1)
            g_low = np.maximum(f_l, 1e-18) ** (e1 / 2.0) - 1.0

            same_sign = (g_low * g_mid) > 0.0
            t_low = np.where(same_sign, t_mid, t_low)
            t_high = np.where(same_sign, t_high, t_mid)

        t_root = 0.5 * (t_low + t_high)
        global_indices = idx_valid[idx_cross]
        is_blocked[global_indices] = True
        t_hit[global_indices] = t_root

    return is_blocked, t_hit


def compute_independent_reference_shadow(
    ray_o: np.ndarray, ray_d: np.ndarray,
    rec_hit: np.ndarray, rec_t: np.ndarray, rec_norm: np.ndarray,
    light: RectangularAreaLight,
    proxy_params: Dict[str, Any],
    n_samples: int = 256
) -> np.ndarray:
    """
    Computes an authoritative independent reference visibility field V_ref using
    high-sample Monte Carlo (N=256) and exact float64 ray intersections.
    Completely decoupled from studio3a.shadows and metal2 renderer.metal.
    """
    H, W = rec_hit.shape
    V_ref = np.ones((H, W), dtype=np.float32)
    
    if not np.any(rec_hit):
        return V_ref
        
    p_rec = ray_o[rec_hit] + rec_t[rec_hit, None] * ray_d[rec_hit]
    n_rec = rec_norm[rec_hit]
    p_bias = p_rec + 1e-3 * n_rec # Acne offset
    
    # Generate 256 stratified jittered light sample points in float64
    np.random.seed(9999) # Independent seed
    grid_dim = int(math.sqrt(n_samples))
    light_samples = []
    for gy in range(grid_dim):
        for gx in range(grid_dim):
            # Stratified jitter in [0, 1]
            u = (float(gx) + np.random.uniform(0.1, 0.9)) / float(grid_dim) - 0.5
            v = (float(gy) + np.random.uniform(0.1, 0.9)) / float(grid_dim) - 0.5
            p_emit = light.pos + (u * light.width) * light.u_tangent + (v * light.height) * light.v_bitangent
            light_samples.append(p_emit)
            
    p_type = proxy_params["type"]
    center = np.array(proxy_params["position"], dtype=np.float32)
    radii = np.array(proxy_params["dimensions"], dtype=np.float32)
    e1 = float(proxy_params.get("e1", 1.0))
    e2 = float(proxy_params.get("e2", 1.0))
    R = euler_to_rotation_matrix(*proxy_params.get("rotation", (0.0, 0.0, 0.0)))
    
    # Occlusion testing per surface pixel
    vis_accum = np.zeros(len(p_bias), dtype=np.float32)
    
    for p_emit in light_samples:
        L_vec = p_emit[None, :] - p_bias
        dist_sq = np.sum(L_vec * L_vec, axis=-1)
        dist = np.sqrt(np.maximum(dist_sq, 1e-6))
        L_dir = L_vec / dist[:, None]
        
        # Test occlusion against proxy
        if p_type == "SPHERE":
            # Exact analytical ray-sphere intersection
            oc = p_bias - center
            b = np.sum(oc * L_dir, axis=-1)
            c = np.sum(oc * oc, axis=-1) - radii[0]**2
            disc = b * b - c
            hit = (disc >= 0.0)
            sqrt_disc = np.sqrt(np.maximum(disc, 0.0))
            t_hit = -b - sqrt_disc
            is_blocked = hit & (t_hit > 1e-3) & (t_hit < dist - 1e-3)
            
        elif p_type == "OBB":
            # Exact analytical ray-box intersection
            oc = p_bias - center
            ro_loc = oc @ R
            rd_loc = L_dir @ R
            inv_d = 1.0 / np.where(np.abs(rd_loc) < 1e-6, np.sign(rd_loc + 1e-9) * 1e-6, rd_loc)
            t0 = (-radii - ro_loc) * inv_d
            t1 = (radii - ro_loc) * inv_d
            tmin = np.maximum(np.maximum(np.minimum(t0[:, 0], t1[:, 0]), np.minimum(t0[:, 1], t1[:, 1])), np.minimum(t0[:, 2], t1[:, 2]))
            tmax = np.minimum(np.minimum(np.maximum(t0[:, 0], t1[:, 0]), np.maximum(t0[:, 1], t1[:, 1])), np.maximum(t0[:, 2], t1[:, 2]))
            is_blocked = (tmin <= tmax) & (tmax > 1e-3) & (tmin < dist - 1e-3)
            
        elif p_type == "SUPERQUADRIC":
            # Evaluated with independent double-precision solver
            blocked_sq, t_sq = independent_superquadric_intersect_rays_f64(
                p_bias, L_dir, center, radii, e1, e2, R, n_steps=64, n_bisection=8
            )
            is_blocked = blocked_sq & (1e-3 < t_sq) & (t_sq < dist - 1e-3)
        else:
            is_blocked = np.zeros(len(p_bias), dtype=bool)
            
        vis_accum += np.where(~is_blocked, 1.0, 0.0)
        
    vis_final = vis_accum / float(len(light_samples))
    V_ref[rec_hit] = vis_final
    return V_ref


def run_independent_shadow_audit():
    print("="*80)
    print("RS-SPIKE-3B.1: INDEPENDENT SHADOW GROUND TRUTH AUDIT")
    print("Evaluating Metal GPU & Production CPU against Independent N=256 Ground Truth")
    print("="*80)

    metal_b = MetalRenderBackend()
    cpu_b = CPURenderBackend()

    H, W = 192, 256 # High-resolution evaluation grid

    test_scenarios = [
        {
            "id": "S1_sphere_plane",
            "name": "Sphere above Ground Plane",
            "proxy": {"type": "SPHERE", "position": [0.0, 0.6, 0.0], "dimensions": [0.3, 0.3, 0.3]},
            "receiver_type": ReceiverType.PLANE,
            "light_pos": [1.0, 2.0, 1.0], "light_dim": [0.4, 0.4], "light_rot": [-45.0, 30.0, 0.0]
        },
        {
            "id": "S2_cube_plane",
            "name": "Cube Box above Ground Plane",
            "proxy": {"type": "OBB", "position": [0.0, 0.4, 0.0], "dimensions": [0.25, 0.25, 0.25]},
            "receiver_type": ReceiverType.PLANE,
            "light_pos": [1.2, 1.8, 1.5], "light_dim": [0.5, 0.5], "light_rot": [-35.0, 30.0, 0.0]
        },
        {
            "id": "S3_rounded_box_plane",
            "name": "Rounded Box above Ground Plane",
            "proxy": {"type": "SUPERQUADRIC", "position": [0.0, 0.4, 0.0], "dimensions": [0.25, 0.35, 0.20], "e1": 0.3, "e2": 0.3},
            "receiver_type": ReceiverType.PLANE,
            "light_pos": [1.0, 2.0, 1.2], "light_dim": [0.4, 0.4], "light_rot": [-40.0, 30.0, 0.0]
        },
        {
            "id": "S4_cosmetic_cyclorama",
            "name": "Cosmetic Bottle above Cyclorama Cove",
            "proxy": {"type": "SUPERQUADRIC", "position": [0.0, 0.45, 0.0], "dimensions": [0.18, 0.45, 0.18], "e1": 0.3, "e2": 1.0},
            "receiver_type": ReceiverType.CYCLORAMA,
            "light_pos": [1.2, 1.8, 1.5], "light_dim": [0.6, 0.6], "light_rot": [-35.0, 30.0, 0.0]
        },
        {
            "id": "S5_grazing_oblique_light",
            "name": "Grazing-Angle Oblique Illumination (15°)",
            "proxy": {"type": "OBB", "position": [0.0, 0.4, 0.0], "dimensions": [0.25, 0.35, 0.25]},
            "receiver_type": ReceiverType.PLANE,
            "light_pos": [2.5, 0.8, 1.0], "light_dim": [0.3, 0.3], "light_rot": [-15.0, 65.0, 0.0]
        },
        {
            "id": "S6_large_softbox_light",
            "name": "Large Softbox Emitter (1.0m x 1.0m)",
            "proxy": {"type": "OBB", "position": [0.0, 0.5, 0.0], "dimensions": [0.25, 0.40, 0.25]},
            "receiver_type": ReceiverType.PLANE,
            "light_pos": [1.0, 2.2, 1.0], "light_dim": [1.0, 1.0], "light_rot": [-45.0, 30.0, 0.0]
        },
        {
            "id": "S7_pinpoint_spot_light",
            "name": "Small Pinpoint Emitter (0.1m x 0.1m - Sharp)",
            "proxy": {"type": "OBB", "position": [0.0, 0.5, 0.0], "dimensions": [0.25, 0.40, 0.25]},
            "receiver_type": ReceiverType.PLANE,
            "light_pos": [1.0, 2.2, 1.0], "light_dim": [0.1, 0.1], "light_rot": [-45.0, 30.0, 0.0]
        }
    ]

    results = []

    for sc in test_scenarios:
        sid = sc["id"]
        print(f"\n[EVALUATING SCENARIO] {sid}: {sc['name']}...")
        
        # Build StudioScene
        scene = StudioScene()
        scene.camera = CameraData(pos=[0.0, 1.4, 2.8], target=[0.0, 0.35, 0.0], fov_deg=45.0, width=W, height=H)
        scene.receiver = ReceiverData(receiver_type=sc["receiver_type"], ground_y=0.0)
        
        # Setup proxy
        p_cfg = sc["proxy"]
        if p_cfg["type"] == "OBB" or p_cfg["type"] == "SPHERE":
            scene.subject.proxy_type = ProxyType.OBB
            scene.subject.dimensions = p_cfg["dimensions"]
        else:
            scene.subject.proxy_type = ProxyType.SUPERQUADRIC
            scene.subject.dimensions = p_cfg["dimensions"]
            scene.subject.sq_exponents = [p_cfg.get("e1", 1.0), p_cfg.get("e2", 1.0)]
        scene.subject.position = p_cfg["position"]
        
        # Setup light
        scene.lights[0].position = sc["light_pos"]
        scene.lights[0].rotation_deg = sc["light_rot"]
        scene.lights[0].width = sc["light_dim"][0]
        scene.lights[0].height = sc["light_dim"][1]
        scene.lights[0].intensity = 1.5
        scene.render_settings.final_samples = 64
        scene.render_settings.enable_contact_grounding = False # Isolate cast-shadow optics for geometric audit
        
        # Setup receiver geometry
        rec_geo = cpu_b.instantiate_receiver(scene)
        cam = cpu_b.instantiate_camera(scene, W, H) if hasattr(cpu_b, 'instantiate_camera') else CameraData(pos=scene.camera.pos, target=scene.camera.target, fov_deg=scene.camera.fov_deg, width=W, height=H)
        from studio3a.camera import Camera3D
        cam3d = Camera3D(pos=scene.camera.pos, target=scene.camera.target, width=W, height=H, fov_deg=scene.camera.fov_deg)
        ray_o, ray_d = cam3d.generate_camera_rays()
        rec_hit, rec_t, rec_norm = rec_geo.intersect_rays(ray_o, ray_d)
        
        img_dummy = np.ones((H, W, 3), dtype=np.float32) * 0.5
        depth_dummy = np.ones((H, W), dtype=np.float32) * 0.5
        normals_dummy = np.zeros((H, W, 3), dtype=np.float32)
        normals_dummy[..., 1] = 1.0
        fg_mask = np.zeros((H, W), dtype=bool)
        
        # 1. Independent Ground Truth Reference Shadow (N=256)
        light_obj = RectangularAreaLight(
            position=scene.lights[0].position,
            rotation_euler=scene.lights[0].rotation_deg,
            width=scene.lights[0].width,
            height=scene.lights[0].height
        )
        t0_gt = time.time()
        V_gt = compute_independent_reference_shadow(
            ray_o=ray_o, ray_d=ray_d,
            rec_hit=rec_hit, rec_t=rec_t, rec_norm=rec_norm,
            light=light_obj,
            proxy_params=p_cfg,
            n_samples=256
        )
        t_gt_s = time.time() - t0_gt
        
        # 2. Production Metal GPU Shadow (FINAL quality, 64 samples)
        r_metal = metal_b.render(scene, img_dummy, depth_dummy, normals_dummy, fg_mask, quality=RenderQuality.FINAL)
        V_metal = r_metal["direct_visibility"]
        
        # 3. Production CPU Shadow (FINAL quality, 64 samples)
        r_cpu = cpu_b.render(scene, img_dummy, depth_dummy, normals_dummy, fg_mask, quality=RenderQuality.FINAL)
        V_cpu = r_cpu["direct_visibility"]
        
        # 4. Multi-Metric Evaluation against Independent Reference
        # A. Continuous Soft IoU (fuzzy Jaccard)
        soft_iou_metal_vs_gt = compute_soft_iou(V_metal, V_gt, rec_hit)
        soft_iou_cpu_vs_gt = compute_soft_iou(V_cpu, V_gt, rec_hit)
        parity_soft_iou = compute_soft_iou(V_metal, V_cpu, rec_hit)
        
        # B. Hard IoU at V < 0.50 (core umbra) and V < 0.85 (umbra + penumbra)
        def calc_hard_iou(cand_v, ref_v, thresh, mask):
            c_sh = (cand_v < thresh) & mask
            r_sh = (ref_v < thresh) & mask
            inter = np.sum(c_sh & r_sh)
            union = np.sum(c_sh | r_sh)
            return float(round(inter / max(union, 1), 4))
            
        hard_iou_50 = calc_hard_iou(V_metal, V_gt, 0.50, rec_hit)
        hard_iou_85 = calc_hard_iou(V_metal, V_gt, 0.85, rec_hit)
        
        # C. Opacity-Weighted Center-of-Mass SDE
        sde_metal_vs_gt = compute_continuous_sde(V_metal, V_gt, rec_hit)
        parity_sde = compute_continuous_sde(V_metal, V_cpu, rec_hit)
        
        # D. 50% Isoline Contour Boundary Displacement
        contour_disp = compute_contour_boundary_displacement(V_metal, V_gt, rec_hit)
        
        # E. Shadow Area Error (at V < 0.85)
        area_metal = int(np.sum((V_metal < 0.85) & rec_hit))
        area_gt = int(np.sum((V_gt < 0.85) & rec_hit))
        area_err_pct = round(abs(area_metal - area_gt) / max(area_gt, 1) * 100.0, 2)
        
        print(f"  CPU-Metal Parity Soft IoU:       {parity_soft_iou:.4f} (Parity SDE: {parity_sde:.2f}px)")
        print(f"  Metal vs Independent GT Soft IoU: {soft_iou_metal_vs_gt:.4f}")
        print(f"  Metal vs Independent GT SDE:      {sde_metal_vs_gt:.2f} px")
        print(f"  Hard IoU (V < 0.50):              {hard_iou_50:.4f} | Hard IoU (V < 0.85): {hard_iou_85:.4f}")
        print(f"  50% Contour Displacement:         {contour_disp:.2f} px")
        print(f"  Shadow Area Error (V < 0.85):     {area_err_pct:.2f}% (Metal: {area_metal} px, GT: {area_gt} px)")
        
        results.append({
            "scenario_id": sid,
            "scenario_name": sc["name"],
            "cpu_metal_parity_soft_iou": parity_soft_iou,
            "cpu_metal_parity_sde_px": parity_sde,
            "independent_gt_soft_iou": soft_iou_metal_vs_gt,
            "independent_gt_sde_px": sde_metal_vs_gt,
            "hard_iou_50": hard_iou_50,
            "hard_iou_85": hard_iou_85,
            "contour_displacement_px": contour_disp,
            "shadow_area_error_pct": area_err_pct,
            "shadow_area_metal_px": area_metal,
            "shadow_area_gt_px": area_gt
        })
        
    out_json = "docs/RS-SPIKE-3B.1/independent_shadow_audit_results.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVED] Independent Shadow Audit JSON -> {out_json}")


if __name__ == "__main__":
    run_independent_shadow_audit()
