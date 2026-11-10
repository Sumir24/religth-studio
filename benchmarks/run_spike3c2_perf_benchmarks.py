"""
RELIGHT STUDIO — RS-SPIKE-3C.2: MATERIAL & SPECULAR HARDWARE PERFORMANCE BENCHMARK
==================================================================================
Measures actual Apple Silicon (M5 GPU) compute latency & throughput:
  • Resolutions: 384x256 (Draft), 1024x576 (Viewport), 1920x1080 (Full HD)
  • Light counts: 1, 2, 4, 8 lights
  • Material Modes:
      1. Diffuse-Only (Baseline RS-SPIKE-3C.1 comparison)
      2. Diffuse + Microfacet Specular (Dielectric Plastic Profile)
      3. Full Conductor Metal (Rough Metal Profile)
  • Measures: Host Wall-clock P50, P95, P99, Mean, FPS, GPU Kernel Execution, Memory
Saves authoritative JSON to metal2/benchmark_results/material_performance_results.json
"""

import os
import json
import time
import numpy as np

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, RenderQuality
)
from studio3a.material import MaterialData
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture

OUTPUT_JSON = "metal2/benchmark_results/material_performance_results.json"
os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)


def run_material_benchmarks():
    print("=" * 80)
    print("RELIGHT STUDIO — RS-SPIKE-3C.2: MATERIAL & BRDF PERFORMANCE BENCHMARKS")
    print("Measuring Real Host Latency & GPU Kernel Execution on Apple Silicon (M5)")
    print("=" * 80)

    mb = MetalRenderBackend()
    dev_info = mb.bridge.get_device_info()
    print(f"[DEVICE] {dev_info['device_name']}, Unified Memory: {dev_info['has_unified_memory']}")

    resolutions = [
        ("Draft (384x256)", 384, 256, RenderQuality.PREVIEW, 4),
        ("Viewport Preview (1024x576)", 1024, 576, RenderQuality.PREVIEW, 4),
        ("Viewport Final (1024x576)", 1024, 576, RenderQuality.FINAL, 25),
        ("Full HD Preview (1920x1080)", 1920, 1080, RenderQuality.PREVIEW, 4),
        ("Full HD Final (1920x1080)", 1920, 1080, RenderQuality.FINAL, 25),
    ]

    all_results = []

    for res_name, W, H, quality, spp in resolutions:
        print(f"\n--- Benchmarking Resolution: {res_name} ---")
        scene_base, img, depth, norm, fg, rec, _ = generate_scene_fixture(
            "cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE, H=H, W=W
        )

        for num_lights in [1, 2, 4, 8]:
            scene = StudioScene.from_json(scene_base.to_json())
            scene.render_settings.preview_samples = spp
            scene.render_settings.final_samples = spp

            # Key light
            scene.lights[0].name = "Key Softbox"
            scene.lights[0].position = [1.2, 1.8, 1.5]
            scene.lights[0].intensity = 1.2

            # Additional lights up to 8
            extra_lights_defs = [
                ("Fill Softbox", [-1.5, 1.2, 1.0], [-25.0, -35.0, 0.0], 0.6, 3200.0),
                ("Rim Kicker", [0.0, 2.2, -1.8], [45.0, 180.0, 0.0], 1.2, 6500.0),
                ("Top Softbox", [0.0, 2.8, 0.0], [-90.0, 0.0, 0.0], 0.5, 5000.0),
                ("Left Accent", [-2.0, 0.8, -0.5], [10.0, 90.0, 0.0], 0.8, 4000.0),
                ("Right Accent", [2.0, 0.8, -0.5], [10.0, -90.0, 0.0], 0.8, 4000.0),
                ("Floor Bounce", [0.0, 0.1, 1.0], [45.0, 0.0, 0.0], 0.4, 3000.0),
                ("Back Rim 2", [-0.8, 2.0, -2.0], [40.0, 160.0, 0.0], 0.7, 7000.0),
            ]

            for i in range(num_lights - 1):
                name, pos, rot, intensity, cct = extra_lights_defs[i]
                l = scene.add_light()
                l.name = name
                l.position = pos
                l.rotation_deg = rot
                l.intensity = intensity
                l.temperature_kelvin = cct

            modes = [
                ("Diffuse_Only", False, MaterialData()),
                ("Diffuse_Plus_Specular", True, MaterialData.plastic()),
                ("Rough_Metal", True, MaterialData.rough_metal()),
            ]

            for mode_name, enable_spec, mat in modes:
                scene.subject.material = mat
                scene.render_settings.enable_specular = enable_spec
                scene.render_settings.specular_only = False

                # Warmup iterations
                for _ in range(3):
                    mb.render(scene, img, depth, norm, fg, quality=quality)

                # Reset buffer pool stats after warmup to measure steady state
                mb.bridge.reset_buffer_pool()
                # Run 1 frame to initialize persistent pool
                mb.render(scene, img, depth, norm, fg, quality=quality)

                n_iter = 20
                wall_times = []
                gpu_times = []

                for _ in range(n_iter):
                    t0 = time.time()
                    res = mb.render(scene, img, depth, norm, fg, quality=quality)
                    dt_wall = (time.time() - t0) * 1000.0
                    wall_times.append(dt_wall)
                    gpu_times.append(res["diagnostics"]["gpu_time_ms"])

                pool_stats = mb.bridge.get_buffer_pool_stats()
                # Steady allocations must be 0
                assert pool_stats["alloc_count"] == 1, f"Buffer pool resized unexpectedly: {pool_stats}"

                p50 = float(np.percentile(wall_times, 50))
                p95 = float(np.percentile(wall_times, 95))
                p99 = float(np.percentile(wall_times, 99))
                mean_wall = float(np.mean(wall_times))
                mean_gpu = float(np.mean(gpu_times))
                fps = round(1000.0 / mean_wall, 1)

                print(
                    f"  [{mode_name:22s}] {num_lights} Lights: "
                    f"Wall P50={p50:5.2f}ms | P95={p95:5.2f}ms | GPU={mean_gpu:5.2f}ms | "
                    f"FPS={fps:5.1f} | Allocations={pool_stats['alloc_count']}"
                )

                all_results.append({
                    "resolution": res_name,
                    "width": W,
                    "height": H,
                    "quality": quality.value,
                    "spp_per_light": spp,
                    "num_lights": num_lights,
                    "mode": mode_name,
                    "wall_p50_ms": round(p50, 2),
                    "wall_p95_ms": round(p95, 2),
                    "wall_p99_ms": round(p99, 2),
                    "wall_mean_ms": round(mean_wall, 2),
                    "gpu_mean_ms": round(mean_gpu, 2),
                    "fps": fps,
                    "buffer_pool_alloc_count": pool_stats["alloc_count"],
                    "buffer_pool_steady_frames": pool_stats["steady_frames"],
                })

    with open(OUTPUT_JSON, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n[BENCHMARK COMPLETE] Saved results to {OUTPUT_JSON}")
    print("=" * 80)


if __name__ == "__main__":
    run_material_benchmarks()
