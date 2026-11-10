# RS-SPIKE-3B.1: Repository & Checkpoint Forensic Audit

**Milestone:** RS-SPIKE-3B.1 — Independent Evidence Audit & Photographic Fidelity Verification  
**Auditor:** Principal Computational Photography Engineer & Quality Assurance Architect  
**Audited Checkpoint:** `efed4ed` (`feat(RS-SPIKE-3B): Geometric Lighting Fidelity & Scene Interaction validation complete (UNCONDITIONAL PASS)`)  
**Audit Branch:** `audit/RS-SPIKE-3B.1` (branched directly from `efed4ed`)  
**Date:** November 2026  

---

## 1. Executive Summary

This forensic audit establishes the exact baseline repository state of Relight Studio at git checkpoint `efed4ed`. The objective is to independently verify repository integrity, inspect all source and test implementations, identify inconsistencies or gaps in the RS-SPIKE-3B deliverables, and prepare an audit plan before any further engineering work.

### Key Forensic Findings
1. **Repository Cleanliness & Checkpoint Authenticity:**
   - Git HEAD is verified at `efed4ed`, which introduced the RS-SPIKE-3B geometry corrections, benchmarks, regression tests, and documentation.
   - Working tree on the audit branch is $100\%$ clean with zero uncommitted modifications and zero untracked files.
2. **Implementation vs. Metric Nomenclature Inconsistency (The "1.0000 Parity" Discrepancy):**
   - In RS-SPIKE-3B, the reported `Soft IoU = 1.0000` and `SDE = 0.00 px` on canonical scenes M2_01, M2_02, M2_03, M2_05, and M2_06 were **implementation parity measurements comparing the native Metal GPU renderer directly against the CPU reference renderer** (`studio3a`).
   - The master benchmark script (`benchmarks/run_spike3b_master_benchmark.py`, line 69) explicitly evaluated:
     ```python
     soft_iou = compute_soft_iou(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
     sde = compute_continuous_sde(r_metal["direct_visibility"], r_cpu["direct_visibility"], rec)
     ```
   - While achieving $1.0000$ parity confirms that Apple Silicon Metal executes the exact mathematical model implemented in Python, **it does not establish absolute geometric correctness against an independent ground truth**. Calling this metric "Shadow Soft IoU" in the executive report without explicitly qualifying it as "CPU–Metal Implementation Parity Soft IoU" was a critical documentation ambiguity that Phase 2 of this audit will rigorously investigate.
3. **Test Suite Hygiene:**
   - The repository contains 51 automated pytest tests across 16 test files. All 51 pass cleanly in $4.77\,\text{s}$.
   - Zero tests use mocks, zero tests are skipped, and zero xfails exist.
   - One empty test file was discovered: `tests/test_v5_engine.py` (0 bytes).
   - In `metal2/tests/test_math_parity.py`, line 81 asserts `max_err_irr < 0.05` (a loose threshold), whereas the actual measured error is $\sim 10^{-5}$ and the RS-SPIKE-3B target was $\le 0.001$.
4. **Performance Measurement Disaggregation:**
   - Latency figures reported in RS-SPIKE-3B varied widely ($0.41\,\text{ms}$ to $30.43\,\text{ms}$).
   - The audit confirmed that these variations correspond to completely distinct workloads:
     - $0.41\,\text{ms}$: GPU kernel for a simple OBB on Plane at $768 \times 512$.
     - $1.02\,\text{ms}$ GPU / $8.06\,\text{ms}$ Host: $1024 \times 576$ interactive preview ($N=4$ samples). Host overhead in Python accounts for $7.04\,\text{ms}$ of the $8.06\,\text{ms}$.
     - $7.24\,\text{ms}$ GPU: $1920 \times 1080$ Full HD final quality ($N=32$ samples).
     - $22.08\,\text{ms}$ to $30.43\,\text{ms}$: Nike footwear plate using a 280-triangle unaccelerated mesh proxy evaluated at 64 samples per pixel.

---

## 2. Checkpoint Verification & Git Integrity

### Commit Log Inspection
```
efed4ed (HEAD -> audit/RS-SPIKE-3B.1, main) feat(RS-SPIKE-3B): Geometric Lighting Fidelity & Scene Interaction validation complete (UNCONDITIONAL PASS)
70cf251 feat(RS-SPIKE-3A.1): shadow fidelity, metal parity, hardware optimizations & interactive validation
185d3c5 feat(metal2): complete RS-METAL-2 native Metal GPU engine with reference repairs and benchmarks
5411bf0 docs: add independent RS-SPIKE-3A audit and RS-METAL-2 implementation plan
a450ecb feat(RS-SPIKE-3A): complete artist-controlled virtual 3D studio foundation implementation and validation
```

- **Branch Created:** `audit/RS-SPIKE-3B.1`
- **Working Tree:** Clean (`nothing to commit, working tree clean`)
- **Historical Milestones Preserved:** Spike 1 (`spike1_output/`), Spike 2 (`spike2_output/`), Spike 2.1 (`spike2_1_output/`), Spike 2.2 (`spike2_2_output/`), RS-SPIKE-3A (`experiments/RS-SPIKE-3A/`), RS-SPIKE-3A-CORRECTED (`experiments/RS-SPIKE-3A-CORRECTED/`), and RS-SPIKE-3B (`docs/RS-SPIKE-3B/`). None of these historical trees have been altered.

---

## 3. Source & Test File Inventory

### Core Source Components Inspected:
| Subsystem | File Path | Role | Key Mechanics |
| :--- | :--- | :--- | :--- |
| **Geometry** | `studio3a/geometry.py` | CPU analytical primitives | OBB, Superquadric with $G(p) = \rho(p) - 1.0$, LowPolyMesh, Receivers. |
| **Lighting** | `studio3a/lighting.py` | Area light radiometry | Stratified cell centers, inverse-square, Planckian blackbody table. |
| **Shadows** | `studio3a/shadows.py` | CPU shadow transport | Monte Carlo ray casting, superellipse contact grounding. |
| **Renderer** | `studio3a/renderer.py` | Authoritative CPU reference | End-to-end scene pipeline. |
| **Workspace** | `studio3a/workspace.py` | UI controller & session | State synchronization, undo/redo stack, Gradio app builder. |
| **Metal Shaders**| `metal2/shaders/renderer.metal` | GPU compute kernel | Ray-superquadric solver, mesh intersection, C3 Oklab gamut clamping. |
| **Metal Bridge** | `metal2/src/metal_bridge.mm` | Objective-C++ Metal runtime | Command queue, shared memory buffers, hardware timestamping. |
| **Python Bridge**| `metal2/bridge.py` | ctypes interface | C-struct definitions, zero-copy buffer mapping. |
| **GPU Renderer**| `metal2/renderer.py` | MetalRenderBackend | Packs StudioScene into Metal uniforms, dispatches compute pass. |
| **Evaluation** | `metal2/shadow_evaluation.py` | Continuous metrics | Soft IoU (fuzzy Jaccard), Continuous SDE, Contour displacement. |

### Test Suite Inventory (51 Tests Total):
- `metal2/tests/test_math_parity.py` (4 tests): Sky-masking, irradiance parity, protected zero-mutation, latency.
- `metal2/tests/test_metal_device.py` (3 tests): Metal device detection, unified memory confirmation, compilation.
- `metal2/tests/test_metal_reconstruction.py` (1 test): C3 Oklab kernel accuracy.
- `metal2/tests/test_shadow_evaluation.py` (4 tests): Soft IoU, Continuous SDE, contact gate, comprehensive evaluation.
- `tests/RS-SPIKE-3A/camera/test_camera.py` (4 tests): Camera basis, Gram-Schmidt orthonormality, projection.
- `tests/RS-SPIKE-3A/geometry/test_geometry.py` (7 tests): OBB, Superquadric ellipsoid, LowPolyMesh, Receivers.
- `tests/RS-SPIKE-3A/lighting/test_lighting.py` (4 tests): Kelvin conversion, energy conventions, inverse-square falloff.
- `tests/RS-SPIKE-3A/reconstruction/test_reconstruction.py` (3 tests): Reconstruction pipelines.
- `tests/RS-SPIKE-3A/renderer/test_renderer_repairs.py` (4 tests): Ground plane, sky masking, receiver integration.
- `tests/RS-SPIKE-3A/scene_state/test_scene_state.py` (4 tests): JSON serialization, undo/redo stack.
- `tests/RS-SPIKE-3A/shadows/test_shadows.py` (2 tests): Direct visibility and contact occlusion.
- `tests/RS-SPIKE-3B/test_spike3b_regressions.py` (4 tests): $G(p)$ stability, area light radiometry, bitwise mutation, superquadric parity.
- `tests/test_pbr_engine.py` (2 tests): Legacy PBR engine checks.
- `tests/test_v3_engine.py` (5 tests): Legacy V3 engine checks.
- `tests/test_v5_engine.py` (0 tests): Empty file (identified for deletion or population).

---

## 4. Benchmark & Deliverable Audit

### RS-SPIKE-3B Artifacts Present in Repository:
1. `docs/RS-SPIKE-3B/00_BASELINE_INDEPENDENT_AUDIT.md` (11.9 KB)
2. `docs/RS-SPIKE-3B/01_GEOMETRY_FIDELITY_ANALYSIS.md` (8.8 KB)
3. `docs/RS-SPIKE-3B/02_AREA_LIGHT_VALIDATION.md` (8.3 KB)
4. `docs/RS-SPIKE-3B/03_SHADOW_ACCURACY_REPORT.md` (8.5 KB)
5. `docs/RS-SPIKE-3B/04_INTERACTION_PERFORMANCE_REPORT.md` (5.6 KB)
6. `docs/RS-SPIKE-3B/05_PHOTOGRAPHIC_VALIDATION_REPORT.md` (6.8 KB)
7. `docs/RS-SPIKE-3B/06_REGRESSION_AND_PARITY_REPORT.md` (6.3 KB)
8. `docs/RS-SPIKE-3B/07_FINAL_VALIDATION_REPORT.md` (7.2 KB)
9. `docs/RS-SPIKE-3B/08_NEXT_MILESTONE_RECOMMENDATION.md` (5.6 KB)
10. `docs/RS-SPIKE-3B/benchmark_results.json` & `benchmark_results.csv`
11. `docs/RS-SPIKE-3B/area_light_validation_results.json`
12. `docs/RS-SPIKE-3B/interaction_performance_results.json`
13. `docs/RS-SPIKE-3B/photographic_validation_results.json`
14. `docs/RS-SPIKE-3B/photographic_boards/` (3 visual contact boards)

All 14 claimed deliverables exist and contain authentic empirical data.

---

## 5. Audit Plan for RS-SPIKE-3B.1

To address the mandate of the master prompt, the independent audit will execute the following focused investigations:

1. **Phase 1: Superquadric Mathematical Proof & Independent Geometric Reference:**
   - Mathematically analyze $G(p) = \rho(p) - 1.0$: Establish its homogeneity, gradient properties, and deviations from an exact Euclidean signed distance function.
   - Construct an **independent high-precision double-precision (float64) Brent/Scipy root solver** completely outside `studio3a` and `metal2` to measure absolute geometric accuracy across 12 distinct superquadric configurations (sharp box, sphere, flattened pancake, tall cylinder, grazing rays).
2. **Phase 2: Independent Ground-Truth Shadow Benchmark:**
   - Disentangle CPU–Metal parity from absolute geometric accuracy.
   - Create an independent ground-truth ray caster using high-sample analytical geometry ($N=256$, double-precision) and compute true Soft IoU, Hard IoU, SDE, and penumbra width error.
3. **Phase 3: Latency Decomposition & Hardware Benchmarking:**
   - Disaggregate GPU kernel dispatch from host Python wrapping overhead.
   - Profile the exact bottleneck of the 280-triangle mesh proxy on the Nike plate ($22.08\,\text{ms}$) vs the analytical box on the architectural plate ($0.41\,\text{ms}$).
4. **Phase 4: Photographic Fidelity & DCI Metric Audit:**
   - Audit the Laplacian SSIM formulation of DCI mathematically. Test whether it masks local smoothing or contrast changes.
   - Expand the evaluation dataset to inspect fine texture, specular boundaries, and identity preservation.
5. **Phase 5: Visual Contact Sheet Audit:**
   - Generate high-resolution visual boards with zoomed insets for all canonical and photographic cases.
6. **Phase 6: Final Milestone Scorecard & Readiness Verdict:**
   - Issue an evidence-backed decision on whether RS-SPIKE-3C (Multi-Light Rig) is authorized.

