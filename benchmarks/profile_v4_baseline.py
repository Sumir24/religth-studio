"""
Baseline Performance Profiling Suite for Relight Studio Engine v4
Milestone 5: Interactive Rendering Runtime (IRR) - Phase 1

Measures stage-level latency (median, p95), memory footprint (peak, allocation volume via tracemalloc),
and output quality across:
- Portrait and Product photography
- 1 MP, 4 MP, and 12 MP resolutions
- Directional, Point, Spot, Area (Softbox), Ring, Rim lights
- Single-light and multi-light studio rigs
- Material presets (matte, satin, glossy)
"""

import os
import sys
import time
import json
import tracemalloc
import gc
from typing import Dict, List, Any, Tuple
import cv2
import numpy as np

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine.relighter_v4 as v4


def get_memory_stats(func, *args, **kwargs) -> Tuple[Any, float, float]:
    """Runs func with tracemalloc and returns (result, peak_mb, alloc_mb)."""
    gc.collect()
    tracemalloc.reset_peak()
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()
    
    result = func(*args, **kwargs)
    
    snapshot2 = tracemalloc.take_snapshot()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Calculate total allocations from snapshot stats
    alloc_bytes = sum(stat.size for stat in snapshot2.compare_to(snapshot1, 'lineno') if stat.size_diff > 0)
    peak_mb = peak / (1024 * 1024)
    alloc_mb = alloc_bytes / (1024 * 1024)
    return result, peak_mb, alloc_mb


def benchmark_function(func, args, kwargs=None, iterations=5, warmup=1):
    """Measures median and p95 latency in milliseconds."""
    kwargs = kwargs or {}
    # Warmup
    for _ in range(warmup):
        _ = func(*args, **kwargs)
    
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        _ = func(*args, **kwargs)
        t1 = time.perf_counter_ns()
        times.append((t1 - t0) / 1e6) # ms
    
    times.sort()
    median_ms = float(np.median(times))
    p95_idx = int(math.ceil(0.95 * len(times))) - 1
    p95_ms = float(times[min(p95_idx, len(times) - 1)])
    return median_ms, p95_ms


import math

def prepare_scaled_images(base_paths: Dict[str, str], target_mps: Dict[str, int]) -> Dict[str, Dict[str, np.ndarray]]:
    """Generates 1 MP, 4 MP, and 12 MP test images for portrait and product."""
    scaled = {}
    for genre, path in base_paths.items():
        scaled[genre] = {}
        srgb = v4.load_srgb(path)
        h, w = srgb.shape[:2]
        aspect = w / h
        
        for mp_name, target_pixels in target_mps.items():
            target_h = int(round(math.sqrt(target_pixels / aspect)))
            target_w = int(round(target_h * aspect))
            im_resized = cv2.resize(srgb, (target_w, target_h), interpolation=cv2.INTER_AREA if target_pixels < (h*w) else cv2.INTER_LINEAR)
            scaled[genre][mp_name] = im_resized
            print(f"  [Dataset] {genre} @ {mp_name}: shape={im_resized.shape} ({(im_resized.shape[0]*im_resized.shape[1])/1e6:.2f} MP)")
    return scaled


def run_stage_profiling(scaled_images: Dict[str, Dict[str, np.ndarray]]) -> Dict[str, Any]:
    """Instruments every individual pipeline stage in Engine v4."""
    print("\n--- Running Stage-Level Profiling ---")
    results = {}
    
    p = v4.Params(lam=0.7, strength=1.0)
    
    # We will test stage-level breakdown at 1 MP on Product
    im_1mp = scaled_images["product"]["1MP"]
    H, W = im_1mp.shape[:2]
    
    # 1. prepare_scene
    _, peak_prep, alloc_prep = get_memory_stats(v4.prepare_scene, im_1mp, p)
    med_prep, p95_prep = benchmark_function(v4.prepare_scene, (im_1mp, p), iterations=5)
    
    sc = v4.prepare_scene(im_1mp, p)
    
    # 2. guided_filter (on logY)
    r_base = max(4, int(round(p.base_radius_frac * sc.long)))
    _, peak_gf, alloc_gf = get_memory_stats(v4.guided_filter, sc.base_gamma, np.log(sc.Y), r_base, p.base_eps)
    med_gf, p95_gf = benchmark_function(v4.guided_filter, (sc.base_gamma, np.log(sc.Y), r_base, p.base_eps), iterations=5)
    
    # 3. masked_guided
    r_ratio = max(8, int(round(p.ratio_radius_frac * sc.long)))
    dummy_logR = np.random.uniform(-0.5, 0.5, (H, W)).astype(np.float32)
    _, peak_mg, alloc_mg = get_memory_stats(v4.masked_guided, sc.base_gamma, dummy_logR, sc.mask, r_ratio, p.ratio_eps_guided)
    med_mg, p95_mg = benchmark_function(v4.masked_guided, (sc.base_gamma, dummy_logR, sc.mask, r_ratio, p.ratio_eps_guided), iterations=5)
    
    # 4. contact_shadow
    l_vec = np.array([0.7, -0.3, 0.5], np.float32)
    l_field = np.broadcast_to(l_vec, (H, W, 3))
    _, peak_cs, alloc_cs = get_memory_stats(v4.contact_shadow, sc.h, l_field, p.shadow_steps, p.shadow_dist_frac, 0.03 * sc.S, p.shadow_target_px)
    med_cs, p95_cs = benchmark_function(v4.contact_shadow, (sc.h, l_field, p.shadow_steps, p.shadow_dist_frac, 0.03 * sc.S, p.shadow_target_px), iterations=5)
    
    # 5. shade (directional vs area softbox)
    lt_dir = [v4.L("directional", 270, 30, intensity=1.1)]
    _, peak_shade_dir, alloc_shade_dir = get_memory_stats(v4.shade, sc, lt_dir, p.ambient_new, p, True, True)
    med_shade_dir, p95_shade_dir = benchmark_function(v4.shade, (sc, lt_dir, p.ambient_new, p, True, True), iterations=5)
    
    lt_area = [v4.L("area", 290, 35, distance=1.3, size=(0.9, 0.7), intensity=1.2, samples=3)]
    _, peak_shade_area, alloc_shade_area = get_memory_stats(v4.shade, sc, lt_area, p.ambient_new, p, True, True)
    med_shade_area, p95_shade_area = benchmark_function(v4.shade, (sc, lt_area, p.ambient_new, p, True, True), iterations=5)
    
    # 6. relight_scene (end to end with cached scene)
    _, peak_relight, alloc_relight = get_memory_stats(v4.relight_scene, sc, lt_dir, None, p)
    med_relight, p95_relight = benchmark_function(v4.relight_scene, (sc, lt_dir, None, p), iterations=5)
    res = v4.relight_scene(sc, lt_dir, None, p)
    
    # 7. compute_metrics
    _, peak_metrics, alloc_metrics = get_memory_stats(v4.compute_metrics, im_1mp, res, p)
    med_metrics, p95_metrics = benchmark_function(v4.compute_metrics, (im_1mp, res, p), iterations=5)
    m = v4.compute_metrics(im_1mp, res, p)
    
    # 8. quality_gate
    _, peak_qg, alloc_qg = get_memory_stats(v4.quality_gate, m)
    med_qg, p95_qg = benchmark_function(v4.quality_gate, (m,), iterations=5)
    
    # 9. ratio_transfer
    dummy_gen = cv2.GaussianBlur(im_1mp, (0, 0), 15.0)
    _, peak_rt, alloc_rt = get_memory_stats(v4.ratio_transfer, im_1mp, dummy_gen, p)
    med_rt, p95_rt = benchmark_function(v4.ratio_transfer, (im_1mp, dummy_gen, p), iterations=5)

    results = {
        "prepare_scene": {"median_ms": med_prep, "p95_ms": p95_prep, "peak_mb": peak_prep, "alloc_mb": alloc_prep},
        "guided_filter": {"median_ms": med_gf, "p95_ms": p95_gf, "peak_mb": peak_gf, "alloc_mb": alloc_gf},
        "masked_guided": {"median_ms": med_mg, "p95_ms": p95_mg, "peak_mb": peak_mg, "alloc_mb": alloc_mg},
        "contact_shadow": {"median_ms": med_cs, "p95_ms": p95_cs, "peak_mb": peak_cs, "alloc_mb": alloc_cs},
        "shade_directional": {"median_ms": med_shade_dir, "p95_ms": p95_shade_dir, "peak_mb": peak_shade_dir, "alloc_mb": alloc_shade_dir},
        "shade_area_3x3": {"median_ms": med_shade_area, "p95_ms": p95_shade_area, "peak_mb": peak_shade_area, "alloc_mb": alloc_shade_area},
        "relight_scene": {"median_ms": med_relight, "p95_ms": p95_relight, "peak_mb": peak_relight, "alloc_mb": alloc_relight},
        "compute_metrics": {"median_ms": med_metrics, "p95_ms": p95_metrics, "peak_mb": peak_metrics, "alloc_mb": alloc_metrics},
        "quality_gate": {"median_ms": med_qg, "p95_ms": p95_qg, "peak_mb": peak_qg, "alloc_mb": alloc_qg},
        "ratio_transfer": {"median_ms": med_rt, "p95_ms": p95_rt, "peak_mb": peak_rt, "alloc_mb": alloc_rt},
    }
    return results


def run_matrix_benchmark(scaled_images: Dict[str, Dict[str, np.ndarray]]) -> List[Dict[str, Any]]:
    """Runs full matrix benchmark across genres, resolutions, light types, rigs, and materials."""
    print("\n--- Running Full Resolution & Configuration Matrix ---")
    
    light_configs = {
        "directional": [v4.L("directional", 270, 30, intensity=1.1, kelvin=5600)],
        "point": [v4.L("point", 300, 35, distance=1.0, intensity=1.4, kelvin=3000, k2=0.8, pool=0.6)],
        "spot": [v4.L("spot", 300, 40, distance=1.3, intensity=1.9, kelvin=3800, cone_outer_deg=30, pool=0.5)],
        "area_softbox": [v4.L("area", 290, 35, distance=1.3, size=(0.9, 0.7), intensity=1.2, samples=3, kelvin=5600)],
        "ring": [v4.L("ring", 90, 90, distance=1.2, size=(0.45, 0.45), intensity=1.0, kelvin=5600)],
        "rim": [v4.L("rim", 100, -25, intensity=1.5, kelvin=8000)],
        "multi_warm_key_cool_rim": v4.PRESETS["warm_key_cool_rim"],
        "multi_three_point": v4.PRESETS["three_point"]
    }
    
    records = []
    
    for genre in ["product", "portrait"]:
        for mp_name in ["1MP", "4MP", "12MP"]:
            im = scaled_images[genre][mp_name]
            h, w = im.shape[:2]
            pixels = h * w
            
            p = v4.Params(lam=0.7, strength=1.0, **v4.MATERIALS["satin"])
            
            # 1. Measure prepare_scene at this resolution
            iters = 1 if mp_name == "12MP" else (2 if mp_name == "4MP" else 3)
            warmup = 0 if mp_name == "12MP" else 1
            t_prep_med, t_prep_p95 = benchmark_function(v4.prepare_scene, (im, p), iterations=iters, warmup=warmup)
            _, prep_peak, prep_alloc = get_memory_stats(v4.prepare_scene, im, p)
            sc = v4.prepare_scene(im, p)
            
            for cfg_name, lights in light_configs.items():
                print(f"  Testing {genre} | {mp_name} | {cfg_name}...")
                
                # Measure interactive relight with cached scene (simulate warm slider drag)
                def warm_run():
                    return v4.relight_scene(sc, lights, None, p)
                
                t_warm_med, t_warm_p95 = benchmark_function(warm_run, (), iterations=iters, warmup=warmup)
                res, warm_peak, warm_alloc = get_memory_stats(warm_run)
                
                # Measure metrics on output
                m = v4.compute_metrics(im, res, p)
                
                rec = {
                    "genre": genre,
                    "resolution": mp_name,
                    "dimensions": f"{w}x{h}",
                    "megapixels": round(pixels / 1e6, 2),
                    "light_config": cfg_name,
                    "prepare_scene_ms": round(t_prep_med, 1),
                    "warm_relight_median_ms": round(t_warm_med, 1),
                    "warm_relight_p95_ms": round(t_warm_p95, 1),
                    "fps_interactive": round(1000.0 / max(t_warm_med, 1.0), 1),
                    "peak_memory_mb": round(warm_peak, 1),
                    "alloc_volume_mb": round(warm_alloc, 1),
                    "detail_lock_err": round(m["detail_lock_error_log"], 4),
                    "banding_gain": round(m["banding_gain"], 4),
                }
                records.append(rec)
    return records


def main():
    print("=== Relight Studio Engine v4: Baseline Performance Profiling Suite ===")
    
    os.makedirs("demo_output/milestone5", exist_ok=True)
    
    base_paths = {
        "product": "demo_output/nike_sample.jpg",
        "portrait": "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794143824741_478ce89a.jpg"
    }
    
    target_mps = {
        "1MP": 1_000_000,
        "4MP": 4_000_000,
        "12MP": 12_000_000
    }
    
    scaled_images = prepare_scaled_images(base_paths, target_mps)
    
    # 1. Run stage-level profiling
    stage_profile = run_stage_profiling(scaled_images)
    print("\nStage-Level Latency Breakdown (1 MP Product):")
    for stage, data in stage_profile.items():
        print(f"  {stage:20s}: Median={data['median_ms']:6.2f} ms | P95={data['p95_ms']:6.2f} ms | Peak={data['peak_mb']:6.1f} MB | Alloc={data['alloc_mb']:6.1f} MB")
        
    # 2. Run full configuration matrix
    matrix_records = run_matrix_benchmark(scaled_images)
    
    output_data = {
        "environment": {
            "python_version": sys.version,
            "platform": sys.platform,
            "engine": "Relight Studio v4.0 Baseline"
        },
        "stage_profile_1mp": stage_profile,
        "matrix_benchmarks": matrix_records
    }
    
    json_path = "demo_output/milestone5/baseline_profile_report.json"
    with open(json_path, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"\n[DONE] Baseline profiling complete. Results saved to {json_path}")


if __name__ == "__main__":
    main()

