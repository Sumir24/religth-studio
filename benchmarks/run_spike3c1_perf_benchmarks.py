"""
RELIGHT STUDIO — RS-SPIKE-3C.1: MULTI-LIGHT HARDWARE PERFORMANCE BENCHMARK
===========================================================================
Measures actual Apple Silicon (M5) multi-light compute performance:
  • Resolutions: 384x256 (Draft), 1024x576 (Viewport), 1920x1080 (Full HD)
  • Light counts: 1, 2, 3, 4 lights
  • Modes: PREVIEW (4 samples/light), FINAL (25 samples/light)
  • Metrics: Host Wall Latency (P50, P95, P99, Mean), GPU Kernel Time, Throughput FPS
  • Buffer Pool Invariant: Persistent buffer allocations in steady state
Saves authoritative JSON to metal2/benchmark_results/multilight_performance_results.json
"""

import os
import json
import time
import numpy as np

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, EnergyConvention, RenderQuality
)
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture

OUTPUT_JSON = "metal2/benchmark_results/multilight_performance_results.json"
os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)


def run_benchmarks():
    print("="*80)
    print("RELIGHT STUDIO — RS-SPIKE-3C.1: MULTI-LIGHT HARDWARE PERFORMANCE BENCHMARKS")
    print("Measuring Real Host Wall-Clock Latency & GPU Kernel Execution on Apple M5")
    print("="*80)

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

        for num_lights in [1, 2, 3, 4]:
            scene = StudioScene.from_json(scene_base.to_json())
            
            # Setup num_lights
            # Light 1: Key
            scene.lights[0].name = "Key Softbox"
            scene.lights[0].position = [1.2, 1.8, 1.5]
            scene.lights[0].intensity = 1.2
            
            # Additional lights
            lights_def = [
                ("Fill Softbox", [-1.5, 1.2, 1.0], [-25.0, -35.0, 0.0], 0.6, 3200.0),
                ("Rim Kicker", [0.0, 2.2, -1.8], [45.0, 180.0, 0.0], 1.2, 6500.0),
                ("Top Softbox", [0.0, 2.8, 0.0], [-90.0, 0.0, 0.0], 0.5, 5000.0)
            ]
            for i in range(num_lights - 1):
                name, pos, rot, intensity, cct = lights_def[i]
                l = scene.add_light()
                l.name = name
                l.position = pos
                l.rotation_deg = rot
                l.intensity = intensity
                l.temperature_kelvin = cct

            # Warmup iterations
            for _ in range(5):
                mb.render(scene, img, depth, norm, fg, quality=quality)

            wall_times = []
            gpu_times = []

            iterations = 20
            for _ in range(iterations):
                t0 = time.time()
                res = mb.render(scene, img, depth, norm, fg, quality=quality)
                wall_times.append((time.time() - t0) * 1000.0)
                gpu_times.append(res["diagnostics"]["gpu_time_ms"])

            p50_wall = float(np.percentile(wall_times, 50))
            p95_wall = float(np.percentile(wall_times, 95))
            p99_wall = float(np.percentile(wall_times, 99))
            mean_wall = float(np.mean(wall_times))
            p50_gpu = float(np.percentile(gpu_times, 50))
            fps = 1000.0 / p50_wall

            pool_stats = mb.bridge.get_buffer_pool_stats()

            entry = {
                "config": res_name,
                "width": W,
                "height": H,
                "quality": quality.value,
                "spp_per_light": spp,
                "num_lights": num_lights,
                "host_p50_ms": round(p50_wall, 2),
                "host_p95_ms": round(p95_wall, 2),
                "host_p99_ms": round(p99_wall, 2),
                "host_mean_ms": round(mean_wall, 2),
                "gpu_p50_ms": round(p50_gpu, 2),
                "throughput_fps": round(fps, 1),
                "buffer_pool_alloc_count": pool_stats["alloc_count"],
                "buffer_pool_steady_frames": pool_stats["steady_frames"]
            }
            all_results.append(entry)

            print(f"  [{num_lights} Light(s)]: Host P50={p50_wall:.2f}ms, P95={p95_wall:.2f}ms | GPU Kernel={p50_gpu:.2f}ms | Throughput={fps:.1f} FPS")

    with open(OUTPUT_JSON, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n[SAVED] Benchmark Results -> {OUTPUT_JSON}")
    return all_results


if __name__ == "__main__":
    run_benchmarks()
