# RS-SPIKE-3C.1 Task Plan: Multi-Light Architecture & Additive Illumination

**Baseline Checkpoint:** `c613235` (RS-SPIKE-3C.0)  
**Branch:** `feature/RS-SPIKE-3C.1-multilight-architecture`  
**Execution Standard:** Evidence-first engineering, measured numbers only, zero mocks/skips, physical radiometric consistency.

---

## Phase 0: Baseline Forensic Audit & Verification
- [x] 0.1 Confirm active branch `feature/RS-SPIKE-3C.1-multilight-architecture` and verify baseline commit `c613235`.
- [x] 0.2 Read all ten RS-SPIKE-3C.0 reports (`docs/RS-SPIKE-3C.0/00` to `09`).
- [x] 0.3 Inspect existing single-light implementation: `studio3a/scene.py`, `studio3a/lighting.py`, `studio3a/renderer.py`, `metal2/src/metal_bridge.mm`, `metal2/shaders/renderer.metal`, `metal2/bridge.py`, `metal2/renderer.py`.
- [x] 0.4 Run all 63 existing tests and confirm 100% pass baseline.
- [x] 0.5 Reproduce 1024x576 and 1080p benchmarks and qualify the existing 78.1 FPS 1080p preview limitation.
- [x] 0.6 Verify existing scene serialization format and single-light entry points.
- [x] 0.7 Deliverable: Author `docs/RS-SPIKE-3C.1/00_BASELINE_FORENSIC_AUDIT.md`.

## Phase 1: Multi-Light Scene Architecture & Management
- [x] 1.1 Audit `studio3a/scene.py` scene state model and `AreaLightData`:
  - Add stable unique identifier (`light_id: str`).
  - Add light enable/disable flag (`enabled: bool`), shadow toggle (`cast_shadows: bool`).
  - Add light creation, deletion, duplication, selection, reordering, and per-light undo/redo in `StudioScene`.
- [x] 1.2 Implement explicit backward-compatible scene migration for legacy single-light scenes (v3.0.0 -> v3.1.0).
- [x] 1.3 Ensure deterministic JSON serialization, deserialization, and replay.
- [x] 1.4 Deliverable: Author `docs/RS-SPIKE-3C.1/01_MULTI_LIGHT_SCENE_ARCHITECTURE.md`.

## Phase 2: Additive Illumination Mathematics & CPU Reference
- [x] 2.1 Formulate rigorous additive radiometric accumulation:
  - $E_{\text{total}}(\mathbf{p}) = \sum_{i=1}^M E_i(\mathbf{p})$, where $E_i(\mathbf{p}) = \text{irr}_i(\mathbf{p}) \cdot V_i(\mathbf{p})$.
  - Ensure visibility $V_i$ strictly modulates only its own light's irradiance $E_i$.
  - Maintain energy conventions (FIXED_POWER vs FIXED_RADIANCE) without cross-contamination.
- [x] 2.2 Reconstruct single unified shading ratio: $R_{\text{target}} = \text{ambient\_fill} + E_{\text{total}} \cdot \text{exposure}$.
- [x] 2.3 Apply E.1 Guided-Filter once on combined ratio $\rho_{\text{total}} = \log R_{\text{target}}$: $Y_{\text{relit}} = Y_{\text{orig}} \cdot \exp(\bar{\rho}_{\text{total}})$.
- [x] 2.4 Verify exact numerical invariance when $M=1$ against RS-SPIKE-3C.0 single-light output.
- [x] 2.5 Update CPU reference `studio3a/renderer.py` and test additive illumination.
- [x] 2.6 Deliverable: Author `docs/RS-SPIKE-3C.1/02_ADDITIVE_ILLUMINATION_MATHEMATICS.md`.

## Phase 3: Metal GPU Multi-Light Pipeline Implementation
- [x] 3.1 Design multi-light GPU data representation in `metal2/shaders/renderer.metal`:
  - `ConstantLightBuffer` / array of `CLightParams` with count `num_lights` (max 8 lights).
  - Single-pass stratified accumulation kernel computing per-light irradiance and shadows, accumulating into `out_irradiance` and effective composite visibility.
- [x] 3.2 Update `metal2/src/metal_bridge.h` and `metal2/src/metal_bridge.mm`:
  - Accept `CLightParams*` array and `uint32_t num_lights`.
  - Maintain `PersistentBufferPool` (zero per-frame allocations).
- [x] 3.3 Update `metal2/bridge.py` and `metal2/renderer.py` to marshal multi-light arrays.
- [x] 3.4 Compile native `libmetal2.dylib` and verify clean build.
- [x] 3.5 Deliverable: Author `docs/RS-SPIKE-3C.1/03_METAL_IMPLEMENTATION.md`.

## Phase 4: Multi-Light Shadow Independence & Geometric Accuracy
- [x] 4.1 Construct multi-light test matrix (1, 2, 3, 4 lights; opposing keys, different sizes, overlapping penumbrae).
- [x] 4.2 Validate shadow independence: disabling Light 2 must remove ONLY Light 2's shadows, leaving Light 1 identical.
- [x] 4.3 Validate overlapping shadow penumbra density (min vs additive vs physical transport).
- [x] 4.4 Verify CPU vs Metal implementation parity ($\text{Soft IoU} \ge 0.93$, $\text{SDE} \le 1.0\text{ px}$, $\text{MAE} \le 0.001$).
- [x] 4.5 Deliverable: Author `docs/RS-SPIKE-3C.1/04_SHADOW_INDEPENDENCE_VALIDATION.md`.

## Phase 5: Light Interaction & Artist Control
- [x] 5.1 Implement workspace multi-light selection and manipulation in `studio3a/workspace.py`:
  - Active light selection, move, rotate, resize, intensity, Kelvin slider.
  - Multi-light wireframe frustum visualization in virtual studio viewport (active light highlighted).
- [x] 5.2 Validate rapid dragging, switching, deletion, duplication, and undo/redo responsiveness.
- [x] 5.3 Deliverable: Author `docs/RS-SPIKE-3C.1/05_ARTIST_INTERACTION_VALIDATION.md`.

## Phase 6: Photographic Fidelity Validation
- [x] 6.1 Evaluate multi-light scenes (1, 2, 3, 4 lights) on plates P1, P2, P3:
  - Nike footwear (Plate P1).
  - Landscape HDR (Plate P2).
  - Broken statue (Plate P3).
- [x] 6.2 Compute isolated foreground DCI ($DCI_{\text{fg}} \ge 0.8800$), background DCI, and whole DCI.
- [x] 6.3 Verify exact bitwise immutability on protected regions ($0.0000000000$ mutation).
- [x] 6.4 Save visual comparison boards and heatmaps in `metal2/benchmark_results/diagnostic_boards/`.
- [x] 6.5 Deliverable: Author `docs/RS-SPIKE-3C.1/06_PHOTOGRAPHIC_FIDELITY_REPORT.md`.

## Phase 7: Radiometric & Energy Validation
- [x] 7.1 Verify linearity of light accumulation: doubling one light scales its isolated irradiance by $2.000\times$.
- [x] 7.2 Verify two identical lights produce $2.000\times$ irradiance in unshadowed regions.
- [x] 7.3 Verify energy conservation across fixed-power and fixed-radiance modes.
- [x] 7.4 Verify floating-point overflow and C3 Oklab gamut safety under high multi-light exposure.
- [x] 7.5 Deliverable: Author `docs/RS-SPIKE-3C.1/07_RADIOMETRIC_VALIDATION.md`.

## Phase 8: Multi-Light Performance Benchmarks
- [x] 8.1 Benchmark 1, 2, 3, 4 lights across $384 \times 256$, $1024 \times 576$, and $1920 \times 1080$.
- [x] 8.2 Measure host P50, P95, P99 latency, GPU kernel time, and throughput FPS.
- [x] 8.3 Verify 1-light performance has not regressed vs RS-SPIKE-3C.0.
- [x] 8.4 Verify persistent buffer reuse in steady state (0 allocations).
- [x] 8.5 Deliverable: Author `docs/RS-SPIKE-3C.1/08_PERFORMANCE_BENCHMARKS.md`.

## Phase 9: Automated Regression & Failure Testing
- [x] 9.1 Build comprehensive regression test suite in `tests/RS-SPIKE-3C.1/test_spike3c1_multilight.py`.
- [x] 9.2 Run full combined test suite across the entire repository (ensure 0 failures, 0 skips, 0 mocks).
- [x] 9.3 Deliverable: Author `docs/RS-SPIKE-3C.1/09_REGRESSION_TEST_REPORT.md`.

## Phase 10: Final Acceptance & Roadmap
- [x] 10.1 Synthesize final acceptance report and audit against all 12 acceptance gates.
- [x] 10.2 Deliverables: Author `docs/RS-SPIKE-3C.1/10_FINAL_ACCEPTANCE_REPORT.md` and `docs/RS-SPIKE-3C.1/11_REMAINING_RISKS_AND_NEXT_STEPS.md`.
