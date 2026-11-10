# RELIGHT STUDIO — RS-SPIKE-3B.1 READINESS RECOMMENDATION
# 08: ARCHITECTURAL READINESS & GATING DECISION FOR RS-SPIKE-3C

**Author:** Principal Computational Photography Architect & Systems Reviewer  
**Date:** November 10, 2026  
**Audited Checkpoint:** `efed4ed` (RS-SPIKE-3B)  
**Target Milestone:** RS-SPIKE-3C (Multi-Light Studio Rigs, Light Mixing & Advanced Interaction)  
**Readiness Verdict:** **CONDITIONAL GO**  

---

## 1. FORMAL READINESS DECISION

### Decision: **CONDITIONAL GO**

Relight Studio has established a remarkably robust, high-performance foundation on Apple Silicon Metal:
- **Core GPU Throughput:** Renders 64 stratified area-light shadow rays at $> 140\text{ FPS}$ at Full HD 1080p ($> 540\text{ FPS}$ at 576p viewport preview).
- **Geometric Robustness:** Superquadrics track ground-truth double-precision geometry to within $1 - 37\,\mu\text{m}$.
- **Immutability & State:** Zero-mutation (`0.0000000000`) and deterministic replay (`0.0000000000`) are fully verified.

However, proceeding immediately to multi-light rigs without addressing single-light defects would compound existing architectural flaws (multiplying texture degradation and amplifying CPU buffer allocation bottlenecks).

Therefore, **RS-SPIKE-3C is AUTHORIZED, subject to five mandatory Phase 0 engineering gates** to be completed before multi-light mixing code is written.

---

## 2. MANDATORY PRE-REQUISITES (PHASE 0 ENGINEERING GATES)

Before implementing multi-light data structures, additive radiance accumulation, or multi-light UI controls in RS-SPIKE-3C, the following five repairs must be implemented and verified:

### Gate 1: Implementation of E.1 Guided-Filter Regularization in Metal Shaders
- **Defect:** `metal2/shaders/renderer.metal` executes naive multiplicative relighting ($\mathbf{I}_{\text{relit}} = \mathbf{I}_{\text{orig}} \cdot (\mathbf{E} \cdot V + 0.15)$), causing foreground DCI on the Nike sneaker plate to fail at **$0.8282$** with severe texture crunch.
- **Requirement:**
  1. Implement a 2D Box / Guided-Filter compute pass in Metal to smooth the shading ratio:
     $$S(x, y) = \frac{\mathbf{E}_{\text{irr}}(x, y) \cdot V(x, y) + A}{\mathbf{E}_{\text{orig}}(x, y) + \epsilon}$$
  2. Modulate the original photographic plate with the regularized ratio $S_{\text{guided}}$ rather than raw pixel irradiance.
  3. Acceptance Criteria: Plate P1 foreground DCI must achieve $\mathbf{\ge 0.8800}$.

### Gate 2: Strict Metric Nomenclature Separation (Parity vs Accuracy)
- **Defect:** RS-SPIKE-3B reported CPU-Metal implementation parity as "Shadow Soft IoU: 1.0000", misleading readers into assuming exact physical accuracy.
- **Requirement:**
  1. In all test harnesses, benchmark JSONs, and reports, metrics comparing Metal against CPU must be labeled explicitly as **"Parity (Metal vs CPU)"**.
  2. Metrics evaluating rendering against independent Monte Carlo references must be labeled **"Ground Truth Accuracy (vs N=256 GT)"**.
  3. Acceptance criteria for shadow transport in RS-SPIKE-3C:
     - Ground Truth Soft IoU: $\ge 0.8800$ (Canonical OBB & Superquadric).
     - Ground Truth Contour Boundary Displacement: $\le 2.00\text{ px}$.

### Gate 3: Foreground-Isolated Detail Preservation Evaluation
- **Defect:** Whole-image DCI allowed a smooth $0.9702$ background to mask a failing $0.8282$ foreground on the sneaker plate.
- **Requirement:**
  1. The primary acceptance gate for DCI must evaluate strictly on the subject foreground mask:
     $$\text{DCI}_{\text{gate}} = \text{eval\_DCI}(\mathbf{I}_{\text{orig}}, \mathbf{I}_{\text{relit}}, \text{fg\_mask})$$
  2. Whole-image DCI may be recorded as a secondary diagnostic, but cannot be used for pass/fail gating.

### Gate 4: Formalization of the Sphere Proxy Primitive
- **Defect:** The data model lacks an analytical sphere primitive. Setting `ProxyType.OBB` to represent a spherical subject causes an unacceptably large $134.7\%$ shadow area error.
- **Requirement:**
  1. Update `StudioScene` and `ProxyType` to explicitly enforce `ProxyType.SUPERQUADRIC` with $e_1 = 1.0, e_2 = 1.0$ whenever a spherical proxy is requested, OR add a dedicated `ProxyType.SPHERE` that branches to analytical ray-sphere intersection in Metal.
  2. Add automated regression tests validating spherical shadow projection against analytical ground truth ($\text{Soft IoU} \ge 0.9200$).

### Gate 5: Metal Host Allocation Optimization & Persistent Buffer Pool
- **Defect:** End-to-end host latency at 1080p is $27 - 34\text{ ms}$ ($29 - 37\text{ FPS}$), despite raw GPU execution being $4.67 - 7.00\text{ ms}$ ($143 - 214\text{ FPS}$). $81.2\%$ of frame time is wasted allocating $116\text{ MB}$ of shared buffers per frame and executing CPU-bound wireframe line drawing.
- **Requirement:**
  1. Pre-allocate a persistent buffer pool in `Metal2Bridge` for full-resolution frame buffers (`depth`, `normals`, `image`, `out_relit`, `out_vis`, `out_irr`).
  2. Replace per-frame `newBufferWithBytes:` allocations with sub-millisecond in-place buffer updates.
  3. Replace Python `memcpy` with zero-copy NumPy wrapping (`np.frombuffer`).
  4. Acceptance Criteria: Full HD 1080p end-to-end host latency must drop to $\mathbf{\le 12.0\text{ ms}}$ ($> 80\text{ FPS}$).

---

## 3. RS-SPIKE-3C IMPLEMENTATION ROADMAP

```
[RS-SPIKE-3C Execution Architecture]
│
├── Phase 0: Prerequisite Engineering Gates (Single-Light Stability)
│   ├── Task 0.1: Native Metal Guided-Filter Compute Shader (Fix P1 Sneaker DCI >= 0.88)
│   ├── Task 0.2: Persistent Metal Buffer Pool (Cut 1080p latency to < 12 ms)
│   ├── Task 0.3: Native Sphere Primitive & Foreground DCI Harness
│   └── Verification: Sign-off on single-light fixes across all 3 photographic plates
│
├── Phase 1: Multi-Light Scene Architecture & Data Model
│   ├── Multi-light uniform buffers (up to 4 independent studio fixtures)
│   ├── Independent fixture parameters: Key, Fill, Rim, Hair / Background lights
│   ├── Spectral mixing and blackbody Kelvin synthesis
│   └── Multi-light shadow attenuation & overlap handling
│
├── Phase 2: Native Metal Multi-Light Shaders
│   ├── Batched stratified area-light accumulation in single GPU pass
│   ├── Light-to-proxy bounding box early rejection
│   └── Energy conservation and additive irradiance normalization
│
├── Phase 3: Dual Viewport & Artist Lighting Rig Controls
│   ├── Live multi-light gizmo manipulation in 3D viewport
│   ├── Dynamic key/fill ratio controls (e.g. 1:2, 1:4, 1:8 lighting ratios)
│   └── Interactive studio presets: Rembrandt, Butterfly, Split, Rim lighting
│
└── Phase 4: Validation & Milestone Sign-Off
    ├── Multi-light parity against CPU reference
    ├── Photographic evaluation on complex multi-light portraits
    └── Final audit and production integration review
```

---

## 4. CONCLUSION

Milestone RS-SPIKE-3B provided the crucial computational breakthrough for Relight Studio: proving that physically stratified area lighting and superquadric geometry can execute on Apple Silicon GPUs with sub-millisecond hardware speed.

By addressing the specific single-light defects identified in this audit during Phase 0, the engineering team ensures that **RS-SPIKE-3C** will be built upon an unshakeable, photographically validated, and fully interactive foundation.
