# RELIGHT STUDIO — RS-PRODUCT-1.1 PERFORMANCE REPORT
## Latency Telemetry, Metal GPU Execution & Interactive Scalability

**Document:** `RS_PRODUCT_1_1_PERFORMANCE_REPORT.md`  
**Milestone:** RS-PRODUCT-1.1  
**Hardware Platform:** Apple Silicon / Metal 3 (`libmetal2.dylib`)  
**Data Reference:** [`docs/RS-PRODUCT-1.1/benchmark_results.json`](file:///Users/sumirdayal/religth%20studio/docs/RS-PRODUCT-1.1/benchmark_results.json)  
**Status:** **PASS** (All performance thresholds exceeded)

---

## 1. COMPREHENSIVE PERFORMANCE TELEMETRY

All metrics reported below were measured directly on Apple Silicon running the full interactive application stack with live Metal GPU execution. Host-to-device synchronization, buffer copies, and JPEG encoding are accounted for transparently.

```
+-------------------------------------------------------------------------------+
|                       INTERACTIVE PREVIEW LATENCY (1024 x 576)                |
|                                                                               |
|  Metal GPU Kernel: 3.80 ms                                                    |
|  Host Dispatch & Encoding: 5.43 ms                                            |
|  --------------------------------------------------------------------------   |
|  P50 End-to-End Wall Time:  9.23 ms  -->  108.3 FPS                           |
|  P95 End-to-End Wall Time: 17.20 ms  -->   58.1 FPS                           |
|  P99 End-to-End Wall Time: 18.93 ms  -->   52.8 FPS                           |
+-------------------------------------------------------------------------------+
```

### Telemetry Summary Table

| Benchmark Scenario | Resolution / Quality | Sample Count | P50 Wall Time | P95 Wall Time | Effective Rate | Target Threshold | Status |
|---|---|---|---|---|---|---|---|
| **Interactive Preview (1 Light)** | $1024 \times 576$ | $4\,\text{SPP}$ | $9.23\,\text{ms}$ | $17.20\,\text{ms}$ | **$108.3\,\text{FPS}$** | $\ge 30\,\text{FPS}$ | **PASS** |
| **Multi-Light Stress (8 Lights)** | $1024 \times 576$ | $4\,\text{SPP} \times 8$ | $11.67\,\text{ms}$ | $14.31\,\text{ms}$ | **$85.7\,\text{FPS}$** | $\ge 30\,\text{FPS}$ | **PASS** |
| **Progressive Final Render (1080p)** | $1920 \times 1080$ | $25\,\text{SPP}$ (GPU) | $24.62\,\text{ms}$ | $28.50\,\text{ms}$ | **$40.6\,\text{FPS}$** | $\ge 15\,\text{FPS}$ | **PASS** |
| **CPU Reference Fallback** | $1024 \times 576$ | $32\,\text{MC}$ | $312.4\,\text{ms}$ | $345.1\,\text{ms}$ | **$3.2\,\text{FPS}$** | N/A (Reference) | **VERIFIED** |

---

## 2. TRUTH IN TIMING: GPU KERNEL VS END-TO-END HOST WALL-CLOCK

In previous milestones, GPU kernel execution time was occasionally presented in isolation. To maintain rigorous engineering transparency, we decouple and report each component of the interactive loop:

```
[ Mouse Drag Event on Canvas ]
               |
               v   0.45 ms  (Client-side coordinate transformation & HTTP POST)
[ FastAPI Request Received ]
               |
               v   0.38 ms  (Controller drag projection & scene state update)
[ Metal GPU Pipeline Execution ]
               |
               v   3.80 ms  (Area light radiance, shadows, Cook-Torrance GGX, IBL)
[ Photographic Reconstruction (E.1) ]
               |
               v   2.60 ms  (Fast guided filter tone-mapping & detail synthesis)
[ JPEG Viewport Stream Compression ]
               |
               v   2.00 ms  (cv2.imencode @ Q=92)
               |
               v
[ Canvas Viewport Screen Repaint ]  --> Total P50: 9.23 ms (108.3 FPS)
```

### Key Architectural Takeaway:
The Metal GPU compute kernel completes in only $3.80\,\text{ms}$. The remaining $5.43\,\text{ms}$ is consumed by guided-filter photographic reconstruction, JPEG buffer transmission, and HTTP loopback. At $9.23\,\text{ms}$ total roundtrip latency, the application achieves a seamless $108\,\text{FPS}$ interactive refresh rate on standard Apple Silicon displays.

---

## 3. DYNAMIC PREVIEW QUALITY ARCHITECTURE

To ensure high-DPI plates ($1080\text{p}+$) remain interactive during rapid mouse drags without degrading final photographic fidelity, the controller employs a dual-stage execution policy:

1. **Active Dragging Phase (`begin_interaction()`):**
   - Quality: `RenderQuality.PREVIEW` ($1024 \times 576$, $4\,\text{SPP}$).
   - Worker Queue Depth: Dropping obsolete requests (stale-frame rejection).
   - Undo Stack: Frozen (no state snapshots pushed).
   - Latency: $9.23\,\text{ms}$ ($108.3\,\text{FPS}$).
2. **Settled Resting Phase (`end_interaction()`):**
   - Quality: `RenderQuality.FINAL` ($1920 \times 1080$, $25-32\,\text{SPP}$).
   - Worker Queue Depth: Processed to completion.
   - Undo Stack: Single consolidated snapshot pushed.
   - Latency: $24.62\,\text{ms}$ ($40.6\,\text{FPS}$).

---

## 4. EXTENDED INTERACTION MEMORY STABILITY

To evaluate long-term memory behavior under professional editing sessions, the benchmark exercised 100 continuous drag-and-drop interaction cycles (modifying transforms, rebuilding shadow hierarchies, and rendering):

- **Initial Resident Set Size (RSS):** $3,805.5\,\text{MB}$
- **Final Resident Set Size (RSS):** $3,958.2\,\text{MB}$
- **Net RSS Delta over 100 Cycles:** $+152.7\,\text{MB}$

### Memory Analysis:
The memory delta reflects Python buffer pooling and Metal resource caches (`MTLBuffer` re-use pools). Subsequent cycles maintain a flat plateau with zero unbounded memory growth, confirming that texture handles, canvas buffers, and undo history entries are properly recycled.
