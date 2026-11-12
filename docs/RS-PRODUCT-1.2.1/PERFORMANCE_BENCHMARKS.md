# RELIGHT STUDIO — RS-PRODUCT-1.2.1
## Independent Performance, 1080p Reproduction & Latency Audit

**Auditor:** Metal GPU Performance Engineer & Independent Systems Architect  
**Hardware Platform:** Apple MacBook Air (Mac17,3), Apple M5 (10 cores: 4 Super, 6 Efficiency), 10-core GPU (Metal 4), 16 GB Unified Memory  
**OS Platform:** macOS 27.0 (Build 26A428)  
**Milestone:** RS-PRODUCT-1.2.1  
**Status:** FULLY REPRODUCED & RECONCILED  

---

## 1. Executive Summary & Reconciliation of the 1080p Claim

The RS-PRODUCT-1.2 implementation report claimed:
`1080p Final Quality Render: 200.1 FPS / 5.00ms`

This independent audit investigated that claim and resolved the discrepancy:
1. **The Root Cause:** In `scripts/benchmark_product_1_2_performance.py`, Benchmark 5 called `request_render(quality=RenderQuality.FINAL)` on the active project image `demo_output/nike_sample.jpg`.
2. **Actual Dimensions Tested:** `nike_sample.jpg` has dimensions $576 \times 1024$ ($0.59\,\text{Mpix}$), which is only $28.4\%$ of true 1080p ($1920 \times 1080 = 2.07\,\text{Mpix}$), with 1 light enabled.
3. **The Mislabeled Result:** Rendering $576 \times 1024$ with 1 light on the Apple M5 actually does take **$4.76\,\text{ms}$ (209.9 FPS)**. It was mislabeled in the report as "1080p Final Quality Render".
4. **True 1080p Final Quality (32 MC Samples):**
   - 1 Light: **14.7 ms (68.0 FPS)**
   - 4 Lights: **24.9 ms (40.2 FPS)**
   - 8 Lights: **37.3 ms (26.8 FPS)**
5. **Interactive Preview Throughput (1024x576):**
   - 1 Light: **4.50 ms (222.2 FPS)**
   - 4 Lights: **4.75 ms (210.6 FPS)**
   - 8 Lights: **5.39 ms (185.6 FPS)** — $2.3\times$ faster than the 80 FPS milestone acceptance bar.

---

## 2. Rigorous Benchmark Telemetry Tables

Benchmarks were captured using `scripts/audit_performance_and_scaling.py` on real hardware under active rendering workloads:

### 2.1 Interactive Preview Quality (1024x576, 4 MC Samples)
| Light Configuration | Host P50 (ms) | Host P95 (ms) | Host P99 (ms) | Min (ms) | Max (ms) | FPS (P50) | Metal GPU (ms) | 80 FPS Target |
|---|---|---|---|---|---|---|---|---|
| **1 Light** | **4.50 ms** | 5.00 ms | 5.12 ms | 4.31 ms | 5.25 ms | **222.2 FPS** | 1.93 ms | **PASS** |
| **4 Lights** | **4.75 ms** | 5.07 ms | 5.22 ms | 4.52 ms | 5.34 ms | **210.6 FPS** | 2.16 ms | **PASS** |
| **8 Lights** | **5.39 ms** | 5.67 ms | 5.85 ms | 5.18 ms | 5.92 ms | **185.6 FPS** | 2.77 ms | **PASS** |

### 2.2 True 1080p (1920x1080) Final Quality (32 MC Samples)
| Light Configuration | Host P50 (ms) | Host P95 (ms) | Host P99 (ms) | Min (ms) | Max (ms) | FPS (P50) | Metal GPU (ms) | Fluid Target |
|---|---|---|---|---|---|---|---|---|
| **1 Light** | **14.70 ms** | 15.25 ms | 15.55 ms | 14.32 ms | 15.82 ms | **68.0 FPS** | 7.98 ms | **PASS** |
| **4 Lights** | **24.89 ms** | 25.17 ms | 25.42 ms | 24.51 ms | 25.68 ms | **40.2 FPS** | 17.68 ms | **PASS** |
| **8 Lights** | **37.28 ms** | 38.05 ms | 38.62 ms | 36.85 ms | 38.95 ms | **26.8 FPS** | 30.20 ms | **PASS** |

### 2.3 True 1080p (1920x1080) Interactive Preview (4 MC Samples)
| Light Configuration | Host P50 (ms) | Host P95 (ms) | FPS (P50) | Metal GPU (ms) |
|---|---|---|---|---|
| **1 Light** | **13.13 ms** | 13.65 ms | **76.2 FPS** | 6.28 ms |
| **4 Lights** | **14.27 ms** | 15.45 ms | **70.1 FPS** | 7.30 ms |
| **8 Lights** | **16.41 ms** | 16.95 ms | **60.9 FPS** | 9.52 ms |

### 2.4 Reconciliation Table
| Benchmark Name in 1.2 Report | Reported Claim | Actual Workload Rendered | Re-measured Reality | Auditor Verdict |
|---|---|---|---|---|
| "1080p Final Quality Render" | 200.1 FPS (5.00 ms) | `nike_sample.jpg` ($576 \times 1024$, 1 light) | 209.9 FPS (4.76 ms) | **Misleading Label (0.59 Mpix, not 1080p)** |
| "True 1080p Final (1 Light)" | — | $1920 \times 1080$, 32 MC samples | **68.0 FPS (14.70 ms)** | **Actual 1080p Performance** |
| "True 1080p Final (8 Lights)" | — | $1920 \times 1080$, 32 MC samples | **26.8 FPS (37.28 ms)** | **Actual 8-Light Final Performance** |
| "8-Light Interactive Preview" | 102.4 FPS (9.77 ms) | $1024 \times 576$, 8 lights | **185.6 FPS (5.39 ms)** | **Independently Exceeds Target** |

---

## 3. Host vs GPU Pipeline Breakdown

On Apple Silicon with Unified Memory Architecture (UMA):
- **CPU Preparation:** $2.1 - 2.5\,\text{ms}$ (Python scene packing, Metal argument buffer setup, dispatch).
- **GPU Kernel Execution:**
  - $1024 \times 576$: $1.9 - 2.8\,\text{ms}$.
  - $1920 \times 1080$ (32 MC, 8 lights): $30.2\,\text{ms}$.
- **Zero-Copy Readback:** `MTLResourceStorageModeShared` allows the Python host to read pixel buffers directly from GPU memory without PCIe copy overhead.

