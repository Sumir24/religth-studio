# RELIGHT STUDIO — RS-SPIKE-3C.2.1
## Independent Evidence Audit Report 00: Repository Forensics & Baseline Reproduction

**Author:** Independent Principal Rendering Engineer, Physically Based Rendering Researcher & Adversarial Verification Lead  
**Milestone:** RS-SPIKE-3C.2.1 — Independent BRDF, Material Transport & Photographic Fidelity Audit  
**Audited Target:** RS-SPIKE-3C.2 Checkpoint `9f9bb12` (`9f9bb124cb050d034c8aa7b1b935590ac1ee144f`)  
**Audit Branch:** `audit/RS-SPIKE-3C.2.1-independent-verification`  
**Parent Checkpoint:** `c859cc7` (`c859cc71c8a33d42bc524398ba37c1cdf76e1362`)  
**Execution Standard:** Evidence-First Independent Verification. Zero modifications to production files.

---

### 1. Executive Summary & Audit Mandate

This report documents Phase 0 repository forensics for **RS-SPIKE-3C.2.1**, an independent adversarial audit of the Cook–Torrance microfacet BRDF, material transport architecture, stochastic area-light integration, and photographic reconstruction implemented in milestone **RS-SPIKE-3C.2**.

The audit objectives are:
1. Verify git commit integrity, tree provenance, and commit history for target `9f9bb12`.
2. Inspect all 13 engineering reports in `docs/RS-SPIKE-3C.2/` against actual source code.
3. Verify all production source files in Python (`studio3a/`) and Apple Metal (`metal2/`).
4. Independently reproduce the full automated test suite (87 tests).
5. Audit benchmark output artifacts, JSON metrics, and visual comparison boards.
6. Identify critical anomalies, discrepancies, and focus areas for subsequent audit phases.

---

### 2. Git Provenance & Commit Forensics

#### 2.1 Commit Identification & Lineage
- **Target Commit SHA:** `9f9bb124cb050d034c8aa7b1b935590ac1ee144f`
- **Short SHA:** `9f9bb12`
- **Parent Commit SHA:** `c859cc71c8a33d42bc524398ba37c1cdf76e1362` (`feature/RS-SPIKE-3C.1-multilight-architecture`)
- **Author:** Sumir24 <sumir.satsangi2004@gmail.com>
- **Date:** Tue Nov 10 20:01:04 2026 +0530
- **Commit Message:** `feat(RS-SPIKE-3C.2): Implement Cook-Torrance microfacet BRDFs and material transport`
- **Audit Branch:** Created dedicated branch `audit/RS-SPIKE-3C.2.1-independent-verification` strictly off `9f9bb12`.

#### 2.2 Forensic File Diff Summary
Commit `9f9bb12` introduced **5,168 additions and 114 deletions across 41 files**:
- **New Core Modules:**
  - `studio3a/brdf.py` (218 lines): Standalone Cook-Torrance GGX microfacet BRDF.
  - `studio3a/material.py` (175 lines): `MaterialData` model, presets, and validation.
- **Modified Core Modules:**
  - `studio3a/lighting.py` (+65 lines): Stochastic stratified area-light specular sampling.
  - `studio3a/reconstruction.py` (+48 lines): Two-Scale radiant energy decomposition.
  - `studio3a/renderer.py` (+64 lines): Material parameter routing and specular accumulation.
  - `studio3a/scene.py` (+110 lines): Material schema v3.2.0 migration and serialization.
  - `studio3a/workspace.py` (+121 lines): Material UI controls, presets dropdown, Undo/Redo.
- **Metal GPU Infrastructure:**
  - `metal2/shaders/renderer.metal` (+125 lines): Cook-Torrance BRDF shaders, 64-byte `CMaterialParams`, Pass 8 additive linear specular injection.
  - `metal2/src/metal_bridge.h` (+13 lines): C ABI struct `CMaterialParams`.
  - `metal2/src/metal_bridge.mm` (+28 lines): Objective-C++ bridge binding and uniform dispatch.
  - `metal2/bridge.py` (+30 lines): ctypes wrapper for `CMaterialParams`.
  - `metal2/renderer.py` (+33 lines): Material buffer management and execution.
- **Tests Added (12 new tests bringing suite from 75 to 87):**
  - `tests/RS-SPIKE-3C.2/test_brdf_foundation.py` (4 tests)
  - `tests/RS-SPIKE-3C.2/test_material_model.py` (4 tests)
  - `tests/RS-SPIKE-3C.2/test_brdf_validation.py` (8 tests)
  - `tests/RS-SPIKE-3C.2/test_artist_interaction.py` (3 tests)
- **Documentation:** 13 complete technical reports in `docs/RS-SPIKE-3C.2/`.
- **Benchmark Artifacts:** 3 JSON files and 3 diagnostic boards (`.jpg`) in `metal2/benchmark_results/`.

---

### 3. Production Source Code Integrity & Implementation Audit

Independent forensic inspection of the codebase at `9f9bb12` confirmed the following architectural properties:

| Component | Implementation File | Verified Features | Architectural Integrity |
| :--- | :--- | :--- | :---: |
| **BRDF Formulation** | `studio3a/brdf.py` | GGX $D$, Heitz height-correlated Smith $G_2/Vis$, Schlick $F$, $\alpha = \text{roughness}^2$. | **VERIFIED** |
| **Numerical Guards** | `studio3a/brdf.py` & `metal2/shaders/renderer.metal` | $\alpha_{\text{min}} = 0.0016$ ($\text{roughness} \ge 0.04$), $\epsilon_{\text{dot}} = 10^{-5}$, $\epsilon_{\text{len}} = 10^{-7}$. | **VERIFIED** |
| **Material Model** | `studio3a/material.py` | 5 factory presets (Fabric, Marble, Plastic, Rough Metal, Polished Metal). Range validation $[0, 1]$. | **VERIFIED** |
| **Two-Scale Recon** | `studio3a/reconstruction.py` | $\mathbf{L}_{\text{relit}} = I_{\text{orig}} \cdot \exp(\hat{\rho}_{\text{diffuse}}) + \Delta \mathbf{L}_{\text{specular}}$. Specular separated from Guided Filter. | **VERIFIED** |
| **GPU Metal Shaders** | `metal2/shaders/renderer.metal` | MSL functions `evaluate_ggx_brdf`, `eval_specular_area_light`, Pass 8 additive linear composite. | **VERIFIED** |
| **C ABI & Bridge** | `metal2/src/metal_bridge.h`, `.mm` | 64-byte aligned `CMaterialParams` matching Python `ctypes.Structure` byte-for-byte. | **VERIFIED** |
| **Interactive State** | `studio3a/workspace.py` | Multi-step Undo/Redo stack pushes `(scene_state, material_state)`. Immutability preserved. | **VERIFIED** |
| **Schema Migration** | `studio3a/scene.py` | Migration from v3.0.0 and v3.1.0 to v3.2.0 with default material fallback. | **VERIFIED** |

---

### 4. Independent Regression Suite Reproduction

The complete repository regression test suite was executed in an isolated subshell using `./.venv/bin/pytest tests/ -v`:

```
Platform: macOS-15.5-arm64-arm-64bit (Darwin 24.5.0)
Python: 3.14.6
Pytest: 9.0.2

============================= test session starts ==============================
tests/RS-METAL-2/test_metal_reconstruction_pipeline.py::test_reconstructed_scene_shape PASSED
tests/RS-METAL-2/test_metal_reconstruction_pipeline.py::test_zero_mutation_protected_regions PASSED
tests/RS-METAL-2/test_metal_reconstruction_pipeline.py::test_metal_reference_parity_dci PASSED
tests/RS-METAL-2/test_metal_reconstruction_pipeline.py::test_sky_mask_handling PASSED
tests/RS-METAL-2/test_metal_reconstruction_pipeline.py::test_contact_occlusion_consistency PASSED
tests/RS-METAL-2/test_metal_reconstruction_pipeline.py::test_cgs_and_grounding_evaluation PASSED
tests/RS-SPIKE-3A.1/test_shadow_fidelity_interactive.py::test_reconstruction_pipeline_basic PASSED
...
tests/RS-SPIKE-3C.1/test_spike3c1_multilight.py::test_gate15_ci_test_suite_execution PASSED
tests/RS-SPIKE-3C.2/test_artist_interaction.py::test_workspace_material_state_roundtrip PASSED
tests/RS-SPIKE-3C.2/test_artist_interaction.py::test_workspace_material_undo_redo PASSED
tests/RS-SPIKE-3C.2/test_artist_interaction.py::test_workspace_full_relighting_with_materials PASSED
tests/RS-SPIKE-3C.2/test_brdf_foundation.py::test_ggx_distribution_monotonic_peak PASSED
tests/RS-SPIKE-3C.2/test_brdf_foundation.py::test_fresnel_schlick_limits PASSED
tests/RS-SPIKE-3C.2/test_brdf_foundation.py::test_smith_geometry_grazing PASSED
tests/RS-SPIKE-3C.2/test_brdf_foundation.py::test_brdf_horizon_cutoff PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_helmholtz_reciprocity PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_energy_conservation PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_white_furnace_specular PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_diffuse_specular_energy_conservation PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_two_scale_energy_decomposition PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_area_light_specular_stochastic_vs_ground_truth PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_multilight_specular_accumulation PASSED
tests/RS-SPIKE-3C.2/test_brdf_validation.py::test_cpu_metal_material_parity PASSED
tests/RS-SPIKE-3C.2/test_material_model.py::test_material_data_defaults_and_validation PASSED
tests/RS-SPIKE-3C.2/test_material_model.py::test_factory_profiles PASSED
tests/RS-SPIKE-3C.2/test_material_model.py::test_scene_serialization_with_material PASSED
tests/RS-SPIKE-3C.2/test_material_model.py::test_legacy_scene_migration PASSED

======================== 87 passed in 29.97s ========================
```

**Result:** **87 / 87 tests passed (100.0%, 0 failures, 0 skips)**.
All baseline tests from RS-SPIKE-3C.1 (75 tests) and new RS-SPIKE-3C.2 tests (12 tests) pass deterministically.

---

### 5. Benchmark Output Forensics & Discrepancy Analysis

The output artifacts in `metal2/benchmark_results/` were inspected and cross-referenced with the reports in `docs/RS-SPIKE-3C.2/`:

#### 5.1 Photographic Material Results (`photographic_material_results.json`)
- Evaluated across 3 authentic photographic plates:
  - `P1_nike_sneaker` ($1024 \times 1024$)
  - `P2_classical_statue` ($1024 \times 1024$)
  - `P3_architectural_relief` ($1024 \times 1024$)
- Across 5 material profiles (Fabric, Marble, Plastic, Rough Metal, Polished Metal).
- **Protected Region Error:** Exactly `0.0` across all 15 evaluations. Bitwise zero mutation verified.
- **DCI Measurements:**
  - 14 / 15 evaluations achieved Foreground DCI $\ge 0.9720$ and Whole DCI $\ge 0.9756$.
  - **1 Evaluation Anomaly:** Plate P1 (Nike Sneaker) under Rough Metal achieved:
    - **Foreground DCI:** `0.7899` (Significant drop below the standard $\ge 0.95$ threshold)
    - **Whole DCI:** `0.8825`
    - Report 07 and Report 11 recorded this as a "PASS (Limitation)".
    - **Audit Priority:** Phase 5 must conduct a detailed forensic investigation into this drop.

#### 5.2 Material Performance Results (`material_performance_results.json`)
- 60 benchmark configurations evaluated on Apple Silicon M5 GPU:
  - 3 resolutions: Preview ($1024 \times 576$), Standard ($1920 \times 1080$), High ($2048 \times 2048$).
  - 4 light configurations: 1, 2, 4, 8 lights.
  - 5 material profiles.
- **Latency Anomaly:**
  - At 576p Preview (1 light), Diffuse Only reported **$4.25\,\text{ms}$** ($235.3\,\text{FPS}$), while Diffuse + Specular reported **$4.15\,\text{ms}$** ($240.9\,\text{FPS}$).
  - A mathematically more complex shader (Cook-Torrance BRDF evaluation + specular accumulation) reporting lower execution time requires physical explanation (GPU clock ramping, execution divergence, or timing granularity).
- **Throughput vs Target:**
  - Full HD ($1920 \times 1080$) Preview throughput is $71.5\,\text{FPS}$ ($13.99\,\text{ms}$), while the prompt target mentions $80\,\text{FPS}$.
  - Final quality (8 lights, 1024spp area lights) achieves $25.0\,\text{FPS}$ ($40.0\,\text{ms}$).
  - **Audit Priority:** Phase 6 must reconcile these timings against GPU hardware performance counters.

#### 5.3 Area Specular Investigation Results (`area_specular_investigation.json`)
- Stochastic Stratified area sampling was compared against a 1024-spp ground truth and Karis Most Representative Point (MRP) approximation.
- Reported PSNR: $57.4\,\text{dB}$ ($\text{MAE} \le 0.000144$).
- **Audit Priority:** Phase 3 must verify if the 1024-spp reference is converged by comparing against an independent 4096-spp reference.

---

### 6. Phase 0 Audit Conclusion & Investigation Directives

The repository checkpoint `9f9bb12` is forensically intact, self-consistent, and 100% reproducible. No commit tampering, missing dependencies, or silent test failures were detected.

The subsequent audit phases will focus specifically on:
1. **Mathematical rigor:** Validating Cook-Torrance formulas against an independent reference built from first principles (Phase 1).
2. **Energy conservation:** Testing quadrature convergence with denser grids ($180 \times 360$ up to $720 \times 1440$) and Fibonacci hemisphere sampling (Phase 2).
3. **Area sampling convergence:** Independent 4096-spp ground-truth validation (Phase 3).
4. **Photographic reconstruction:** Proving the Two-Scale decomposition prevents highlight halos and double-counting (Phase 4).
5. **Plate P1 Rough Metal DCI drop (0.7899):** Dissecting conductor electron absorption ($k_d \to 0$) vs texture attenuation (Phase 5).
6. **GPU performance reconciliation:** Clock boosting, timing methodology, and 80 FPS targets (Phase 6).
7. **Architectural readiness:** Evaluating IBL and studio probe integration for RS-SPIKE-3C.3 (Phase 9).
