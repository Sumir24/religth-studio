# RS-SPIKE-3C.2 Task Plan: Specular Microfacet BRDFs & Material Transport

**Baseline Checkpoint:** `c859cc7` (RS-SPIKE-3C.1)  
**Branch:** `feature/RS-SPIKE-3C.2-specular-material-transport`  
**Execution Standard:** Evidence-first engineering, measured numbers only, zero mocks/skips, physical radiometric consistency.

---

## Phase 0: Baseline Forensic Audit & Verification
- [x] 0.1 Confirm active branch `feature/RS-SPIKE-3C.2-specular-material-transport` and verify baseline commit `c859cc7`.
- [x] 0.2 Review all RS-SPIKE-3C.1 reports (`docs/RS-SPIKE-3C.1/00` to `11`).
- [x] 0.3 Run all 75 existing tests and confirm 100% pass baseline.
- [x] 0.4 Inspect multi-light scene representation, additive pipeline, E.1 reconstruction, CPU reference, Metal shaders, photographic fixtures.
- [x] 0.5 Reproduce existing performance benchmarks on Apple Silicon (1, 2, 4 lights across 576p and 1080p).
- [x] 0.6 Deliverable: Author `docs/RS-SPIKE-3C.2/00_BASELINE_FORENSIC_AUDIT.md`.

## Phase 1: BRDF Mathematical Foundation
- [x] 1.1 Formulate Cook-Torrance microfacet specular BRDF:
  - GGX/Trowbridge-Reitz NDF: $D(\mathbf{h}, \alpha) = \frac{\alpha^2}{\pi ((\mathbf{n} \cdot \mathbf{h})^2(\alpha^2 - 1) + 1)^2}$, where $\alpha = \text{roughness}^2$.
  - Schlick Fresnel: $F(\mathbf{v}, \mathbf{h}, F_0) = F_0 + (1 - F_0)(1 - (\mathbf{v} \cdot \mathbf{h}))^5$.
  - Smith height-correlated masking-shadowing function:
    $G(\mathbf{l}, \mathbf{v}, \mathbf{h}, \alpha) = \frac{2 (\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})}{(\mathbf{n} \cdot \mathbf{v})\sqrt{\alpha^2 + (1-\alpha^2)(\mathbf{n} \cdot \mathbf{l})^2} + (\mathbf{n} \cdot \mathbf{l})\sqrt{\alpha^2 + (1-\alpha^2)(\mathbf{n} \cdot \mathbf{v})^2}}$.
- [x] 1.2 Implement numerical safeguards: $\alpha_{\text{min}} = 0.001$, division-by-zero protection, grazing-angle stabilization, dot product clamping.
- [x] 1.3 Implement stand-alone BRDF evaluation modules in Python: `studio3a/brdf.py`.
- [x] 1.4 Deliverable: Author `docs/RS-SPIKE-3C.2/01_BRDF_MATHEMATICAL_FOUNDATION.md`.

## Phase 2: Material Model & Scene Architecture
- [x] 2.1 Define `MaterialData` in `studio3a/material.py` and `studio3a/scene.py`:
  - `material_id: str`, `name: str`, `base_color: List[float]`, `roughness: float`, `metallic: float`, `specular_f0: float`, `specular_intensity: float`.
  - Energy conservation rules: $F_0 = \text{mix}(0.04, \text{base\_color}, \text{metallic})$, diffuse albedo $= \text{base\_color} \times (1 - \text{metallic})$.
  - Material profiles: Matte dielectric, rough dielectric, smooth dielectric, metallic surface, rough metal, polished metal.
- [x] 2.2 Attach materials to `SubjectProxyData` and `ReceiverData`.
- [x] 2.3 Implement scene serialization v3.2.0 with backward-compatible defaults for v3.0.0 and v3.1.0 scenes.
- [x] 2.4 Support material CRUD operations and undo/redo in `StudioWorkspace`.
- [x] 2.5 Deliverable: Author `docs/RS-SPIKE-3C.2/02_MATERIAL_MODEL.md`.

## Phase 3: Area-Light Specular Integration
- [x] 3.1 Investigate area-light specular integration:
  - Option A: Stochastic integration with stratified sampling.
  - Option B: Most Representative Point (MRP) approximation (Karis 2013).
  - Option C: Linearly Transformed Cosines (LTC).
- [x] 3.2 Implement and benchmark accuracy, performance, and stability on Apple Silicon.
- [x] 3.3 Select production approach based on empirical evidence and validate against high-sample-count reference.
- [x] 3.4 Implement multi-light specular accumulation accounting for distance, solid angle, and visibility.
- [x] 3.5 Deliverable: Author `docs/RS-SPIKE-3C.2/03_AREA_LIGHT_SPECULAR_INTEGRATION.md`.

## Phase 4: Diffuse & Specular Energy Accounting & Photographic Reconstruction
- [x] 4.1 Formulate total outgoing radiance: $L_o = L_{o, \text{diffuse}} + L_{o, \text{specular}}$.
- [x] 4.2 Reconcile specular transport with E.1 Guided-Filter photographic reconstruction:
  - Formulate two-scale decomposition preserving diffuse microtexture via Guided Filter while adding specular energy in linear space.
  - Prevent specular highlights from destabilizing log ratio or creating edge halos.
- [x] 4.3 Verify gamut safety under extreme specular intensity using C3 Oklab compression.
- [x] 4.4 Deliverable: Author `docs/RS-SPIKE-3C.2/04_DIFFUSE_SPECULAR_ENERGY_ACCOUNTING.md`.

## Phase 5: CPU Reference & Native Metal Implementation
- [x] 5.1 Implement CPU reference renderer in `studio3a/renderer.py`.
- [x] 5.2 Implement Metal shader support in `metal2/shaders/renderer.metal`:
  - Design 64-byte aligned `CMaterialParams` structure.
  - Add specular evaluation branch to `evaluate_multilight_surface_kernel`.
- [x] 5.3 Update C++/Objective-C bridge (`metal2/src/metal_bridge.h`, `metal2/src/metal_bridge.mm`, `metal2/bridge.py`, `metal2/renderer.py`).
- [x] 5.4 Maintain persistent UMA buffer pool (zero per-frame allocations).
- [x] 5.5 Recompile `libmetal2.dylib` and verify clean build.
- [x] 5.6 Validate CPU-Metal parity across material sweeps (Soft IoU $\ge 0.999$, MAE $< 0.001$).
- [x] 5.7 Deliverable: Author `docs/RS-SPIKE-3C.2/05_METAL_IMPLEMENTATION.md`.

## Phase 6: Independent BRDF Validation
- [x] 6.1 Implement independent mathematical tests in `tests/RS-SPIKE-3C.2/test_brdf_validation.py`:
  - Normal-incidence Fresnel response.
  - Grazing-angle response ($F \to 1$).
  - Roughness sweep (0.05, 0.10, 0.25, 0.50, 0.75, 1.00).
  - Metallic sweep (0.0, 0.25, 0.50, 0.75, 1.0).
  - Helmholtz reciprocity: $f_r(\mathbf{l}, \mathbf{v}) = f_r(\mathbf{v}, \mathbf{l})$.
  - Hemispherical energy conservation ($\int_{\Omega^+} f_r \cos\theta d\omega \le 1$).
  - White furnace test (uniform hemispherical radiance).
  - CPU-Metal parity.
  - Area-light specular integration reference comparison.
- [x] 6.2 Deliverable: Author `docs/RS-SPIKE-3C.2/06_INDEPENDENT_BRDF_VALIDATION.md`.

## Phase 7: Photographic Material Validation
- [x] 7.1 Evaluate material relighting on real plates:
  - Plate P1 (Nike footwear): Fabric mesh vs rubber vs leather specular response.
  - Plate P2 (Classical statue): Marble/stone specular response.
  - Plate P3 (Architectural relief): Plaster/stone response.
- [x] 7.2 Verify foreground DCI $\ge 0.8800$, background bitwise zero mutation ($0.0000000000$).
- [x] 7.3 Generate 100% crop visual boards for fabric, marble, plastic, and metal.
- [x] 7.4 Document single-image material recovery limitations explicitly.
- [x] 7.5 Deliverable: Author `docs/RS-SPIKE-3C.2/07_PHOTOGRAPHIC_MATERIAL_VALIDATION.md`.

## Phase 8: Artist Interaction & Workspace
- [x] 8.1 Integrate material authoring into `studio3a/workspace.py`:
  - Material selection, parameter editing (base color, roughness, metallic, specular intensity).
  - Diffuse-only vs diffuse-plus-specular toggle.
  - Specular-only visualization mode for debugging/inspection.
  - Full undo/redo integration.
- [x] 8.2 Verify interaction responsiveness and state determinism.
- [x] 8.3 Deliverable: Author `docs/RS-SPIKE-3C.2/08_ARTIST_INTERACTION.md`.

## Phase 9: Performance Validation
- [x] 9.1 Benchmark 1, 2, 4, 8 lights across 384x256, 1024x576, and 1920x1080.
- [x] 9.2 Measure GPU kernel time, Host P50/P95/P99 latency, and FPS on Apple M5.
- [x] 9.3 Verify diffuse-only path incurs zero overhead when specular is disabled.
- [x] 9.4 Verify 0 steady-state buffer allocations.
- [x] 9.5 Deliverable: Author `docs/RS-SPIKE-3C.2/09_PERFORMANCE_BENCHMARKS.md`.

## Phase 10: Regression Testing & Acceptance
- [x] 10.1 Build comprehensive regression suite in `tests/RS-SPIKE-3C.2/`.
- [x] 10.2 Run complete repository test suite (87 tests; ensure 100% pass, 0 skips, 0 mocks).
- [x] 10.3 Deliverable: Author `docs/RS-SPIKE-3C.2/10_REGRESSION_TEST_REPORT.md`.
- [x] 10.4 Deliverable: Author `docs/RS-SPIKE-3C.2/11_FINAL_ACCEPTANCE_REPORT.md`.
- [x] 10.5 Deliverable: Author `docs/RS-SPIKE-3C.2/12_REMAINING_RISKS_AND_NEXT_STEPS.md`.
