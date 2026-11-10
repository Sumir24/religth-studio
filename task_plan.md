# RS-SPIKE-3C.3 Task Plan: Image-Based Lighting & Studio Reflection Probes

**Role:** Principal Rendering Engineer, Physically Based Rendering Researcher, Metal GPU Engineer, Computational Photography Architect, and Independent Validation Lead.  
**Starting Checkpoint:** `3d6cee7` (Phase 0 Remediation Complete)  
**Branch:** `feature/RS-SPIKE-3C.3-ibl-reflection-probes`  
**Platform:** macOS / Apple Silicon / Metal 3  
**Execution Standard:** Evidence-first engineering. Ground-truth physical verification before implementation. Preservation of original photograph integrity and non-destructive Two-Scale reconstruction.

---

## Phase 0: Baseline & Repository Verification
- [x] 0.1 Inspect complete repository, Git state, and active branch (`feature/RS-SPIKE-3C.3-ibl-reflection-probes` at `3d6cee7`).
- [x] 0.2 Inspect the GGX denominator fix in `studio3a/brdf.py` and `metal2/shaders/renderer.metal`.
- [x] 0.3 Trace production rendering path from `StudioScene` through `RenderBackend` / `MetalRenderBackend` to final reconstructed image.
- [x] 0.4 Audit existing material (`MaterialData`), light (`AreaLightData`), camera, geometry, and reconstruction structures.
- [x] 0.5 Check for existing environment abstractions or prior IBL attempts.
- [x] 0.6 Reproduce baseline measurements (test suite, benchmarks, performance).
- [x] 0.7 Deliverable: Author `RS_SPIKE_3C_3_BASELINE_AUDIT.md`.

## Phase A: Controlled IBL Reference Experiment
- [x] A.1 Create a controlled synthetic environment map with distinct features:
  - High-intensity bright region (studio softbox / key light).
  - Low-intensity dark region.
  - Neutral / midtone studio bounce.
  - Tinted / colored accent feature.
  - High-contrast edge boundary.
- [x] A.2 Establish controlled reference scene:
  - 1 metallic sphere ($m=1.0, F_0=1.0$).
  - 1 dielectric sphere ($m=0.0, F_0=0.04$).
  - Fixed camera, fixed exposure, no direct lights.
- [x] A.3 Material test matrix: roughness $r \in [0.04, 0.10, 0.25, 0.50, 1.00]$ for both metallic and dielectric.
- [x] A.4 Construct independent, high-sample Monte Carlo reference implementation:
  - Cosine-weighted hemisphere integration for diffuse irradiance.
  - GGX importance sampling over hemisphere for specular reflection.
  - Demonstrate numerical convergence across sample counts ($N = 64, 256, 1024, 4096, 16384$).
- [x] A.5 Validate acceptance criteria:
  - Sharpness decreases monotonically with increasing roughness.
  - No energy amplification ($R(V) \le 1.0$).
  - No black pixels / coordinate lookup singularities.
  - No seam discontinuities at $\phi = 0/2\pi$ or poles $\theta = 0/\pi$.
  - Stability at $r = 0.04$.
- [x] A.6 Deliverable: Author `RS_SPIKE_3C_3_PHASE_A_REFERENCE.md` with rendered images, convergence graphs, and error metrics.

## Phase B: Environment Representation & Precomputation Architecture
- [x] B.1 Select and justify environment representation:
  - Equirectangular format (2:1 aspect ratio, linear float32 HDR).
  - Radiance environment map representation.
  - Diffuse irradiance map representation (precomputed / numerical).
  - Specular prefiltered reflection map (Karis / Epic Games split-sum approximation with GGX roughness mips).
  - Preintegrated BRDF LUT ($256 \times 256$ float32 texture for $N \cdot V$ vs Roughness).
- [x] B.2 Define linear color space, HDR radiometric units, and exposure conventions.
- [x] B.3 Implement environment map loading, validation, and prefiltering generator in Python.
- [x] B.4 Add unit tests for environment map coordinates, sampling, and prefiltering.

## Phase C: Metal GPU Implementation
- [x] C.1 Extend `metal2/shaders/renderer.metal`:
  - Add prefiltered specular environment sampling with GGX mip selection.
  - Add 2D BRDF LUT sampling (`brdf_lut`).
  - Add diffuse irradiance environment sampling.
  - Combine environment diffuse: $k_d \cdot c_{\text{diff}} \cdot E_{\text{diffuse}}$.
  - Combine environment specular: $(F_0 \cdot \text{scale} + \text{bias}) \cdot L_{\text{prefiltered}}$.
- [x] C.2 Extend `metal2/src/metal_bridge.mm` and `metal2/src/metal_bridge.h`:
  - Texture/buffer bindings for environment irradiance map, prefiltered maps, and BRDF LUT.
  - Persistent Metal buffer allocations in steady state.
  - Extend uniform buffer for environment parameters (`CEnvironmentParams`).
- [x] C.3 Extend Python bridge `metal2/bridge.py` and `metal2/renderer.py` to support environment data.
- [x] C.4 Extend CPU reference renderer in `studio3a/renderer.py` for exact mathematical parity.
- [x] C.5 Verify CPU–Metal parity for environment illumination ($\text{MAE} < 0.005$).

## Phase D: Direct Light + IBL Energy Accounting
- [x] D.1 Formulate rigorous radiometric balance:
  - Direct Diffuse + Direct Specular + Environment Diffuse + Environment Specular.
  - Single-scattering energy conservation: $k_d = (1 - F) \cdot (1 - \text{metallic})$.
- [x] D.2 Test configurations:
  - Environment only.
  - 1 direct light only.
  - Environment + 1 direct light.
  - Environment + 4 direct lights.
  - Environment + 8 direct lights.
- [x] D.3 Verify energy bounds under multi-light + IBL illumination (no unintended doubling).

## Phase E: Relight Studio Photographic Integration
- [x] E.1 Integrate IBL into Two-Scale Photographic Reconstruction:
  - Diffuse transport: $\mathbf{L}_{\text{diffuse, total}} = \mathbf{L}_{\text{direct, diff}} + \mathbf{L}_{\text{env, diff}}$.
  - Guided filter applies to combined diffuse ratio.
  - Specular transport: $\mathbf{L}_{\text{specular, total}} = \mathbf{L}_{\text{direct, spec}} + \mathbf{L}_{\text{env, spec}}$.
  - Additive specular highlight overlay with C3 Oklab gamut compression.
- [x] E.2 Evaluate on photographic test plates:
  - Plate P1: Nike sneaker.
  - Plate P2: Classical statue.
  - Plate P3: Architectural relief.
- [x] E.3 Measure foreground DCI, background DCI, whole-image DCI, and protected-region zero-mutation.
- [x] E.4 Verify zero modification to unmasked background and strict identity preservation.

## Phase F: Uncertainty Supervisor & Artist Controls
- [x] F.1 Integrate environment parameters into `StudioScene`:
  - `EnvironmentData`: `enabled`, `asset_id`, `intensity`, `rotation_deg`, `diffuse_weight`, `specular_weight`.
  - Schema migration and JSON serialization round-trip.
  - Undo/redo stack preservation.
- [x] F.2 Integrate with Uncertainty Supervisor:
  - Distinguish known HDR, user-provided, estimated SDR, and missing environment info.
  - Prevent fabrication of missing environment data as ground truth.
- [x] F.3 Author comprehensive test suite in `tests/RS-SPIKE-3C.3/`.

## Phase G: Validation, Performance & Reporting
- [x] G.1 Execute full regression suite (historical + new spike): 118/118 passing.
- [x] G.2 Benchmark 1024x576 and 1920x1080 across 5 configurations.
- [x] G.3 Produce all 5 authoritative milestone markdown deliverables.
- [x] G.4 Produce high-resolution diagnostic visual comparison boards.
  - Flag environment reflection reliability based on surface normal visibility and proxy distance.
  - Prevent deceptive "ground truth" claims for unmeasured environment detail.

## Phase G: Validation, Performance & Deliverables
- [ ] G.1 Run full regression suite across repository (all existing + new tests).
- [ ] G.2 Perform comprehensive hardware performance benchmarks on Apple Silicon M5 GPU:
  - 576p and 1080p preview & final quality.
  - Zero heap allocation verification across steady frames.
  - Accurate latency, FPS, and bottleneck analysis.
- [ ] G.3 Author all required deliverables:
  - `RS_SPIKE_3C_3_BASELINE_AUDIT.md`
  - `RS_SPIKE_3C_3_PHASE_A_REFERENCE.md`
  - `RS_SPIKE_3C_3_IMPLEMENTATION_REPORT.md`
  - `RS_SPIKE_3C_3_VALIDATION_REPORT.md`
  - `RS_SPIKE_3C_3_PERFORMANCE_REPORT.md`
  - Visual comparison boards and reference comparison images.
- [ ] G.4 Conclude with final engineering verdict (PASS / CONDITIONAL PASS / FAIL).
