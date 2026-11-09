# RELIGHT STUDIO — RS-SPIKE-3A
## 00_REPOSITORY_AUDIT: Pre-Implementation Architectural & Codebase Audit

- **Document ID:** RS-SPIKE-3A-AUDIT-v1.0
- **Author:** Principal Computational Photography Engineer, Senior macOS/Metal Architect & Rendering Systems Auditor
- **Date:** 2026-11-09
- **Status:** APPROVED BASELINE AUDIT
- **Mandate:** Source-level verification of existing repository assets prior to RS-SPIKE-3A implementation.

---

### 1. Executive Summary

This repository audit establishes the technical baseline for **RS-SPIKE-3A: Artist-Controlled Virtual 3D Studio Foundation**.
Relight Studio has completed four preceding research cycles:
- **Spike 1:** Evaluated five image-space luminance reconstruction paradigms and three Oklab gamut mapping formulations. Validated Paradigm E.1 (Guided-Filter Regularized Shading Ratio) and C3 (Oklab Constant-Hue Chroma Reduction).
- **Spike 2 / 2.1:** Explored 2.5D shadow transport and built an independent 3D ray-traced reference renderer (`spike2_1_reference_renderer.py`).
- **Spike 2.2:** Re-evaluated contact grounding, self-occlusion, and Apple Silicon Metal benchmarking. Audited silhouette leakage rates ($SLR$) and shadow distance errors ($SDE$).
- **Post-Spike 2.2 Independent Review:** Dissected critical implementation defects in Spike 2.2:
  1. The Metal benchmark script (`spike2_2_metal_benchmark.py`) used a mock bisection loop (`cond = t_mid > 0.5`) that omitted inverse transforms and gamut tests; genuine PyTorch MPS bisection required $239.24\text{ ms}$ at 1080p ($4.1\text{ FPS}$).
  2. The parameter `confidence_fallback: bool = True` in `spike2_2_candidate.py` was dead code, causing ablation configuration C10 to be identical to C9.
  3. The 2.5D cast shadow engine failed 25 of 26 synthetic test cases ($SDE = 13.4\text{ px}$, $\text{IoU} = 0.521$), proving that 2D heightfield shear projections cannot represent 3D volumetric occluders or curved cycloramas.

RS-SPIKE-3A moves the project from exploratory 2D/2.5D image-space scripts to a **deterministic, artist-controlled virtual 3D studio architecture** driven by analytical 3D proxies, parametric receivers, and rectangular area lights.

---

### 2. Detailed Inspection of Existing Architecture & Assets

```
REPOSITORY STRUCTURE & ASSET MAP:
-------------------------------------------------------------------------------
relight studio/
├── engine/                       [Production Relighting Candidates]
│   ├── relighter_v3.py           (Legacy polar-coordinate 2D relighter)
│   ├── relighter_v4.py           (Monolithic 2D/2.5D engine with GGX specular)
│   ├── relighter_v4_locked.py    (Read-only archive of v4)
│   ├── relighter_v5.py           (Experimental candidate)
│   └── shaders/                  (Early Metal and WGSL prototypes)
├── spike1_output/                (Historical Spike 1 CSV/JSON/Reports - FROZEN)
├── spike2_output/                (Historical Spike 2 CSV/JSON/Reports - FROZEN)
├── spike2_1/ & spike2_1_output/  (Historical Spike 2.1 Artifacts - FROZEN)
├── spike2_2/ & spike2_2_output/  (Historical Spike 2.2 Artifacts - FROZEN)
├── docs/
│   ├── review_post_spike2_2/     (Independent Review & CAHRA Architecture)
│   └── spike2_2/                 (Spike 2.2 Documentation & Evidence)
├── tests/
│   ├── test_v3_engine.py         (5 unit tests: identity, lambda, falloff)
│   ├── test_pbr_engine.py        (2 unit tests: normal map, specular sanity)
│   └── test_v5_engine.py         (Empty placeholder)
├── demo_output/                  (Photographic assets: nike_sample.jpg, etc.)
└── .venv/                        (Python 3.14.6, PyTorch 2.15.0 MPS, Gradio 6.31.0)
```

#### 2.1 Reusable Components
1. **Analytical 3D Ray-Primitive Math (`spike2_2/spike2_2_reference_renderer.py`):**
   - Vectorized Pinhole Camera (`Camera3D`) with ray generation through pixel NDC.
   - Closed-form ray-sphere intersection.
   - Kay-Kajiya slab ray-box intersection.
   - Vectorized horizontal floor plane ($Y=0$) and vertical wall ($Z=-1$).
   - Analytical curved cyclorama cove fillet ($Y(Z)$ fillet circle intersection).
   - Monte Carlo area-light soft shadow sampling.
   *Assessment:* Highly reusable as the mathematical core for `studio3a/geometry.py` and `studio3a/lighting.py`.
2. **Frequency-Guided Luminance Reconstruction (`spike2_2/spike2_2_candidate.py`):**
   - Guided filter log-luminance ratio remapping (E.1).
   - Decoupled additive radiance compositing contract:
     $$Y_{\text{indirect}} = Y_b \cdot R_{\text{amb}} \cdot A_{\text{amb}}$$
     $$Y_{\text{direct}} = Y_b \cdot (R_{\text{key}} - R_{\text{amb}}) \cdot D_{\text{diffuse}} \cdot V_{\text{direct}}$$
   *Assessment:* Validated and ready for incorporation into `studio3a/reconstruction.py`.
3. **Reference Photographic Test Assets (`demo_output/`):**
   - `demo_output/nike_sample.jpg` + depth map + surface normals.
   - `demo_output/01_original.png` (Architectural relief) + depth + normals.
   - Statue asset (`/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/statue_depth.png`).
   *Assessment:* Verified and available for photographic validation.

#### 2.2 Broken or Incomplete Components (Must NOT be Reused As-Is)
1. **2.5D Heightfield Shear Projection (`compute_component_V_cast`):**
   - Broken on non-planar receivers ($12.66\%$ leakage on cycloramas).
   - Broken on hovering geometry ($48.33\text{ px}$ centroid error).
   *Action:* Completely replaced in RS-SPIKE-3A by analytical 3D proxy ray tracing onto parametric receivers.
2. **Monolithic Polar Light Controls (`engine/relighter_v4.py`):**
   - Light position is specified as polar angles (`azimuth`, `elevation`, `distance`), lacking explicit 3D spatial transforms, rectangular emitter dimensions, and physical orientation vectors.
   *Action:* Replaced by a true 3D `AreaLight` with 3D translation vector, rotation matrix / Euler angles, width, height, and energy conventions.
3. **Mock Metal Benchmark (`spike2_2_metal_benchmark.py`):**
   - The mock bisection loop must not be referenced for performance claims.
   *Action:* Measure end-to-end full pipeline execution with genuine color and shadow calculations.

#### 2.3 Dependency Constraints
- **Python Version:** 3.14.6 arm64 on macOS Darwin.
- **Installed Packages:**
  - `torch 2.15.0` with `torch.backends.mps.is_available() == True`.
  - `gradio 6.31.0`, `fastapi 0.162.2`, `uvicorn 0.54.0` available in `.venv`.
  - `numpy 2.5.4`, `scipy 1.18.1`, `opencv-python 5.0.0.93`, `pillow 12.3.0`, `pytest 9.2.0`.
- **Constraint:** Zero external network calls; all tests and workspaces must run locally without downloading unapproved packages.

---

### 3. Integration Risks & Mitigation Strategies

| Risk | Description | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Risk 1: UI-Engine Desynchronization** | UI controls mutating display buffers directly, bypassing scene state. | Loss of deterministic replay and undo/redo failure. | Strict Model-View-Controller isolation. The UI is a read/write view of `StudioScene`. The renderer accepts only `StudioScene` instances. |
| **Risk 2: Coordinate Space Ambiguity** | Differing axis conventions (e.g. Y-up vs Z-up, left-handed vs right-handed). | Shadow ray inversion or inverted surface normals. | Standardize strictly on right-handed 3D studio coordinates: $+X$ right, $+Y$ up, $+Z$ towards camera. Ground plane at $Y=0$. |
| **Risk 3: Numerical Instability in Superquadrics** | Fractional exponents $\frac{2}{\epsilon}$ causing negative base power errors or division by zero. | Render NaN/Inf pixels and visual blowups. | Implement sign-preserving absolute power transforms and clamp exponents to $[\epsilon_{\min}, \epsilon_{\max}] = [0.1, 4.0]$. |
| **Risk 4: Metal MPS Dispatch Overhead** | PyTorch MPS launching hundreds of small kernels, tanking interactive framerates. | Sluggish viewport response during active gizmo dragging. | Implement dual-path backend: Fast vectorized NumPy/SciPy reference for preview, with explicit PyTorch MPS batched tensors for final rendering. |

---

### 4. Proposed Module Boundaries for `studio3a/`

```
studio3a/
├── scene.py          -> Serializable StudioScene, Camera, SubjectProxy, Receiver, AreaLight, Settings
├── camera.py         -> 3D Pinhole camera, calibration, ray generation, world<->camera transforms
├── geometry.py       -> OBB, Superquadric, Mesh, Plane, Cyclorama ray-intersection and normals
├── lighting.py       -> Rectangular AreaLight emitter, radiance/power conventions, Monte Carlo sampling
├── shadows.py        -> Direct visibility, Self-occlusion, 3D Cast shadows, Near-field contact
├── uncertainty.py    -> 3-channel variance supervisor (sigma_geom^2, sigma_occl^2, sigma_mat^2)
├── reconstruction.py -> Immutable image preservation, E.1 guided-filter ratio, C3 gamut mapping
├── renderer.py       -> RenderBackend contract, Preview vs Final quality, deterministic replay
└── workspace.py      -> Interactive Studio UI (Photograph viewport, 3D Studio viewport, Inspector)
```

---

### 5. Recommended Implementation Sequence

1. **Phase 1: Scene & Camera Foundation:** Build `StudioScene` dataclass, JSON serialization/deserialization, undo/redo state manager, and 3D Camera coordinate transforms.
2. **Phase 2: Analytical Geometry Foundation:** Implement OBB, Superquadric Ellipsoid, Low-Poly Mesh, Ground Plane, and Curved Cyclorama Cove with ray intersections and normal estimation.
3. **Phase 3: Lighting & Shadow Engine:** Implement Rectangular Area Light, Monte Carlo emitter sampling, direct diffuse response, geometric cast shadows, and contact grounding.
4. **Phase 4: Image Preservation & Uncertainty:** Implement linear-light pipeline, texture-preserving E.1 reconstruction, and multi-channel uncertainty supervisor.
5. **Phase 5: Artist Workspace UI:** Build the interactive studio interface with Photograph Viewport, 3D Virtual Studio Viewport, and Context Inspector.
6. **Phase 6: Experiments, Benchmarks & Validation:** Run test suite across all 5 object categories, evaluate quantitative acceptance gates, benchmark performance, and compile visual evidence.
