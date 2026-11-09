"""
RELIGHT STUDIO — RS-SPIKE-3A: EXPERIMENTAL VALIDATION & BENCHMARK HARNESS
========================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Strict Verification Mode: Executes quantitative benchmarks across 5 product categories:
  1. Perfume Box (OBB proxy on Plane and Cyclorama)
  2. Cylindrical Cosmetic Bottle (Superquadric proxy on Cyclorama)
  3. Sneaker (Procedural Footwear Hull Mesh proxy on Plane)
  4. Metallic Watch (Compact OBB / Cylinder proxy)
  5. Irregular Organic Object (Superquadric on Pedestal)
"""

from __future__ import annotations

import os
import time
import math
import json
import csv
from typing import Dict, Any, List, Tuple
import numpy as np
import cv2
from PIL import Image
from scipy.spatial.distance import cdist

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, ProxyType, ReceiverType,
    EnergyConvention, RenderQuality
)
from studio3a.camera import Camera3D
from studio3a.geometry import (
    OrientedBoundingBox, SuperquadricEllipsoid, LowPolyMesh,
    GroundPlaneReceiver, CycloramaReceiver
)
from studio3a.lighting import RectangularAreaLight
from studio3a.shadows import ShadowEngine
from studio3a.renderer import RenderBackend
from studio3a.workspace import render_virtual_studio_viewport
from studio3a.reconstruction import srgb_to_linear, linear_to_srgb


OUTPUT_DIR = "experiments/RS-SPIKE-3A"
BENCH_DIR = os.path.join(OUTPUT_DIR, "benchmark_results")
DIAG_DIR = os.path.join(OUTPUT_DIR, "diagnostic_outputs")
GT_DIR = os.path.join(OUTPUT_DIR, "ground_truth")

os.makedirs(BENCH_DIR, exist_ok=True)
os.makedirs(DIAG_DIR, exist_ok=True)
os.makedirs(GT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. METRIC EVALUATORS
# ---------------------------------------------------------------------------

def compute_SDE(V_cand: np.ndarray, V_gt: np.ndarray, receiver_mask: np.ndarray) -> float:
    """Shadow Distance Error: distance between cand and GT shadow centroids."""
    cand_shadow = (V_cand < 0.85) & receiver_mask
    gt_shadow = (V_gt < 0.85) & receiver_mask
    if not np.any(cand_shadow) or not np.any(gt_shadow):
        return 0.0 if (not np.any(cand_shadow) and not np.any(gt_shadow)) else 50.0
    cy_c, cx_c = np.mean(np.where(cand_shadow)[0]), np.mean(np.where(cand_shadow)[1])
    cy_g, cx_g = np.mean(np.where(gt_shadow)[0]), np.mean(np.where(gt_shadow)[1])
    return round(float(math.sqrt((cy_c - cy_g)**2 + (cx_c - cx_g)**2)), 2)


def compute_IoU(V_cand: np.ndarray, V_gt: np.ndarray, receiver_mask: np.ndarray) -> float:
    """Intersection over Union between cand and GT binary shadow masks."""
    cand_shadow = (V_cand < 0.85) & receiver_mask
    gt_shadow = (V_gt < 0.85) & receiver_mask
    if not np.any(gt_shadow):
        return 1.0 if not np.any(cand_shadow) else 0.0
    intersection = np.sum(cand_shadow & gt_shadow)
    union = np.sum(cand_shadow | gt_shadow)
    return round(float(intersection / max(union, 1)), 4)


def compute_SLR(V_cand: np.ndarray, cliff_mask: np.ndarray, V_gt: Optional[np.ndarray] = None) -> float:
    """Silhouette Leakage Rate: percentage of cliff edge pixels falsely shadowed."""
    if cliff_mask is None or not np.any(cliff_mask):
        return 0.0
    cliff_pts = cliff_mask
    cand_shadowed = (V_cand < 0.85) & cliff_pts
    if V_gt is not None:
        gt_lit = (V_gt >= 0.85) & cliff_pts
        leak_pts = cand_shadowed & gt_lit
        denom = max(np.sum(gt_lit), 1)
    else:
        leak_pts = cand_shadowed
        denom = max(np.sum(cliff_pts), 1)
    return round(float(100.0 * np.sum(leak_pts) / denom), 2)


def compute_CGS(V_direct: np.ndarray, contact_occlusion: np.ndarray, contact_mask: np.ndarray) -> float:
    """Contact Grounding Sharpness: minimum direct visibility at contact interface."""
    if contact_mask is None or not np.any(contact_mask):
        return 0.0
    val = float(np.min(V_direct[contact_mask] * contact_occlusion[contact_mask]))
    return round(val, 4)


def compute_DCI(img_orig: np.ndarray, img_relit: np.ndarray) -> float:
    """Detail Correlation Index: cosine similarity of high-frequency laplacian edges."""
    g_orig = cv2.Laplacian(cv2.cvtColor((img_orig*255).astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F)
    g_relit = cv2.Laplacian(cv2.cvtColor((img_relit*255).astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F)
    num = np.sum(g_orig * g_relit)
    den = math.sqrt(max(np.sum(g_orig**2), 1e-4) * max(np.sum(g_relit**2), 1e-4))
    return round(float(np.clip(num / den, 0.0, 1.0)), 4)


# ---------------------------------------------------------------------------
# 2. SYNTHETIC SCENE GENERATOR
# ---------------------------------------------------------------------------

def generate_synthetic_scene_fixture(
    category_id: str,
    proxy_type: ProxyType,
    receiver_type: ReceiverType,
    H: int = 256,
    W: int = 384
) -> Tuple[StudioScene, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generates synthetic ground-truth ray traced scene with exact 3D geometry.
    Returns: (scene, img_orig_srgb, depth_map, normals_map, fg_mask, V_gt)
    """
    scene = StudioScene()
    scene.camera = CameraData(pos=[0.0, 1.2, 2.5], target=[0.0, 0.35, 0.0], fov_deg=45.0, width=W, height=H)
    scene.receiver = ReceiverData(receiver_type=receiver_type, ground_y=0.0)
    scene.subject.proxy_type = proxy_type
    
    # Configure by category
    if category_id == "cat1_perfume_box":
        scene.subject.dimensions = [0.25, 0.40, 0.20]
        scene.subject.position = [0.0, 0.40, 0.0]
    elif category_id == "cat2_cosmetic_bottle":
        scene.subject.dimensions = [0.18, 0.45, 0.18]
        scene.subject.sq_exponents = [0.3, 1.0] # Rounded cylinder
        scene.subject.position = [0.0, 0.45, 0.0]
    elif category_id == "cat3_sneaker":
        scene.subject.dimensions = [0.35, 0.20, 0.45]
        scene.subject.position = [0.0, 0.15, 0.0]
    elif category_id == "cat4_metallic_watch":
        scene.subject.dimensions = [0.20, 0.10, 0.20]
        scene.subject.position = [0.0, 0.10, 0.0]
    elif category_id == "cat5_organic_object":
        scene.subject.dimensions = [0.30, 0.35, 0.30]
        scene.subject.sq_exponents = [1.5, 1.2]
        scene.subject.position = [0.0, 0.35, 0.0]

    # Setup 3D camera rays
    cam = Camera3D(pos=scene.camera.pos, target=scene.camera.target, width=W, height=H, fov_deg=scene.camera.fov_deg)
    ray_o, ray_d = cam.generate_camera_rays()
    
    backend = RenderBackend()
    proxy = backend.instantiate_proxy_geometry(scene)
    receiver = backend.instantiate_receiver(scene)
    
    hit_proxy, t_proxy, norm_proxy = proxy.intersect_rays(ray_o, ray_d)
    hit_rec, t_rec, norm_rec = receiver.intersect_rays(ray_o, ray_d)
    
    # Hit sorting
    fg_mask = hit_proxy & (t_proxy < t_rec)
    rec_mask = (~fg_mask) & hit_rec
    
    depth_map = np.zeros((H, W), dtype=np.float32)
    normals_map = np.zeros((H, W, 3), dtype=np.float32)
    surface_pos = np.zeros((H, W, 3), dtype=np.float32)
    
    # Camera space depth
    t_cam = np.where(fg_mask, t_proxy, np.where(rec_mask, t_rec, 5.0))
    cos_f = np.maximum(0.1, np.sum(ray_d * cam.forward, axis=-1))
    z_cam = t_cam * cos_f
    depth_map = np.clip((z_cam - 0.5) / 2.5, 0.0, 1.0).astype(np.float32)
    
    normals_map[fg_mask] = norm_proxy[fg_mask]
    normals_map[rec_mask] = norm_rec[rec_mask]
    surface_pos = ray_o + t_cam[..., None] * ray_d
    
    # Synthetic Base Image (Lambertian base shading under initial key)
    L_init = np.array([0.5, 0.8, 0.5], dtype=np.float32)
    L_init /= np.linalg.norm(L_init)
    diffuse = np.maximum(0.0, np.sum(normals_map * L_init, axis=-1))
    
    base_color = np.zeros((H, W, 3), dtype=np.float32)
    base_color[fg_mask] = np.array([0.80, 0.70, 0.60])
    base_color[rec_mask] = np.array([0.75, 0.75, 0.75])
    
    img_orig_srgb = np.clip(base_color * (0.2 + 0.8 * diffuse[..., None]), 0.0, 1.0)
    
    # Generate 3D Ground-Truth Direct Visibility using 64 Monte Carlo samples
    light_obj = RectangularAreaLight(
        position=scene.lights[0].position,
        rotation_euler=scene.lights[0].rotation_deg,
        width=scene.lights[0].width,
        height=scene.lights[0].height
    )
    shadow_engine = ShadowEngine(proxy=proxy, receiver=receiver)
    V_gt = shadow_engine.compute_direct_visibility(
        surface_pos=surface_pos,
        surface_norm=normals_map,
        light=light_obj,
        n_samples=64,
        seed=1337
    )
    
    return scene, img_orig_srgb, depth_map, normals_map, fg_mask, V_gt


# ---------------------------------------------------------------------------
# 3. EXPERIMENTAL BENCHMARK EXECUTION
# ---------------------------------------------------------------------------

def run_rs_spike_3a_benchmarks():
    print("\n" + "="*80)
    print("RELIGHT STUDIO — RS-SPIKE-3A BENCHMARK EXECUTION")
    print("Validating Analytical 3D Proxies, Area Lights & Cyclorama Receivers")
    print("="*80)
    
    test_manifest = [
        # 1. Perfume Box on Flat Floor Plane
        ("S3A_01_perfume_box_plane", "cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE),
        # 2. Perfume Box on Curved Cyclorama Cove
        ("S3A_02_perfume_box_cyclorama", "cat1_perfume_box", ProxyType.OBB, ReceiverType.CYCLORAMA),
        # 3. Cylindrical Cosmetic Bottle on Curved Cyclorama
        ("S3A_03_cosmetic_bottle_cyclorama", "cat2_cosmetic_bottle", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA),
        # 4. Footwear Sole Hull Mesh on Flat Floor
        ("S3A_04_sneaker_mesh_plane", "cat3_sneaker", ProxyType.MESH, ReceiverType.PLANE),
        # 5. Metallic Watch on Flat Floor
        ("S3A_05_metallic_watch_plane", "cat4_metallic_watch", ProxyType.OBB, ReceiverType.PLANE),
        # 6. Organic Sculpture on Curved Cyclorama
        ("S3A_06_organic_sculpture_cyclorama", "cat5_organic_object", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA),
    ]
    
    backend = RenderBackend()
    results = []
    
    for case_id, cat_id, proxy_type, rec_type in test_manifest:
        print(f"\n[RUNNING] {case_id} ({cat_id}, Proxy: {proxy_type.value}, Receiver: {rec_type.value})...")
        
        scene, img_orig, depth, normals, fg_mask, V_gt = generate_synthetic_scene_fixture(
            cat_id, proxy_type, rec_type, H=256, W=384
        )
        
        # Receiver mask
        rec_mask = (~fg_mask)
        
        # Cliff mask for leakage
        gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
        gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
        cliff_mask = (gx**2 + gy**2) > 0.04
        
        # Contact mask: lowest row of foreground
        contact_mask = np.zeros_like(fg_mask)
        if np.any(fg_mask):
            fy, fx = np.where(fg_mask)
            max_y = np.max(fy)
            contact_mask[max(0, max_y - 2):min(depth.shape[0], max_y + 3), np.min(fx):np.max(fx)] = True
            
        # Execute Render (Preview Quality: 4 samples)
        t_prev_0 = time.time()
        res_preview = backend.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.PREVIEW)
        lat_prev_ms = (time.time() - t_prev_0) * 1000.0
        
        # Execute Render (Final Quality: 32 samples)
        t_final_0 = time.time()
        res_final = backend.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.FINAL)
        lat_final_ms = (time.time() - t_final_0) * 1000.0
        
        # Compute quantitative metrics against GT
        V_cand = res_final["direct_visibility"]
        sde = compute_SDE(V_cand, V_gt, rec_mask)
        iou = compute_IoU(V_cand, V_gt, rec_mask)
        slr = compute_SLR(V_cand, cliff_mask, V_gt)
        cgs = compute_CGS(V_cand, res_final["contact_occlusion"], contact_mask)
        dci = compute_DCI(img_orig, res_final["relit_srgb"])
        
        # Acceptance gate evaluations
        gate_sde = "PASS" if sde <= 2.0 else "FAIL"
        gate_iou = "PASS" if iou >= 0.90 else "FAIL"
        gate_slr = "PASS" if slr <= 1.0 else "FAIL"
        gate_cgs = "PASS" if cgs <= 0.15 else "FAIL"
        gate_dci = "PASS" if dci >= 0.980 else "FAIL"
        gate_lat = "PASS" if lat_prev_ms <= 35.0 else "FAIL"
        
        print(f"  -> SDE={sde}px ({gate_sde}), IoU={iou} ({gate_iou}), SLR={slr}% ({gate_slr}), CGS={cgs} ({gate_cgs}), DCI={dci} ({gate_dci})")
        print(f"  -> Latency: Preview={lat_prev_ms:.1f}ms, Final={lat_final_ms:.1f}ms")
        
        # Save Diagnostic Images
        img_out_srgb = (res_final["relit_srgb"] * 255).astype(np.uint8)
        img_overlay = (res_final["proxy_overlay"] * 255).astype(np.uint8)
        
        # Heatmap of shadow difference
        diff_vis = np.abs(V_cand - V_gt)
        heat_vis = cv2.applyColorMap((np.clip(diff_vis * 2.5, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)
        
        # 3D Studio Stage Viewport
        stage_view = render_virtual_studio_viewport(scene, width=384, height=256)
        
        # Multi-panel diagnostic sheet: [Original, Relit, Wireframe Overlay, 3D Studio Stage, Shadow Diff Heatmap]
        panel = np.hstack([
            (img_orig * 255).astype(np.uint8),
            img_out_srgb,
            img_overlay,
            stage_view,
            heat_vis
        ])
        
        sheet_path = os.path.join(DIAG_DIR, f"{case_id}_diagnostic_board.png")
        Image.fromarray(panel).save(sheet_path)
        
        # Save GT image
        gt_vis_img = (V_gt * 255).astype(np.uint8)
        Image.fromarray(gt_vis_img).save(os.path.join(GT_DIR, f"{case_id}_gt_vis.png"))
        
        entry = {
            "case_id": case_id,
            "category": cat_id,
            "proxy_type": proxy_type.value,
            "receiver_type": rec_type.value,
            "SDE_px": sde, "gate_SDE": gate_sde,
            "IoU": iou, "gate_IoU": gate_iou,
            "SLR_pct": slr, "gate_SLR": gate_slr,
            "CGS": cgs, "gate_CGS": gate_cgs,
            "DCI": dci, "gate_DCI": gate_dci,
            "latency_preview_ms": round(lat_prev_ms, 2),
            "latency_final_ms": round(lat_final_ms, 2),
            "gate_latency": gate_lat,
            "diagnostic_sheet": sheet_path
        }
        results.append(entry)

    # 4. PHOTOGRAPHIC CASE VALIDATION (Nike Shoe)
    print("\n[RUNNING] Photographic Validation: Nike Sneaker Photograph...")
    photo_path = "demo_output/nike_sample.jpg"
    depth_path = "demo_output/nike_test/depth.png"
    normals_path = "demo_output/nike_test/normals.png"
    
    im_photo = Image.open(photo_path).convert("RGB")
    im_arr = np.array(im_photo, dtype=np.float32) / 255.0
    H_p, W_p = im_arr.shape[:2]
    
    d_im = Image.open(depth_path)
    d_arr = np.array(d_im, dtype=np.float32) / 255.0
    if d_arr.ndim == 3: d_arr = d_arr[..., 0]
    
    n_im = Image.open(normals_path)
    n_arr = (np.array(n_im, dtype=np.float32) / 255.0) * 2.0 - 1.0
    n_arr = n_arr / np.clip(np.linalg.norm(n_arr, axis=-1, keepdims=True), 1e-6, None)
    
    ground_y = 648
    fg_mask = (d_arr > 0.45) & (np.arange(H_p)[:, None] <= ground_y)
    
    photo_scene = StudioScene()
    photo_scene.camera = CameraData(pos=[0.0, 1.2, 2.5], target=[0.0, 0.35, 0.0], fov_deg=45.0, width=W_p, height=H_p)
    photo_scene.subject.proxy_type = ProxyType.MESH
    photo_scene.subject.position = [0.0, 0.15, 0.0]
    photo_scene.receiver = ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=0.0)
    
    t0 = time.time()
    photo_res = backend.render(photo_scene, im_arr, d_arr, n_arr, fg_mask, quality=RenderQuality.FINAL)
    lat_photo_ms = (time.time() - t0) * 1000.0
    
    dci_photo = compute_DCI(im_arr, photo_res["relit_srgb"])
    print(f"  -> Photographic Relit: DCI={dci_photo}, Latency={lat_photo_ms:.1f}ms")
    
    # Save photographic result
    photo_out_path = os.path.join(DIAG_DIR, "photo_nike_relit_final.png")
    Image.fromarray((photo_res["relit_srgb"] * 255).astype(np.uint8)).save(photo_out_path)
    
    stage_photo = render_virtual_studio_viewport(photo_scene, width=W_p//2, height=H_p//2)
    Image.fromarray(stage_photo).save(os.path.join(DIAG_DIR, "photo_nike_stage_viewport.png"))
    
    # Export JSON and CSV
    json_path = os.path.join(BENCH_DIR, "benchmark_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
        
    csv_path = os.path.join(BENCH_DIR, "benchmark_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
        
    print(f"\n[SAVED] Benchmark JSON -> {json_path}")
    print(f"[SAVED] Benchmark CSV  -> {csv_path}")
    return results


if __name__ == "__main__":
    run_rs_spike_3a_benchmarks()
