"""
RELIGHT STUDIO — RS-SPIKE-3C.3: MASTER BENCHMARK & FIDELITY EVALUATION HARNESS
==============================================================================
Evaluates:
  1. Metal GPU Performance across Preview (4 spp) and Final (25 spp) at 1024x576 and 1920x1080
     Configurations:
       • IBL Disabled (baseline)
       • IBL Enabled (environment only)
       • 1 Direct Light + IBL
       • 4 Direct Lights + IBL
       • 8 Direct Lights + IBL
     Measures: Wall-clock P50, P95, P99, Mean, FPS, GPU Kernel time, CPU overhead, UMA allocations
  2. Photographic Fidelity & DCI Preservation across Plates P1, P2, P3
     Verifies: Foreground DCI >= 0.8800 on dielectrics, bitwise zero-mutation on protected regions.
  3. Visual Board Generation into docs/RS-SPIKE-3C.3/visual_boards/
"""

import os
import json
import time
import math
import numpy as np
import cv2
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, RenderQuality, RenderSettingsData
)
from studio3a.material import MaterialData
from studio3a.environment import EnvironmentData
from studio3a.reconstruction import compute_DCI
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture
from benchmarks.validate_photographic_fidelity import load_photographic_case

PERF_JSON = "metal2/benchmark_results/ibl_performance_results.json"
PHOTO_JSON = "metal2/benchmark_results/ibl_photographic_results.json"
BOARDS_DIR = "docs/RS-SPIKE-3C.3/visual_boards"

os.makedirs("metal2/benchmark_results", exist_ok=True)
os.makedirs(BOARDS_DIR, exist_ok=True)


def run_performance_benchmarks():
    print("=" * 80)
    print("RELIGHT STUDIO — RS-SPIKE-3C.3: HARDWARE PERFORMANCE BENCHMARK")
    print("Measuring Real Host Wall-Clock Latency & GPU Kernel Execution on Apple Silicon")
    print("=" * 80)

    mb = MetalRenderBackend()
    dev_info = mb.bridge.get_device_info()
    print(f"[DEVICE] {dev_info['device_name']}, Unified Memory: {dev_info['has_unified_memory']}")

    resolutions = [
        ("Viewport Preview (1024x576)", 1024, 576, RenderQuality.PREVIEW, 4),
        ("Viewport Final (1024x576)", 1024, 576, RenderQuality.FINAL, 25),
        ("Full HD Preview (1920x1080)", 1920, 1080, RenderQuality.PREVIEW, 4),
        ("Full HD Final (1920x1080)", 1920, 1080, RenderQuality.FINAL, 25),
    ]

    configs = [
        ("IBL_Disabled", 0, False),
        ("IBL_Only", 0, True),
        ("Direct_1_Plus_IBL", 1, True),
        ("Direct_4_Plus_IBL", 4, True),
        ("Direct_8_Plus_IBL", 8, True),
    ]

    perf_results = []

    for res_name, W, H, quality, spp in resolutions:
        print(f"\n--- Benchmarking Resolution: {res_name} ---")
        scene_base, img, depth, norm, fg, rec, _ = generate_scene_fixture(
            "cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE, H=H, W=W
        )

        for cfg_name, num_lights, env_en in configs:
            scene = StudioScene.from_json(scene_base.to_json())
            scene.render_settings.preview_samples = spp
            scene.render_settings.final_samples = spp
            scene.render_settings.enable_specular = True

            # Material setup: glossy plastic
            scene.subject.material = MaterialData.plastic()

            # Environment setup
            scene.environment = EnvironmentData(
                enabled=env_en,
                intensity=1.0 if env_en else 0.0,
                rotation_deg=45.0,
                diffuse_weight=1.0,
                specular_weight=1.0
            )

            # Direct lights setup
            scene.lights = []
            if num_lights >= 1:
                scene.lights.append(AreaLightData(
                    id="l0", name="Key", position=[1.2, 1.8, 1.5], intensity=1.2, width=0.4, height=0.4
                ))
            extra_lights = [
                ("Fill", [-1.5, 1.2, 1.0], [-25.0, -35.0, 0.0], 0.6, 3200.0),
                ("Rim", [0.0, 2.2, -1.8], [45.0, 180.0, 0.0], 1.2, 6500.0),
                ("Top", [0.0, 2.8, 0.0], [-90.0, 0.0, 0.0], 0.5, 5000.0),
                ("AccentL", [-2.0, 0.8, -0.5], [10.0, 90.0, 0.0], 0.8, 4000.0),
                ("AccentR", [2.0, 0.8, -0.5], [10.0, -90.0, 0.0], 0.8, 4000.0),
                ("Floor", [0.0, 0.1, 1.0], [45.0, 0.0, 0.0], 0.4, 3000.0),
                ("Rim2", [-0.8, 2.0, -2.0], [40.0, 160.0, 0.0], 0.7, 7000.0),
            ]
            for i in range(max(0, num_lights - 1)):
                name, pos, rot, inten, cct = extra_lights[i]
                scene.lights.append(AreaLightData(
                    id=f"l{i+1}", name=name, position=pos, rotation_deg=rot, intensity=inten, temperature_kelvin=cct, width=0.3, height=0.3
                ))

            # Warmup
            for _ in range(3):
                mb.render(scene, img, depth, norm, fg, quality=quality)

            mb.bridge.reset_buffer_pool()
            mb.render(scene, img, depth, norm, fg, quality=quality)

            n_iter = 25
            wall_times = []
            gpu_times = []

            for _ in range(n_iter):
                t0 = time.time()
                res = mb.render(scene, img, depth, norm, fg, quality=quality)
                dt_wall = (time.time() - t0) * 1000.0
                wall_times.append(dt_wall)
                gpu_times.append(res["diagnostics"]["gpu_time_ms"])

            pool_stats = mb.bridge.get_buffer_pool_stats()
            p50 = float(np.percentile(wall_times, 50))
            p95 = float(np.percentile(wall_times, 95))
            p99 = float(np.percentile(wall_times, 99))
            mean_wall = float(np.mean(wall_times))
            mean_gpu = float(np.mean(gpu_times))
            cpu_overhead = max(0.0, mean_wall - mean_gpu)
            fps = round(1000.0 / mean_wall, 1)

            print(
                f"  [{cfg_name:18s}] "
                f"Wall P50={p50:5.2f}ms | P95={p95:5.2f}ms | P99={p99:5.2f}ms | "
                f"GPU={mean_gpu:5.2f}ms | CPU={cpu_overhead:5.2f}ms | FPS={fps:5.1f}"
            )

            perf_results.append({
                "resolution": res_name,
                "width": W,
                "height": H,
                "quality": quality.value,
                "spp": spp,
                "configuration": cfg_name,
                "num_lights": num_lights,
                "environment_enabled": env_en,
                "wall_p50_ms": round(p50, 2),
                "wall_p95_ms": round(p95, 2),
                "wall_p99_ms": round(p99, 2),
                "wall_mean_ms": round(mean_wall, 2),
                "gpu_mean_ms": round(mean_gpu, 2),
                "cpu_overhead_ms": round(cpu_overhead, 2),
                "fps": fps,
                "buffer_pool_alloc_count": pool_stats["alloc_count"],
                "buffer_pool_steady_frames": pool_stats["steady_frames"],
            })

    with open(PERF_JSON, "w") as f:
        json.dump(perf_results, f, indent=2)
    print(f"\n[PERFORMANCE RESULTS SAVED] {PERF_JSON}")


def run_photographic_evaluation_and_visual_boards():
    print("\n" + "=" * 80)
    print("RELIGHT STUDIO — RS-SPIKE-3C.3: PHOTOGRAPHIC EVALUATION & BOARDS")
    print("=" * 80)

    metal_renderer = MetalRenderBackend()
    cases = [
        ("P1_nike_sneaker", "Nike Sneaker (Commercial Footwear)", MaterialData.fabric()),
        ("P2_classical_statue", "Classical Statue (Sculpted Marble)", MaterialData.marble()),
        ("P3_architectural_relief", "Architectural Relief (Weathered Stone)", MaterialData.marble()),
    ]

    photo_results = []

    for case_id, case_title, base_mat in cases:
        print(f"\n--- [PLATE EVALUATION] {case_title} ---")
        _, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case(case_id)
        H, W = img_srgb.shape[:2]

        prot_mask = np.zeros((H, W), dtype=bool)
        prot_mask[:, :int(W * 0.35)] = True

        # Render 1: Baseline Direct-only (No Environment)
        scene.environment = EnvironmentData(enabled=False)
        scene.subject.material = base_mat
        res_direct = metal_renderer.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL, protected_mask=prot_mask)

        # Render 2: Environment Only (No Direct Lights)
        scene_env_only = StudioScene.from_dict(scene.to_dict())
        scene_env_only.lights = []
        scene_env_only.environment = EnvironmentData(enabled=True, intensity=1.2, rotation_deg=60.0)
        res_env_only = metal_renderer.render(scene_env_only, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL, protected_mask=prot_mask)

        # Render 3: Hybrid Direct + Environment (Base Material)
        scene.environment = EnvironmentData(enabled=True, intensity=0.8, rotation_deg=60.0)
        res_hybrid = metal_renderer.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL, protected_mask=prot_mask)

        # Render 4: Hybrid with High-Gloss Polished Conductor Metal
        scene_metal = StudioScene.from_dict(scene.to_dict())
        scene_metal.subject.material = MaterialData.polished_metal()
        res_metal = metal_renderer.render(scene_metal, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL, protected_mask=prot_mask)

        # Metrics
        dci_direct_fg = compute_DCI(img_srgb, res_direct["relit_srgb"], mask=fg_mask)
        dci_hybrid_fg = compute_DCI(img_srgb, res_hybrid["relit_srgb"], mask=fg_mask)
        dci_whole = compute_DCI(img_srgb, res_hybrid["relit_srgb"])
        prot_err = float(np.max(np.abs(res_hybrid["relit_srgb"][prot_mask] - img_srgb[prot_mask])))
        spec_peak = float(np.max(res_hybrid["specular_radiance"][fg_mask]))
        spec_mean = float(np.mean(res_hybrid["specular_radiance"][fg_mask]))

        print(f"  Direct-only FG DCI : {dci_direct_fg:.4f}")
        print(f"  Hybrid + IBL FG DCI: {dci_hybrid_fg:.4f} (Threshold >= 0.8800)")
        print(f"  Whole-Plate DCI    : {dci_whole:.4f}")
        print(f"  Protected Error Max: {prot_err:.10f} (Bitwise zero-mutation)")
        print(f"  Specular Peak      : {spec_peak:.4f} | Mean: {spec_mean:.4f}")

        assert prot_err == 0.0
        assert dci_hybrid_fg >= 0.8800

        photo_results.append({
            "case_id": case_id,
            "title": case_title,
            "resolution": f"{W}x{H}",
            "direct_fg_dci": round(dci_direct_fg, 4),
            "hybrid_fg_dci": round(dci_hybrid_fg, 4),
            "whole_dci": round(dci_whole, 4),
            "protected_error_max": prot_err,
            "specular_peak": round(spec_peak, 4),
            "specular_mean": round(spec_mean, 4),
        })

        # Assemble Visual Board (5 columns: Original, Direct Only, Environment Only, Hybrid Relit, Specular Heatmap)
        tile_w, tile_h = 480, int(480 * (H / W))
        t_orig = cv2.resize(img_srgb, (tile_w, tile_h))
        t_dir = cv2.resize(res_direct["relit_srgb"], (tile_w, tile_h))
        t_env = cv2.resize(res_env_only["relit_srgb"], (tile_w, tile_h))
        t_hyb = cv2.resize(res_hybrid["relit_srgb"], (tile_w, tile_h))
        
        spec_luma = np.mean(res_hybrid["specular_radiance"], axis=-1)
        spec_norm = np.clip(spec_luma / max(np.percentile(spec_luma, 99.5), 1e-3), 0.0, 1.0)
        spec_heat = cv2.applyColorMap((spec_norm * 255.0).astype(np.uint8), cv2.COLORMAP_TURBO)
        t_spec = cv2.resize(spec_heat.astype(np.float32) / 255.0, (tile_w, tile_h))

        def add_banner(tile, text):
            canvas = (tile * 255.0).astype(np.uint8)
            cv2.rectangle(canvas, (0, 0), (tile_w, 36), (20, 20, 20), -1)
            cv2.putText(canvas, text, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            return canvas

        b_orig = add_banner(t_orig, "1. Original Photograph")
        b_dir = add_banner(t_dir, f"2. Direct-Only (DCI: {dci_direct_fg:.3f})")
        b_env = add_banner(t_env, "3. Environment Only")
        b_hyb = add_banner(t_hyb, f"4. Hybrid + IBL (DCI: {dci_hybrid_fg:.3f})")
        b_spec = add_banner(t_spec, f"5. Specular Energy (Peak: {spec_peak:.2f})")

        board = np.hstack([b_orig, b_dir, b_env, b_hyb, b_spec])
        board_path = os.path.join(BOARDS_DIR, f"{case_id}_ibl_board.png")
        cv2.imwrite(board_path, cv2.cvtColor(board, cv2.COLOR_RGB2BGR))
        print(f"  [SAVED BOARD] {board_path}")

    with open(PHOTO_JSON, "w") as f:
        json.dump(photo_results, f, indent=2)
    print(f"\n[PHOTOGRAPHIC RESULTS SAVED] {PHOTO_JSON}")


def run_sphere_matrix_board():
    """Generates the dual-sphere material comparison board across roughness values."""
    print("\n--- Generating Dual-Sphere Roughness Comparison Board ---")
    mb = MetalRenderBackend()
    W, H = 384, 384
    cx, cy, radius = 192.0, 192.0, 130.0

    y_coords, x_coords = np.mgrid[0:H, 0:W]
    dx, dy = (x_coords - cx), (y_coords - cy)
    r2 = dx * dx + dy * dy
    sphere_mask = r2 <= (radius * radius)

    depth = np.full((H, W), 2.5, dtype=np.float32)
    normals = np.zeros((H, W, 3), dtype=np.float32)
    normals[:, :, 2] = 1.0
    dz = np.sqrt(np.maximum(radius * radius - r2[sphere_mask], 0.0))
    normals[sphere_mask, 0] = dx[sphere_mask] / radius
    normals[sphere_mask, 1] = -dy[sphere_mask] / radius
    normals[sphere_mask, 2] = dz / radius
    depth[sphere_mask] = 2.0 - (dz / radius) * 0.3
    img = np.full((H, W, 3), 0.5, dtype=np.float32)

    roughnesses = [0.04, 0.10, 0.25, 0.50, 1.00]
    metal_tiles = []
    dielectric_tiles = []

    for r in roughnesses:
        # Metallic Conductor
        scene_m = StudioScene(
            camera=CameraData(pos=[0.0, 0.0, 2.0], target=[0.0, 0.0, 0.0], fov_deg=45.0),
            subject=SubjectProxyData(proxy_type=ProxyType.SPHERE, position=[0.0, 0.0, 0.0], dimensions=[0.25, 0.25, 0.25],
                                     material=MaterialData(roughness=r, metallic=1.0, base_color=[0.95, 0.95, 0.95])),
            receiver=ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=-0.35),
            lights=[],
            environment=EnvironmentData(enabled=True, intensity=1.0, rotation_deg=0.0),
            render_settings=RenderSettingsData(quality=RenderQuality.FINAL, preview_samples=25, enable_specular=True)
        )
        res_m = mb.render(scene_m, img, depth, normals, sphere_mask)
        canvas_m = (res_m["relit_srgb"] * 255.0).astype(np.uint8)
        cv2.putText(canvas_m, f"Metal r={r:.2f}", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        metal_tiles.append(canvas_m)

        # Dielectric Plastic
        scene_d = StudioScene(
            camera=CameraData(pos=[0.0, 0.0, 2.0], target=[0.0, 0.0, 0.0], fov_deg=45.0),
            subject=SubjectProxyData(proxy_type=ProxyType.SPHERE, position=[0.0, 0.0, 0.0], dimensions=[0.25, 0.25, 0.25],
                                     material=MaterialData(roughness=r, metallic=0.0, base_color=[0.8, 0.1, 0.1], specular_f0=0.04)),
            receiver=ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=-0.35),
            lights=[],
            environment=EnvironmentData(enabled=True, intensity=1.0, rotation_deg=0.0),
            render_settings=RenderSettingsData(quality=RenderQuality.FINAL, preview_samples=25, enable_specular=True)
        )
        res_d = mb.render(scene_d, img, depth, normals, sphere_mask)
        canvas_d = (res_d["relit_srgb"] * 255.0).astype(np.uint8)
        cv2.putText(canvas_d, f"Dielectric r={r:.2f}", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        dielectric_tiles.append(canvas_d)

    row_metal = np.hstack(metal_tiles)
    row_dielectric = np.hstack(dielectric_tiles)
    board = np.vstack([row_metal, row_dielectric])

    board_path = os.path.join(BOARDS_DIR, "dual_sphere_roughness_matrix_board.png")
    cv2.imwrite(board_path, cv2.cvtColor(board, cv2.COLOR_RGB2BGR))
    print(f"[SAVED DUAL-SPHERE MATRIX BOARD] {board_path}")


if __name__ == "__main__":
    run_performance_benchmarks()
    run_photographic_evaluation_and_visual_boards()
    run_sphere_matrix_board()

