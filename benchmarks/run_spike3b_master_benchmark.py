"""
RELIGHT STUDIO — RS-SPIKE-3B: MASTER BENCHMARK RUNNER
=====================================================
Executes the unified regression and verification suite for RS-SPIKE-3B:
  • 6 Canonical Scenes: M2_01 to M2_06 (Parity, Shadows, Latency, Zero-Mutation, Replay)
  • 3 Photographic Real Plates: P1 to P3 (Detail, Gamut, Immutability)
  • Multi-resolution latency distributions on Apple Silicon GPU
Exports authoritative docs/RS-SPIKE-3B/benchmark_results.json and CSV
"""

import os
import sys
import json
import csv
import time
import numpy as np
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, ProxyType, ReceiverType,
    EnergyConvention, RenderQuality
)
from studio3a.renderer import RenderBackend as CPURenderBackend
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture
from metal2.shadow_evaluation import (
    compute_soft_iou, compute_continuous_sde,
    compute_contour_boundary_displacement, compute_penumbra_metrics
)
from benchmarks.validate_photographic_fidelity import load_photographic_case, srgb_to_linear, eval_DCI


def run_master_benchmark():
    print("="*80)
    print("RELIGHT STUDIO — RS-SPIKE-3B MASTER ENGINEERING BENCHMARK")
    print("Measuring Real Apple Silicon Hardware Parity, Shadows & Latency")
    print("="*80)

    cpu_b = CPURenderBackend()
    metal_b = MetalRenderBackend()

    canonical_manifest = [
        ("M2_01_perfume_box_plane", "cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE),
        ("M2_02_perfume_box_cyclorama", "cat1_perfume_box", ProxyType.OBB, ReceiverType.CYCLORAMA),
        ("M2_03_cosmetic_bottle_cyclorama", "cat2_cosmetic_bottle", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA),
        ("M2_04_sneaker_mesh_plane", "cat3_sneaker", ProxyType.MESH, ReceiverType.PLANE),
        ("M2_05_metallic_watch_plane", "cat4_metallic_watch", ProxyType.OBB, ReceiverType.PLANE),
        ("M2_06_organic_sculpture_cyclorama", "cat5_organic_object", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA),
    ]

    canonical_results = []

    print("\n--- SECTION 1: CANONICAL 6-SCENE PARITY & SHADOW EVALUATION ---")
    for case_id, cat_id, p_type, r_type in canonical_manifest:
        print(f"\n[EVALUATING] {case_id} ({p_type.value} on {r_type.value})...")
        scene, img, depth, normals, fg, rec, _ = generate_scene_fixture(cat_id, p_type, r_type, H=256, W=384)
        
        # 1. FINAL Quality Parity Run (64 samples)
        scene.render_settings.final_samples = 64
        r_cpu = cpu_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)
        r_metal = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)

        # Numerical Parity Metrics
        irr_mae = float(np.mean(np.abs(r_metal["direct_irradiance"][fg] - r_cpu["direct_irradiance"][fg])))
        vis_mae = float(np.mean(np.abs(r_metal["direct_visibility"][rec] - r_cpu["direct_visibility"][rec])))

        # Shadow Transport Metrics against Authoritative CPU Reference
        soft_iou = compute_soft_iou(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
        sde = compute_continuous_sde(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
        contour_disp = compute_contour_boundary_displacement(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
        penumbra_res = compute_penumbra_metrics(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)

        # 2. Bitwise Zero-Mutation Test
        prot_mask = np.zeros_like(fg)
        prot_mask[:, :fg.shape[1] // 2] = True
        r_prot = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.PREVIEW, protected_mask=prot_mask)
        max_prot_mut = float(np.max(np.abs(r_prot["relit_srgb"][prot_mask] - img[prot_mask])))

        # 3. Deterministic Replay Test
        scene_json = scene.to_json()
        scene_reload = StudioScene.from_json(scene_json)
        r_replay = metal_b.render(scene_reload, img, depth, normals, fg, quality=RenderQuality.FINAL)
        replay_diff = float(np.max(np.abs(r_metal["relit_srgb"] - r_replay["relit_srgb"])))

        # 4. Latency Distribution (10 iterations)
        prev_gpu, prev_host = [], []
        final_gpu, final_host = [], []
        for _ in range(10):
            t0 = time.perf_counter()
            rp = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.PREVIEW)
            prev_host.append((time.perf_counter() - t0) * 1000.0)
            prev_gpu.append(rp["diagnostics"]["gpu_time_ms"])

            t0 = time.perf_counter()
            rf = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)
            final_host.append((time.perf_counter() - t0) * 1000.0)
            final_gpu.append(rf["diagnostics"]["gpu_time_ms"])

        p50_prev_gpu = round(float(np.percentile(prev_gpu, 50)), 2)
        p95_prev_gpu = round(float(np.percentile(prev_gpu, 95)), 2)
        p50_final_gpu = round(float(np.percentile(final_gpu, 50)), 2)
        p95_final_gpu = round(float(np.percentile(final_gpu, 95)), 2)

        # Acceptance Gates
        gate_iou = "PASS" if (soft_iou >= 0.93 if r_type == ReceiverType.PLANE and p_type == ProxyType.OBB else soft_iou >= 0.89) else "FAIL"
        gate_sde = "PASS" if sde <= 3.0 else "FAIL"
        gate_irr = "PASS" if irr_mae <= 0.001 else "FAIL"
        gate_mut = "PASS" if max_prot_mut == 0.0 else "FAIL"
        gate_replay = "PASS" if replay_diff == 0.0 else "FAIL"
        gate_lat = "PASS" if p95_prev_gpu <= 16.6 else "FAIL"

        print(f"  Parity: Irr MAE={irr_mae:.6f} ({gate_irr}), Vis MAE={vis_mae:.6f}")
        print(f"  Shadows: Soft IoU={soft_iou:.4f} ({gate_iou}), SDE={sde:.2f}px ({gate_sde}), Contour={contour_disp:.2f}px")
        print(f"  Integrity: Mutation={max_prot_mut:.10f} ({gate_mut}), Replay Diff={replay_diff:.10f} ({gate_replay})")
        print(f"  Latency: Prev P95={p95_prev_gpu}ms ({gate_lat}), Final P95={p95_final_gpu}ms")

        canonical_results.append({
            "case_id": case_id,
            "proxy_type": p_type.value,
            "receiver_type": r_type.value,
            "soft_iou": soft_iou, "gate_soft_iou": gate_iou,
            "sde_px": sde, "gate_sde": gate_sde,
            "contour_disp_px": contour_disp,
            "penumbra_mae": penumbra_res["penumbra_mae"],
            "irradiance_mae": irr_mae, "gate_irradiance": gate_irr,
            "zero_mutation_diff": max_prot_mut, "gate_zero_mutation": gate_mut,
            "replay_diff": replay_diff, "gate_replay": gate_replay,
            "preview_gpu_p50_ms": p50_prev_gpu, "preview_gpu_p95_ms": p95_prev_gpu,
            "final_gpu_p50_ms": p50_final_gpu, "final_gpu_p95_ms": p95_final_gpu,
            "gate_latency": gate_lat
        })

    print("\n--- SECTION 2: PHOTOGRAPHIC REAL PLATES ---")
    photo_manifest = ["P1_nike_sneaker", "P2_classical_statue", "P3_architectural_relief"]
    photo_results = []
    for pid in photo_manifest:
        cid, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case(pid)
        H, W = img_srgb.shape[:2]
        res = metal_b.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL)

        # Protected mutation test
        prot_mask = np.zeros((H, W), dtype=bool)
        prot_mask[:, :int(W * 0.40)] = True
        res_prot = metal_b.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL, protected_mask=prot_mask)
        max_prot = float(np.max(np.abs(res_prot["relit_srgb"][prot_mask] - img_srgb[prot_mask])))

        # DCI detail preservation
        orig_lin = srgb_to_linear(img_srgb)
        relit_lin = srgb_to_linear(res["relit_srgb"])
        dci_all = eval_DCI(orig_lin, relit_lin)
        dci_fg = eval_DCI(orig_lin, relit_lin, fg_mask)

        # Gamut validity
        out_gamut = int(np.sum((res["relit_srgb"] < 0.0) | (res["relit_srgb"] > 1.0)))

        photo_results.append({
            "case_id": pid,
            "width": W, "height": H,
            "max_protected_mutation": max_prot,
            "dci_overall": dci_all,
            "dci_foreground": dci_fg,
            "out_of_gamut_pixels": out_gamut,
            "gpu_time_ms": res["diagnostics"]["gpu_time_ms"]
        })
        print(f"  {pid}: Mut={max_prot:.10f}, DCI(overall)={dci_all:.4f}, DCI(fg)={dci_fg:.4f}, OutOfGamut={out_gamut}, GPU={res['diagnostics']['gpu_time_ms']}ms")

    master_summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": "Apple Silicon (Metal)",
        "canonical_scenes": canonical_results,
        "photographic_plates": photo_results
    }

    out_json = "docs/RS-SPIKE-3B/benchmark_results.json"
    with open(out_json, "w") as f:
        json.dump(master_summary, f, indent=2)

    out_csv = "docs/RS-SPIKE-3B/benchmark_results.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(canonical_results[0].keys()))
        writer.writeheader()
        writer.writerows(canonical_results)

    print(f"\n[SAVED] Benchmark JSON -> {out_json}")
    print(f"[SAVED] Benchmark CSV  -> {out_csv}")


if __name__ == "__main__":
    run_master_benchmark()
