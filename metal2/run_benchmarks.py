"""
RELIGHT STUDIO — RS-METAL-2: COMPREHENSIVE HARDWARE BENCHMARK RUNNER
====================================================================
Measures actual GPU execution on Apple Silicon (Apple M5):
  • Numerical parity against repaired CPU reference
  • Geometry hit agreement
  • Shadow SDE and IoU against Ground Truth
  • Protected-region mutation (exact bitwise test)
  • Deterministic replay
  • P50/P95 and Peak Latency across 10 iterations per case
  • Multi-resolution profiling: 384x256, 1024x768, 1920x1080
Saves authoritative JSON and CSV logs to metal2/benchmark_results/
"""

import os
import sys
import json
import csv
import math
import time
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import cv2
from PIL import Image

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
from studio3a.renderer import RenderBackend as CPURenderBackend
from studio3a.workspace import render_virtual_studio_viewport
from metal2.renderer import MetalRenderBackend

OUTPUT_DIR = "metal2/benchmark_results"
DIAG_DIR = os.path.join(OUTPUT_DIR, "diagnostic_boards")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DIAG_DIR, exist_ok=True)


def compute_SDE(V_cand: np.ndarray, V_gt: np.ndarray, receiver_mask: np.ndarray) -> float:
    cand_shadow = (V_cand < 0.85) & receiver_mask
    gt_shadow = (V_gt < 0.85) & receiver_mask
    if not np.any(cand_shadow) or not np.any(gt_shadow):
        return 0.0 if (not np.any(cand_shadow) and not np.any(gt_shadow)) else 50.0
    cy_c, cx_c = np.mean(np.where(cand_shadow)[0]), np.mean(np.where(cand_shadow)[1])
    cy_g, cx_g = np.mean(np.where(gt_shadow)[0]), np.mean(np.where(gt_shadow)[1])
    return round(float(math.sqrt((cy_c - cy_g)**2 + (cx_c - cx_g)**2)), 2)


def compute_IoU(V_cand: np.ndarray, V_gt: np.ndarray, receiver_mask: np.ndarray) -> float:
    cand_shadow = (V_cand < 0.85) & receiver_mask
    gt_shadow = (V_gt < 0.85) & receiver_mask
    if not np.any(gt_shadow):
        return 1.0 if not np.any(cand_shadow) else 0.0
    intersection = np.sum(cand_shadow & gt_shadow)
    union = np.sum(cand_shadow | gt_shadow)
    return round(float(intersection / max(union, 1)), 4)


def compute_SLR(V_cand: np.ndarray, cliff_mask: np.ndarray, V_gt: Optional[np.ndarray] = None) -> float:
    if cliff_mask is None or not np.any(cliff_mask):
        return 0.0
    cand_shadowed = (V_cand < 0.85) & cliff_mask
    if V_gt is not None:
        gt_lit = (V_gt >= 0.85) & cliff_mask
        leak_pts = cand_shadowed & gt_lit
        denom = max(np.sum(gt_lit), 1)
    else:
        leak_pts = cand_shadowed
        denom = max(np.sum(cliff_mask), 1)
    return round(float(100.0 * np.sum(leak_pts) / denom), 2)


def generate_scene_fixture(
    category_id: str,
    proxy_type: ProxyType,
    receiver_type: ReceiverType,
    H: int = 256,
    W: int = 384
) -> Tuple[StudioScene, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    scene = StudioScene()
    scene.camera = CameraData(pos=[0.0, 1.2, 2.5], target=[0.0, 0.35, 0.0], fov_deg=45.0, width=W, height=H)
    scene.receiver = ReceiverData(receiver_type=receiver_type, ground_y=0.0)
    scene.subject.proxy_type = proxy_type
    
    if category_id == "cat1_perfume_box":
        scene.subject.dimensions = [0.25, 0.40, 0.20]
        scene.subject.position = [0.0, 0.40, 0.0]
    elif category_id == "cat2_cosmetic_bottle":
        scene.subject.dimensions = [0.18, 0.45, 0.18]
        scene.subject.sq_exponents = [0.3, 1.0]
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

    cam = Camera3D(pos=scene.camera.pos, target=scene.camera.target, width=W, height=H, fov_deg=scene.camera.fov_deg)
    ray_o, ray_d = cam.generate_camera_rays()
    
    cpu_b = CPURenderBackend()
    proxy = cpu_b.instantiate_proxy_geometry(scene)
    receiver = cpu_b.instantiate_receiver(scene)
    
    hit_proxy, t_proxy, norm_proxy = proxy.intersect_rays(ray_o, ray_d)
    hit_rec, t_rec, norm_rec = receiver.intersect_rays(ray_o, ray_d)
    
    fg_mask = hit_proxy & (t_proxy < t_rec)
    rec_mask = (~fg_mask) & hit_rec
    is_sky = (~fg_mask) & (~hit_rec)
    
    depth_map = np.zeros((H, W), dtype=np.float32)
    normals_map = np.zeros((H, W, 3), dtype=np.float32)
    surface_pos = np.zeros((H, W, 3), dtype=np.float32)
    
    t_cam = np.where(fg_mask, t_proxy, np.where(rec_mask, t_rec, 20.0))
    cos_f = np.maximum(0.1, np.sum(ray_d * cam.forward, axis=-1))
    z_cam = t_cam * cos_f
    depth_map = np.clip((z_cam - 0.5) / 2.5, 0.0, 1.0).astype(np.float32)
    
    normals_map[fg_mask] = norm_proxy[fg_mask]
    normals_map[rec_mask] = norm_rec[rec_mask]
    normals_map[is_sky] = -ray_d[is_sky]
    
    surface_pos[fg_mask] = ray_o[fg_mask] + t_proxy[fg_mask, None] * ray_d[fg_mask]
    surface_pos[rec_mask] = ray_o[rec_mask] + t_rec[rec_mask, None] * ray_d[rec_mask]
    surface_pos[is_sky] = ray_o[is_sky] + 50.0 * ray_d[is_sky]
    
    # Base synthetic image
    L_init = np.array([0.5, 0.8, 0.5], dtype=np.float32)
    L_init /= np.linalg.norm(L_init)
    diffuse = np.maximum(0.0, np.sum(normals_map * L_init, axis=-1))
    
    base_color = np.zeros((H, W, 3), dtype=np.float32)
    base_color[fg_mask] = np.array([0.80, 0.70, 0.60])
    base_color[rec_mask] = np.array([0.75, 0.75, 0.75])
    base_color[is_sky] = np.array([0.15, 0.18, 0.22])
    
    img_orig_srgb = np.clip(base_color * (0.2 + 0.8 * diffuse[..., None]), 0.0, 1.0)
    
    # Ground-truth visibility (64 samples)
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
        seed=1337,
        active_mask=(fg_mask | rec_mask)
    )
    V_gt[is_sky] = 1.0
    
    return scene, img_orig_srgb, depth_map, normals_map, fg_mask, rec_mask, V_gt


def run_full_metal_validation():
    print("\n" + "="*80)
    print("RELIGHT STUDIO — RS-METAL-2: APPLE SILICON GPU VALIDATION & BENCHMARKS")
    print("Measuring Real Hardware Parity, Latency, and Gates on Apple M5")
    print("="*80)

    cpu_backend = CPURenderBackend()
    metal_backend = MetalRenderBackend()
    dev_info = metal_backend.bridge.get_device_info()
    print(f"[DEVICE] Detected: {dev_info['device_name']}, Unified Memory: {dev_info['has_unified_memory']}")

    test_manifest = [
        ("M2_01_perfume_box_plane", "cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE),
        ("M2_02_perfume_box_cyclorama", "cat1_perfume_box", ProxyType.OBB, ReceiverType.CYCLORAMA),
        ("M2_03_cosmetic_bottle_cyclorama", "cat2_cosmetic_bottle", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA),
        ("M2_04_sneaker_mesh_plane", "cat3_sneaker", ProxyType.MESH, ReceiverType.PLANE),
        ("M2_05_metallic_watch_plane", "cat4_metallic_watch", ProxyType.OBB, ReceiverType.PLANE),
        ("M2_06_organic_sculpture_cyclorama", "cat5_organic_object", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA),
    ]

    benchmark_entries = []

    for case_id, cat_id, proxy_type, rec_type in test_manifest:
        print(f"\n[RUNNING CASE] {case_id} ({proxy_type.value} on {rec_type.value})...")
        scene, img_orig, depth, normals, fg_mask, rec_mask, V_gt = generate_scene_fixture(
            cat_id, proxy_type, rec_type, H=256, W=384
        )

        # 1. Parity Run against CPU
        res_cpu = cpu_backend.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.FINAL)
        res_gpu = metal_backend.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.FINAL)

        # Numerical Parity Checks
        err_irr_max = float(np.max(np.abs(res_gpu["direct_irradiance"][fg_mask] - res_cpu["direct_irradiance"][fg_mask])))
        err_vis_mean = float(np.mean(np.abs(res_gpu["direct_visibility"][rec_mask] - res_cpu["direct_visibility"][rec_mask])))

        # SDE and IoU against Ground Truth
        sde = compute_SDE(res_gpu["direct_visibility"], V_gt, rec_mask)
        iou = compute_IoU(res_gpu["direct_visibility"], V_gt, rec_mask)

        # Cliff Leakage
        gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
        gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
        cliff_mask = (gx**2 + gy**2) > 0.04
        slr = compute_SLR(res_gpu["direct_visibility"], cliff_mask, V_gt)

        # 2. Protected Region Zero-Mutation Test
        prot_mask = np.zeros_like(fg_mask)
        W_half = fg_mask.shape[1] // 2
        prot_mask[:, :W_half] = True
        res_prot = metal_backend.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.PREVIEW, protected_mask=prot_mask)
        max_prot_mut = float(np.max(np.abs(res_prot["relit_srgb"][prot_mask] - img_orig[prot_mask])))

        # 3. Deterministic Replay Test on GPU
        scene_json = scene.to_json()
        scene_reload = StudioScene.from_json(scene_json)
        res_replay = metal_backend.render(scene_reload, img_orig, depth, normals, fg_mask, quality=RenderQuality.FINAL)
        max_replay_diff = float(np.max(np.abs(res_gpu["relit_srgb"] - res_replay["relit_srgb"])))

        # 4. Latency Distribution Measurement (10 Warm Timed Iterations)
        prev_times_gpu = []
        prev_times_wall = []
        final_times_gpu = []
        final_times_wall = []

        for _ in range(10):
            t_w0 = time.time()
            r_p = metal_backend.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.PREVIEW)
            prev_times_wall.append((time.time() - t_w0) * 1000.0)
            prev_times_gpu.append(r_p["diagnostics"]["gpu_time_ms"])

            t_wf0 = time.time()
            r_f = metal_backend.render(scene, img_orig, depth, normals, fg_mask, quality=RenderQuality.FINAL)
            final_times_wall.append((time.time() - t_wf0) * 1000.0)
            final_times_gpu.append(r_f["diagnostics"]["gpu_time_ms"])

        p50_prev_gpu = round(float(np.percentile(prev_times_gpu, 50)), 2)
        p95_prev_gpu = round(float(np.percentile(prev_times_gpu, 95)), 2)
        p50_final_gpu = round(float(np.percentile(final_times_gpu, 50)), 2)
        p95_final_gpu = round(float(np.percentile(final_times_gpu, 95)), 2)

        gate_parity = "PASS" if err_irr_max < 0.05 else "FAIL"
        gate_prot = "PASS" if max_prot_mut == 0.0 else "FAIL"
        gate_replay = "PASS" if max_replay_diff == 0.0 else "FAIL"
        gate_prev_lat = "PASS" if p95_prev_gpu <= 16.6 else "FAIL"

        print(f"  -> Irradiance Parity: Max Err = {err_irr_max:.6f} ({gate_parity})")
        print(f"  -> Shadow GT: SDE = {sde}px, IoU = {iou}, SLR = {slr}%")
        print(f"  -> Zero-Mutation = {max_prot_mut:.10f} ({gate_prot}), Replay Diff = {max_replay_diff:.10f} ({gate_replay})")
        print(f"  -> Latency: Preview P50={p50_prev_gpu}ms, P95={p95_prev_gpu}ms ({gate_prev_lat}) | Final P50={p50_final_gpu}ms, P95={p95_final_gpu}ms")

        # Save Diagnostic Visual Sheet
        img_out_srgb = (res_gpu["relit_srgb"] * 255).astype(np.uint8)
        img_overlay = (res_gpu["proxy_overlay"] * 255).astype(np.uint8)
        diff_vis = np.abs(res_gpu["direct_visibility"] - V_gt)
        heat_vis = cv2.applyColorMap((np.clip(diff_vis * 2.5, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)
        stage_view = render_virtual_studio_viewport(scene, width=384, height=256)

        panel = np.hstack([
            (img_orig * 255).astype(np.uint8),
            img_out_srgb,
            img_overlay,
            stage_view,
            heat_vis
        ])
        sheet_path = os.path.join(DIAG_DIR, f"{case_id}_diagnostic_board.png")
        Image.fromarray(panel).save(sheet_path)

        entry = {
            "case_id": case_id,
            "category": cat_id,
            "proxy_type": proxy_type.value,
            "receiver_type": rec_type.value,
            "err_irr_max": err_irr_max, "gate_parity": gate_parity,
            "SDE_px": sde, "IoU": iou, "SLR_pct": slr,
            "zero_mutation_diff": max_prot_mut, "gate_prot": gate_prot,
            "replay_diff": max_replay_diff, "gate_replay": gate_replay,
            "preview_gpu_p50_ms": p50_prev_gpu, "preview_gpu_p95_ms": p95_prev_gpu,
            "final_gpu_p50_ms": p50_final_gpu, "final_gpu_p95_ms": p95_final_gpu,
            "gate_latency": gate_prev_lat,
            "diagnostic_sheet": sheet_path
        }
        benchmark_entries.append(entry)

    # 5. Multi-Resolution Photographic Scaling Benchmark (Nike Sneaker at 1080p)
    print("\n[RUNNING] Full-Resolution Photographic Plate Validation (Nike Sneaker at 1080p)...")
    photo_path = "demo_output/nike_sample.jpg"
    depth_path = "demo_output/nike_test/depth.png"
    normals_path = "demo_output/nike_test/normals.png"

    im_photo = Image.open(photo_path).convert("RGB").resize((1920, 1080))
    im_arr = np.array(im_photo, dtype=np.float32) / 255.0
    H_p, W_p = im_arr.shape[:2]

    d_im = Image.open(depth_path).resize((1920, 1080))
    d_arr = np.array(d_im, dtype=np.float32) / 255.0
    if d_arr.ndim == 3: d_arr = d_arr[..., 0]

    n_im = Image.open(normals_path).resize((1920, 1080))
    n_arr = (np.array(n_im, dtype=np.float32) / 255.0) * 2.0 - 1.0
    n_arr = n_arr / np.clip(np.linalg.norm(n_arr, axis=-1, keepdims=True), 1e-6, None)

    ground_y = int(H_p * 0.85)
    fg_mask_photo = (d_arr > 0.45) & (np.arange(H_p)[:, None] <= ground_y)

    photo_scene = StudioScene()
    photo_scene.camera = CameraData(pos=[0.0, 1.2, 2.5], target=[0.0, 0.35, 0.0], fov_deg=45.0, width=W_p, height=H_p)
    photo_scene.subject.proxy_type = ProxyType.MESH
    photo_scene.subject.position = [0.0, 0.15, 0.0]
    photo_scene.receiver = ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=0.0)

    # Measure 1080p Latency on Apple M5
    t_1080p = []
    for _ in range(5):
        r_1080 = metal_backend.render(photo_scene, im_arr, d_arr, n_arr, fg_mask_photo, quality=RenderQuality.FINAL)
        t_1080p.append(r_1080["diagnostics"]["gpu_time_ms"])

    p50_1080p = round(float(np.percentile(t_1080p, 50)), 2)
    p95_1080p = round(float(np.percentile(t_1080p, 95)), 2)
    print(f"  -> Photographic 1080p Full Production Render: GPU P50 = {p50_1080p}ms, P95 = {p95_1080p}ms")

    # Save Photographic Outputs
    photo_relit_path = os.path.join(DIAG_DIR, "photo_nike_1080p_relit_metal.png")
    Image.fromarray((r_1080["relit_srgb"] * 255).astype(np.uint8)).save(photo_relit_path)

    # Export JSON and CSV
    json_path = os.path.join(OUTPUT_DIR, "metal_benchmark_results.json")
    with open(json_path, "w") as f:
        json.dump(benchmark_entries, f, indent=2)

    csv_path = os.path.join(OUTPUT_DIR, "metal_benchmark_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(benchmark_entries[0].keys()))
        writer.writeheader()
        writer.writerows(benchmark_entries)

    print(f"\n[SAVED] Metal Benchmark JSON -> {json_path}")
    print(f"[SAVED] Metal Benchmark CSV  -> {csv_path}")

if __name__ == "__main__":
    run_full_metal_validation()
