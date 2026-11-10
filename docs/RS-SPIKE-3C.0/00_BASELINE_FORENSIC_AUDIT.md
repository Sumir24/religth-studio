# RELIGHT STUDIO — RS-SPIKE-3C.0 ENGINEERING DELIVERABLE
# 00: BASELINE FORENSIC AUDIT & SOURCE-LEVEL IMPLEMENTATION MAP

**Author:** Principal Rendering Engineer & Metal GPU Architect  
**Date:** November 10, 2026  
**Audited Checkpoint:** `efed4ed` (RS-SPIKE-3B Baseline)  
**Audit Checkpoint:** `5ecd345` (RS-SPIKE-3B.1 Audit Complete)  
**Active Milestone Branch:** `feature/RS-SPIKE-3C.0-single-light-completion`  
**Execution Standard:** Evidence-First Engineering, Zero Mocks, Measured Truth Only  

---

## 1. REPOSITORY & BASELINE VERIFICATION

Prior to modifying any code for RS-SPIKE-3C.0, the repository state was forensically verified:

1. **Active Git State:**
   - Active Branch: `feature/RS-SPIKE-3C.0-single-light-completion` (branched directly from `audit/RS-SPIKE-3B.1`).
   - Clean Working Tree: Verified zero uncommitted or unstaged changes.
   - Commit Lineage:
     - `5ecd345`: `docs(RS-SPIKE-3B.1): complete independent evidence audit and photographic fidelity verification`
     - `efed4ed`: `feat(RS-SPIKE-3B): Geometric Lighting Fidelity & Scene Interaction validation complete (UNCONDITIONAL PASS)`
2. **Historical Spikes Integrity:**
   - All historical code, tests, and deliverables (`spike1_output/`, `spike2_1_output/`, `spike2_2_output/`, `docs/RS-SPIKE-3A/`, `docs/RS-SPIKE-3A.1/`, `docs/RS-SPIKE-3B/`, `docs/RS-SPIKE-3B.1/`) remain intact and unaltered.
3. **Automated Test Baseline:**
   - Command: `PYTHONPATH=. ./.venv/bin/pytest -v`
   - Total Collected Tests: 51
   - Passed: 51
   - Failed: 0, Errors: 0, Skips: 0, xfails: 0.
   - Execution Time: $4.88\text{ s}$.
   - Flaw Identified: `tests/test_v5_engine.py` is empty ($0\text{ bytes}$).

---

## 2. SYNTHESIS OF THE EIGHT RS-SPIKE-3B.1 AUDIT REPORTS

The preceding audit established five critical architectural realities:

1. **E.1 Guided Filter Omission:**
   `metal2/shaders/renderer.metal` executed naive multiplicative relighting ($\mathbf{I}_{\text{relit}} = \mathbf{I}_{\text{orig}} \cdot (\mathbf{E} \cdot V + 0.15)$). The CPU reference `ReconstructionEngine` implemented full E.1 Guided-Filter Log-Ratio Regularization and C3 Oklab Gamut Mapping, but the Metal pipeline bypassed it entirely.
2. **The Parity vs Accuracy Conflation:**
   Reported `Soft IoU = 1.0000` and `SDE = 0.00 px` reflected backend implementation parity between CPU and Metal running identical 64-sample stratified grid layouts. True accuracy against independent double-precision $N=256$ Monte Carlo ground truth is $\text{Soft IoU} \approx 0.9099$ and $\text{Contour Disp} \approx 1.42\text{ px}$.
3. **DCI Metric Background Dilution:**
   On `P1_nike_sneaker`, whole-image DCI scored $0.8941$ (passing), but foreground DCI dropped to **$0.8282$ (FAILED)**. The flat $0.9702$ background masked severe texture crunch on the woven footwear upper.
4. **Sphere Proxy Distortion:**
   Because the data model lacked a native sphere primitive, approximating a sphere with an OBB produced a $134.7\%$ shadow area error ($4,490\text{ px}$ vs $1,913\text{ px}$).
5. **Host Memory Allocation Overhead:**
   Raw GPU shading at 1080p is fast ($4.67 - 7.00\text{ ms}$, $> 140\text{ FPS}$), but end-to-end host latency is $27 - 34\text{ ms}$ ($31\text{ FPS}$) because $116.2\text{ MB}$ of shared UMA buffers are reallocated on every frame ($9.2\text{ ms}$) alongside redundant copies ($4.5\text{ ms}$) and CPU wireframe drawing ($7.0\text{ ms}$).

---

## 3. SOURCE-LEVEL IMPLEMENTATION MAP

Every modification in RS-SPIKE-3C.0 is mapped below with its current implementation, root defect, proposed engineering modification, affected interfaces, regression risks, and independent verification method.

---

### Component 1: Metal E.1 Guided-Filter Regularization & C3 Gamut Mapping
- **Current Implementation:**
  - `metal2/shaders/renderer.metal` (lines 573–578):
    ```cpp
    float3 relit_lin = orig_lin * (irr_acc * visibility + 0.15f);
    float3 relit_srgb = clamp(pow(relit_lin, 1.0f / 2.2f), 0.0f, 1.0f);
    ```
  - `metal2/renderer.py` (line 226): hardcodes `"shading_ratio": np.ones_like(out_vis)`.
- **Actual Defect:**
  Noisy monocular depth normals directly modulate photograph RGB without edge-preserving filtering, causing texture crunch and failing P1 footwear foreground DCI ($0.8282 < 0.88$).
- **Proposed Modification:**
  1. Implement separable 2D box filter kernels in Metal (`box_filter_horizontal`, `box_filter_vertical`).
  2. Implement guided filter compute pass in Metal:
     - Linear luminance extraction $Y_{\text{orig}}$.
     - Target shading ratio $R_{\text{target}} = (Y_b \cdot \text{irr} \cdot V + Y_b \cdot A) / Y_b$.
     - Specular peak protection shoulder ($M_{\text{high}}$).
     - Log ratio regularization: $\rho = \log(\max(R_{\text{eff}}, 10^{-4}))$.
     - Guided filtering $\bar{\rho} = \text{GuidedFilter}(Y_{\text{orig}}, \rho, r=16, \epsilon=0.0004)$.
     - Reconstruction: $Y_{\text{relit}} = Y_{\text{orig}} \cdot \exp(\bar{\rho})$.
  3. Apply integrated C3 Oklab Constant-Hue Chroma Reduction kernel.
- **Affected Interfaces:**
  - `metal2/shaders/renderer.metal`, `metal2/shaders/reconstruction.metal`
  - `metal2/src/metal_bridge.mm`, `metal2/src/metal_bridge.h`
  - `metal2/bridge.py`, `metal2/renderer.py`
- **Regression Risks:**
  - Image boundary artifacts if box filter reflection borders are misaligned.
  - Performance degradation if guided filter passes are unoptimized.
- **Independent Verification Method:**
  - Bitwise comparison of intermediate coefficients ($a, b, \bar{a}, \bar{b}, \bar{\rho}$) against CPU `cv2.boxFilter` reference.
  - Nike sneaker foreground DCI re-evaluation ($\ge 0.8800$).

---

### Component 2: Separation of Validation Reporting & Shadow Discipline
- **Current Implementation:**
  - `benchmarks/run_spike3b_master_benchmark.py`: directly logged `compute_soft_iou(r_metal["direct_visibility"], r_cpu["direct_visibility"])` under "Shadow Soft IoU".
- **Actual Defect:**
  Misrepresented implementation parity as physical shadow accuracy.
- **Proposed Modification:**
  1. Refactor all benchmark harnesses to output three distinct sections:
     - Category A: Implementation Parity (CPU vs Metal MAE, Soft IoU parity).
     - Category B: Independent Geometric Accuracy (Metal vs Converged Monte Carlo $N=2048$ / Analytical Ground Truth).
     - Category C: Photographic Fidelity (Foreground DCI, texture crops, zero-mutation).
  2. Conduct Monte Carlo sample convergence study ($N \in \{64, 128, 256, 512, 1024, 2048\}$) to establish ground-truth reference convergence.
- **Affected Interfaces:**
  - `metal2/shadow_evaluation.py`
  - `benchmarks/validate_area_light.py`, `benchmarks/independent_shadow_ground_truth_audit.py`
  - All benchmark report generators.
- **Regression Risks:**
  None (metric reporting discipline).
- **Independent Verification Method:**
  Verify that parity and accuracy metrics are computed from completely decoupled pipelines and saved to separate JSON fields.

---

### Component 3: Sphere Geometry Correctness
- **Current Implementation:**
  - `studio3a/scene.py`: `ProxyType` supports `OBB`, `SUPERQUADRIC`, `MESH`. No `SPHERE`.
  - When a sphere was requested, test fixtures set `ProxyType.OBB`, producing a cube with $134.7\%$ shadow area error.
- **Actual Defect:**
  Approximating a spherical subject with an OBB ruins cast-shadow accuracy.
- **Proposed Modification:**
  1. Add native `ProxyType.SPHERE` with analytical ray-sphere quadratic intersection in Metal and CPU reference, OR strictly enforce `ProxyType.SUPERQUADRIC` with $e_1=1.0, e_2=1.0$ and dedicated spherical validation.
  2. Implement dedicated ray-sphere analytical branch in `renderer.metal`:
     $$t = -(\mathbf{p} \cdot \mathbf{d}) - \sqrt{(\mathbf{p} \cdot \mathbf{d})^2 - (\mathbf{p} \cdot \mathbf{p} - r^2)}$$
  3. Verify shadow area error $\le 2\%$ against analytical circular disc projection.
- **Affected Interfaces:**
  - `studio3a/scene.py`, `studio3a/geometry.py`
  - `metal2/shaders/renderer.metal`, `metal2/src/metal_bridge.mm`, `metal2/bridge.py`, `metal2/renderer.py`
- **Regression Risks:**
  Proxy parameter packing backwards compatibility in `CProxyParams`.
- **Independent Verification Method:**
  Double-precision analytical ray-sphere ground truth comparison across planar and cyclorama receivers.

---

### Component 4: Persistent Metal Buffer Architecture
- **Current Implementation:**
  - `metal2/src/metal_bridge.mm` (`metal2_render_frame`):
    Calls `[g_device newBufferWithBytes:...]` and `[g_device newBufferWithLength:...]` on every single render call for 6 full-resolution buffers ($116.2\text{ MB/call}$).
  - `metal2/renderer.py` (`_generate_proxy_overlay`):
    Multiplies full-resolution image by 255.0 on CPU and calls OpenCV line drawing, adding $7 - 46\text{ ms}$ host latency.
- **Actual Defect:**
  Allocating $116\text{ MB}$ per frame and CPU-bound OpenCV canvas copies throttle application frame rate to $31\text{ FPS}$ despite $> 140\text{ FPS}$ GPU execution.
- **Proposed Modification:**
  1. Implement persistent buffer pool in `Metal2Bridge`:
     - Retain allocated `MTLBuffer`s; reallocate only if width or height changes.
     - Zero full-size buffer allocations per frame during steady-state interaction.
  2. Implement zero-copy buffer wrapping:
     - Return NumPy arrays referencing shared Metal buffer pointers directly, eliminating $58.2\text{ MB}$ of `memcpy`.
  3. Decouple or optimize proxy wireframe generation:
     - Fast vector projection or native blit, bypassing full CPU image multiplication.
  4. Enable asynchronous command buffer submission without blocking host thread on preview renders.
- **Affected Interfaces:**
  - `metal2/src/metal_bridge.mm`, `metal2/src/metal_bridge.h`
  - `metal2/bridge.py`, `metal2/renderer.py`
- **Regression Risks:**
  Race conditions or stale memory if buffer synchronization is incorrect.
- **Independent Verification Method:**
  Instruments / `vm_stat` allocation count tracking verifying 0 buffer reallocations during 100 consecutive frames, with 1080p P95 host latency $\le 12\text{ ms}$.

---

### Component 5: Test Suite Expansion & Empty Test Investigation
- **Current Implementation:**
  - `tests/test_v5_engine.py` is an empty file (0 bytes).
- **Actual Defect:**
  Empty test file produces pytest warning/exit anomaly and leaves v5 inverse delighting / HBAO crevice occlusion untested.
- **Proposed Modification:**
  1. Populate `tests/test_v5_engine.py` with rigorous tests covering inverse delighting, polar coordinates, and HBAO crevice occlusion.
  2. Expand regression suite with tests for persistent buffer reuse, sphere geometry correctness, E.1 numerical parity, and isolated foreground DCI.
- **Affected Interfaces:**
  - `tests/test_v5_engine.py`, `tests/`
- **Regression Risks:**
  None.
- **Independent Verification Method:**
  Pytest execution verifying all tests pass with zero skips, zero mocks, zero xfails.

