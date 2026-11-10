# RS-SPIKE-3C.0 Task Plan: Single-Light Pipeline Completion

**Baseline Checkpoint:** `efed4ed` (RS-SPIKE-3B)  
**Audit Checkpoint:** `5ecd345` (RS-SPIKE-3B.1)  
**Branch:** `feature/RS-SPIKE-3C.0-single-light-completion`  
**Execution Standard:** Evidence-first engineering, measured numbers only, zero mocks/skips.

---

## Phase 0: Baseline Forensic Audit & Implementation Map
- [x] 0.1 Confirm active branch and verify baseline commits (`efed4ed`, `5ecd345`).
- [x] 0.2 Read all eight RS-SPIKE-3B.1 audit reports (`docs/RS-SPIKE-3B.1/00` to `08`).
- [x] 0.3 Inspect existing CPU reference (`studio3a/renderer.py`, `studio3a/geometry.py`, `engine/relighter_v4.py`) and Metal engine (`metal2/src/metal_bridge.mm`, `metal2/shaders/renderer.metal`, `metal2/bridge.py`, `metal2/renderer.py`).
- [x] 0.4 Run full pytest test suite to record starting baseline.
- [x] 0.5 Author source-level implementation map identifying defect, proposed fix, affected interfaces, regression risks, and independent verification for each change.
- [x] 0.6 Deliverable: Author `docs/RS-SPIKE-3C.0/00_BASELINE_FORENSIC_AUDIT.md`.

## Phase 1 (Phase A): Metal E.1 Guided-Filter Implementation
- [x] 1.1 Recover exact E.1 mathematical formulation from historical Spike 1 (`spike_detail_preservation.py`, `2026-11-09-spike-1-detail-preservation-design.md`, `docs/DECISION_LOG.md`).
- [x] 1.2 Verify CPU reference implementation of E.1 guided filter and establish independent CPU baseline.
- [x] 1.3 Implement native Metal compute shader(s) for 2D Box / Guided-Filter:
  - Mean filter / box filter passes (horizontal + vertical or 2D window).
  - Covariance and variance computation: $\sigma_p^2, \sigma_{ip}, a = \frac{\sigma_{ip}}{\sigma_p^2 + \epsilon}, b = \bar{i} - a \bar{p}$.
  - Shading ratio regularization: $S_{\text{guided}} = \bar{a} p + \bar{b}$.
  - Edge-preserving linear-light reconstruction avoiding texture crunch.
- [x] 1.4 Integrate E.1 into Metal pipeline (`metal2/src/metal_bridge.mm`, `metal2/bridge.py`, `metal2/renderer.py`).
- [x] 1.5 Validate CPU–Metal numerical parity for intermediate coefficients ($a, b$) and final output.
- [x] 1.6 Verify bitwise zero-mutation on protected mask with E.1 active.
- [x] 1.7 Evaluate Nike sneaker foreground DCI (target $\ge 0.8800$, no texture crunch, no halos).
- [x] 1.8 Deliverable: Author `docs/RS-SPIKE-3C.0/01_E1_METAL_IMPLEMENTATION.md`.

## Phase 2 (Phase B): Shadow Validation & Ground-Truth Discipline
- [x] 2.1 Refactor validation reporting into three distinct categories:
  - Implementation Parity (CPU vs Metal)
  - Independent Geometric Accuracy (vs Converged Monte Carlo / Analytical Reference)
  - Photographic Fidelity (Foreground DCI, texture crops)
- [x] 2.2 Conduct Monte Carlo convergence study ($N \in \{64, 128, 256, 512, 1024, 2048\}$) to determine reference convergence and sampling uncertainty.
- [x] 2.3 Run full geometry test matrix (OBB, Superquadric, Mesh on Plane and Cyclorama; floating and grounded objects).
- [x] 2.4 Evaluate against strict gates: Simple planar Soft IoU $\ge 0.95$, Complex Soft IoU $\ge 0.90$, SDE $\le 3\text{ px}$, Contour Disp $\le 2\text{ px}$, Area Error $\le 3\%$.
- [x] 2.5 Deliverable: Author `docs/RS-SPIKE-3C.0/02_SHADOW_VALIDATION_METHODOLOGY.md`.

## Phase 3 (Phase C): Sphere Geometry Correctness
- [x] 3.1 Investigate sphere proxy representation:
  - Evaluate dedicated `ProxyType.SPHERE` vs `ProxyType.SUPERQUADRIC` with $e_1=1.0, e_2=1.0$.
  - Implement native analytical sphere in Metal and CPU or formalize Superquadric sphere equivalence with dedicated unit tests.
- [x] 3.2 Ensure sphere proxy is never approximated by an OBB anywhere in the active pipeline.
- [x] 3.3 Validate sphere shadow area error $\le 2\%$ against analytical ground truth ($A_{\text{shadow}} = \pi r^2 \cdot \text{projection}$).
- [x] 3.4 Deliverable: Author `docs/RS-SPIKE-3C.0/03_SPHERE_GEOMETRY_VALIDATION.md`.

## Phase 4 (Phase D): Persistent Metal Buffer Architecture
- [x] 4.1 Implement persistent Metal buffer pool in `metal2/src/metal_bridge.mm` and `metal2/bridge.py`:
  - Retain allocated `MTLBuffer`s across frames; reallocate only on resolution change.
  - Zero full-size buffer allocations per frame during steady state.
- [x] 4.2 Eliminate redundant CPU memory copies:
  - Replace output `memcpy` with zero-copy `np.frombuffer` or direct buffer mapping.
- [x] 4.3 Eliminate CPU OpenCV wireframe overlay bottleneck:
  - Optimize overlay generation or decouple from rendering path.
- [x] 4.4 Profile host end-to-end latency and FPS at $1920 \times 1080$ and $1024 \times 576$ (Target: 1080p P95 $\le 12\text{ ms}$, Preview $\ge 80\text{ FPS}$).
- [x] 4.5 Deliverables: Author `docs/RS-SPIKE-3C.0/04_METAL_BUFFER_ARCHITECTURE.md` and `docs/RS-SPIKE-3C.0/05_PERFORMANCE_BENCHMARKS.md`.

## Phase 5 (Phase E): Photographic Fidelity Validation
- [x] 5.1 Evaluate photographic plates (Nike sneaker, Classical statue, Architectural relief):
  - Isolate foreground DCI vs background DCI vs whole-image DCI.
  - Inspect micro-contrast, stitch detail, leather grain, and shadow boundaries.
- [x] 5.2 Generate photographic boards, difference heatmaps, and $100\%$ scale texture crops.
- [x] 5.3 Deliverable: Author `docs/RS-SPIKE-3C.0/06_PHOTOGRAPHIC_FIDELITY_REPORT.md`.

## Phase 6 (Phase F): Full Regression & Test Suite Expansion
- [x] 6.1 Investigate empty `tests/test_v5_engine.py` and populate or clean up.
- [x] 6.2 Expand test suite covering all 20 required regression areas (parity, E.1, sphere, persistent buffers, resize, async, replay, immutability).
- [x] 6.3 Run full automated test suite (ensure 0 skips, 0 mocks, 0 xfails).
- [x] 6.4 Deliverable: Author `docs/RS-SPIKE-3C.0/07_REGRESSION_TEST_REPORT.md`.

## Phase 7: Final Acceptance Report & Remaining Risks
- [x] 7.1 Conduct adversarial independent review of all 12 validation questions.
- [x] 7.2 Synthesize final audit report with definitive pass/conditional pass verdict.
- [x] 7.3 Deliverables: Author `docs/RS-SPIKE-3C.0/08_FINAL_ACCEPTANCE_REPORT.md` and `docs/RS-SPIKE-3C.0/09_REMAINING_RISKS_AND_NEXT_STEPS.md`.
