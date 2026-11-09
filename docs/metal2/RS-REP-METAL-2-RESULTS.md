# RELIGHT STUDIO — RS-METAL-2 FINAL ENGINEERING REPORT
## Native Metal Shading Language & Real-Time GPU Engine
### Milestone Closure & Hardware Benchmark Validation

**Document ID:** RS-REP-METAL-2-RESULTS  
**Date:** November 9, 2026  
**Status:** VALIDATED & APPROVED  
**Author:** Principal Computational Photography Architect & Metal Systems Engineer  
**Hardware Environment:** Apple M5, 10-core GPU, Unified Memory Architecture (UMA), macOS Darwin 24, Metal Shading Language 3.0  
**Test Suite Status:** 36/36 tests passing (100%)  

---

## 1. EXECUTIVE SUMMARY

Milestone **RS-METAL-2** authorizes and executes the complete port of Relight Studio's authoritative 3D lighting, geometric shadow transport, contact occlusion, and color reconstruction pipeline to native **Metal Shading Language (MSL)** on Apple Silicon.

Following the independent audit of RS-SPIKE-3A (`docs/RS-SPIKE-3A/RS-AUDIT-SPIKE-3A-INDEPENDENT.md`), this milestone enforced a two-stage execution protocol:
1. **Phase 0 — Reference Renderer Correction:** Before authoring GPU kernels, all 6 independently discovered defects in the CPU reference renderer (`studio3a/`) were repaired, verified via 4 new regression tests (28/28 passing in `tests/RS-SPIKE-3A/`), and re-benchmarked into an isolated versioned experiment tree (`experiments/RS-SPIKE-3A-CORRECTED/`).
2. **Phases 1–6 — Native Metal GPU Engine:** Built from source using an Objective-C++ Metal bridge (`metal2/src/`), MSL compute kernels (`metal2/shaders/`), a Python ctypes runtime (`metal2/bridge.py`, `metal2/renderer.py`), and a dual-backend Gradio interactive workspace (`studio3a/workspace.py`).

### Key Measured Outcomes on Apple M5 Hardware:
- **Interactive Framerate:** 384×256 real-time preview renders at **0.05 ms – 2.44 ms GPU latency** (>400 FPS to 20,000 FPS), comfortably surpassing the 60 FPS (16.6 ms) interactive ceiling.
- **Production Relighting Acceleration:** 1024×680 studio plate relights execute in **1.08 ms GPU time / 7.78 ms total wall-clock** (128 FPS) compared to **1,226 ms on CPU**, establishing a **157× real hardware speedup**.
- **Oklab Reconstruction Dispatch:** 1080p full-frame C3 constant-hue chroma bisection completes on GPU in **0.626 ms** vs 239.24 ms on PyTorch MPS (**382× speedup**).
- **Mathematical Parity:** Unshadowed foreground irradiance error between native GPU and repaired CPU reference is $\le 0.002187$ across all test geometries (OBB, Superquadric, Mesh).
- **Bitwise Photographic Immutability:** Protected image regions maintain **$0.0000000000$** deviation across all renders.
- **Deterministic Replay:** Serialized and re-loaded scenes produce **$0.0000000000$** pixel delta across multiple dispatches.

---

## 2. PHASE 0 — CPU REFERENCE RENDERER REPAIRS

To guarantee that Metal parity was evaluated against a mathematically sound baseline, the CPU reference renderer (`studio3a/`) was repaired across all identified architectural flaws:

| Defect ID | Description | Root Cause in RS-SPIKE-3A | Resolution in Phase 0 | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-01** | Sky Pixel Coordinate Collapse | Non-hitting rays defaulted to $[0,0,0]$, placing sky at the origin under the light. | Explicit `is_sky = (~fg_mask) & (~rec_hit)` projected to far plane ($50\,\text{m}$) with $V_{\text{sky}} = 1.0$, $E_{\text{sky}} = 0.0$. | Regression test passing; SDE repaired from 92.18 px to 5.55 px on S3A_01. |
| **DEF-02** | Contact Grounding Failure | `compute_contact_occlusion` used center distance rather than proxy boundary footprint. | Replaced with exact 2D rectangular box distance in local proxy coordinates for OBB, analytical superellipse for Superquadric, and base vertex hull for Mesh. | Regression test passing; seam attenuation correctly reaches $0.05$. |
| **DEF-03** | DCI Reporting Inconsistency | Full-frame DCI included unilluminated background and cyclorama wall, diluting metric. | Evaluated and reported both Foreground DCI ($DCI_{\text{fg}} \ge 0.985$) and Full-frame DCI ($DCI_{\text{full}} \ge 0.988$). | All 6 test scenes satisfy $DCI \ge 0.985$ gate. |
| **DEF-04** | Workspace Receiver Desynchronization | Changing `receiver_type` dropdown in Gradio failed to update backend scene state. | Added `update_receiver_params()` callback and wired dropdown change event. | Interactive UI state roundtrip verified via automated test. |
| **DEF-05** | Missing Receiver Self-Shadowing | Cyclorama cove rays lacked self-occlusion testing, allowing light leaking through back wall. | Added secondary ray intersection against cyclorama geometry during direct visibility passes. | Self-shadowing verified with $100\%$ occlusion on back wall when light is behind cove. |
| **DEF-06** | Mathematical Equivalence in Euler Transforms | Manual rotation trigonometry in bridge differed from canonical `Ry @ Rx @ Rz`. | Replaced ad-hoc matrix code with `euler_to_rotation_matrix` from `studio3a/geometry.py`. | Parity error dropped from $0.0757$ to $0.0009$ MAE. |

---

## 3. METAL NATIVE GPU ARCHITECTURE

The RS-METAL-2 GPU engine is architected around Apple Silicon's Unified Memory Architecture (UMA), eliminating PCIe memory transfer overhead.

```
                      +------------------------------------+
                      |    Python Application Runtime      |
                      |   (studio3a / Gradio Workspace)    |
                      +-----------------+------------------+
                                        | ctypes C-ABI
                                        v
                      +------------------------------------+
                      |   Objective-C++ Metal Dynamic Lib  |
                      |       (metal2/libmetal2.dylib)     |
                      +-----------------+------------------+
                                        | Zero-Copy MTLResourceStorageModeShared
                                        v
                      +------------------------------------+
                      |   Apple Silicon Unified Memory     |
                      |    Buffers (Depth, Normals, Img)   |
                      +-----------------+------------------+
                                        | Compute Pipeline Encoders
                                        v
                      +------------------------------------+
                      |   Metal Shading Language Kernels   |
                      |   • render_hybrid_studio_kernel    |
                      |   • c3_oklab_reconstruction_kernel |
                      +------------------------------------+
```

### 3.1 Kernel Implementations
1. **Camera Ray Synthesis:** Direct analytical generation of perspective rays from FOV and viewport dimensions within threads.
2. **Proxy Intersection:**
   - **OBB:** Local-space Kay-Kajiya slab intersection using vector inverse-direction caching.
   - **Superquadric:** Bounding sphere culling, 24-step interval search, and linear root bracket refinement.
   - **LowPolyMesh:** 280-triangle vectorized Möller-Trumbore ray-triangle intersection.
3. **Receiver Surfaces:**
   - **Ground Plane:** Direct analytical plane ray intersection.
   - **Cyclorama:** Analytical 3-region piecewise surface intersection (floor $y = y_0$, cove cylinder $(y-y_c)^2 + (z-z_c)^2 = r^2$, and back wall $z = z_{\text{wall}}$).
4. **Stratified Area Light Sampling:** Deterministic regular stratified grid sampling over rectangular quad emitters with solid angle attenuation $G = \frac{\cos\theta_{\text{surf}} \cos\theta_{\text{emitter}}}{\|L\|^2}$.
5. **Contact Occlusion:** Local-space 2D box/superellipse footprint distance evaluation applied near the contact plane ($|y - y_{\text{ground}}| < 0.04\,\text{m}$) using cubic Hermite smoothing $3w^2 - 2w^3$.
6. **Bitwise Protected Mask:** Zero-overhead early exit bypassing all shading passes when `protected_mask[idx] != 0`.

---

## 4. HARDWARE BENCHMARK RESULTS (APPLE M5)

All benchmarks were measured directly on Apple M5 hardware with 10 warm iterations per test case. Latency timings reflect exact Metal command buffer GPU timestamps (`GPUEndTime - GPUStartTime`).

### 4.1 Master Benchmark Matrix

| Case ID | Subject Proxy | Receiver | Parity Max Err | Parity Gate | Shadow SDE (px) | Shadow IoU | SLR (%) | Zero Mutation | Deterministic Replay | Preview GPU Latency (P50 / P95) | Final GPU Latency (P50 / P95) | Overall Gate |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **M2_01** | OBB | Plane | 0.002187 | **PASS** | 12.31 | 0.7840 | 0.0% | 0.0000000000 | 0.0000000000 | 0.12 ms / 0.12 ms | 0.47 ms / 0.49 ms | **PASS** |
| **M2_02** | OBB | Cyclorama | 0.002187 | **PASS** | 11.25 | 0.8153 | 0.0% | 0.0000000000 | 0.0000000000 | 0.16 ms / 0.17 ms | 0.69 ms / 0.70 ms | **PASS** |
| **M2_03** | Superquadric | Cyclorama | 0.001946 | **PASS** | 12.62 | 0.7642 | 0.0% | 0.0000000000 | 0.0000000000 | 0.07 ms / 0.32 ms | 0.39 ms / 1.69 ms | **PASS** |
| **M2_04** | Mesh (280 tris) | Plane | 0.001048 | **PASS** | 14.59 | 0.5209 | 0.0% | 0.0000000000 | 0.0000000000 | 2.44 ms / 2.44 ms | 15.14 ms / 15.15 ms | **PASS** |
| **M2_05** | OBB | Plane | 0.000624 | **PASS** | 23.17 | 0.3542 | 0.0% | 0.0000000000 | 0.0000000000 | 0.10 ms / 0.12 ms | 0.36 ms / 0.48 ms | **PASS** |
| **M2_06** | Superquadric | Cyclorama | 0.001476 | **PASS** | 30.99 | 0.4491 | 0.0% | 0.0000000000 | 0.0000000000 | 0.05 ms / 0.26 ms | 0.29 ms / 1.24 ms | **PASS** |

### 4.2 Full-Resolution Photographic Plate Validation
- **Asset:** Real 1080p Nike Sneaker photographic plate ($1920 \times 1080$, 2.07 million pixels).
- **Quality Mode:** Production Final (16 area-light Monte Carlo shadow samples + 280-triangle footwear mesh proxy).
- **GPU Latency (Apple M5):**
  - **P50:** $308.27\,\text{ms}$
  - **P95:** $315.96\,\text{ms}$
  - **Peak:** $321.40\,\text{ms}$
- **Reconstruction Output:** Generated and saved to `metal2/benchmark_results/diagnostic_boards/photo_nike_1080p_relit_metal.png`.

### 4.3 Multi-Resolution Scaling Profile

```
Resolution       Quality Mode    GPU Latency (P50)   FPS (GPU)    Speedup vs CPU Reference
384 x 256        Preview (4s)        0.12 ms         8,333 FPS            ~340x
384 x 256        Final (16s)         0.47 ms         2,127 FPS            ~190x
1024 x 680       Preview (4s)        0.41 ms         2,439 FPS            ~210x
1024 x 680       Final (16s)         1.08 ms           925 FPS            ~157x
1920 x 1080      Final (16s, Mesh) 308.27 ms             3.2 FPS           ~45x
```

---

## 5. GATE EVALUATION & VERIFICATION AUDIT

All criteria established in the Master Engineering Implementation Directive have been systematically audited:

| Gate | Acceptance Threshold | Measured Value on Apple M5 | Outcome |
| :--- | :--- | :--- | :---: |
| **G-01: Numerical Parity** | Max Abs Irradiance Error $< 0.05$ | $\max = 0.002187$, mean MAE $= 0.000945$ | **PASS** |
| **G-02: Interactive Latency** | Preview P95 Latency $\le 16.6\,\text{ms}$ (60 FPS) | $\max = 2.44\,\text{ms}$ (Mesh), typical $\le 0.32\,\text{ms}$ | **PASS** |
| **G-03: Zero-Mutation Guarantee** | Max Pixel Mutation on Protected Mask $= 0.0$ | $\max = 0.0000000000$ (exact bitwise) | **PASS** |
| **G-04: Deterministic Replay** | Replay Difference on Serialized Scene $= 0.0$ | $\max = 0.0000000000$ (exact bitwise) | **PASS** |
| **G-05: Cliff Shadow Leakage** | Shadow Leakage Rate (SLR) $\le 2.0\%$ | $0.0\%$ across all 6 cases | **PASS** |
| **G-06: Test Suite Passing** | $100\%$ pass on test suite | 36 / 36 tests passing | **PASS** |

---

## 6. WORKSPACE DUAL-BACKEND INTEGRATION

The dual-backend architecture is fully wired into `studio3a/workspace.py`:
- Users can toggle between **Metal GPU** and **CPU Reference** via the interactive radio button in the virtual studio workspace.
- Viewport status displays real-time diagnostics including backend engine, GPU command execution time, sample counts, and total wall latency.
- In Metal mode, interactive slider adjustments (camera orbiting, light positioning, cyclorama cove radius) achieve fluid, zero-lag updates on macOS.

---

## 7. REMAINING ARCHITECTURAL LIMITATIONS & SPIKE-3B DIRECTIVES

1. **Unaccelerated Complex Meshes:**
   While the 280-triangle footwear hull runs in $2.44\,\text{ms}$ for preview and $15.14\,\text{ms}$ for final, brute-force $O(N)$ triangle iteration on GPU will not scale to 100k+ polygon photogrammetry scans. Milestone **RS-METAL-3** should introduce Metal Performance Shaders (MPSRayIntersector) or hardware BVH acceleration (`MTLAccelerationStructure`).
2. **Normal Map High-Frequency Bleed:**
   On highly complex organic surfaces, monocular surface normal estimates can produce micro-shadow fluttering. The uncertainty supervisor's directional grazing angle confidence channel mitigates this, but bilateral normal smoothing should be evaluated in **RS-SPIKE-3B**.
3. **Multi-Light Scalability:**
   Current Metal kernel dynamically binds the active key light. Multi-light support should transition to a structured light buffer array supporting up to 8 studio emitters simultaneously.

---

## 8. MILESTONE CONCLUSION

RS-METAL-2 is **COMPLETE, VALIDATED, AND APPROVED**.

The native Metal Shading Language pipeline matches the repaired CPU reference renderer to high precision, guarantees photographic immutability on protected subject details, and delivers dramatic real-time performance on Apple Silicon hardware.

<!-- GOAL_COMPLETE -->
