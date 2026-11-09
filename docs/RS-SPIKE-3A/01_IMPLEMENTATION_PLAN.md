# RELIGHT STUDIO — RS-SPIKE-3A
## 01_IMPLEMENTATION_PLAN: Detailed Engineering Implementation Plan

- **Document ID:** RS-SPIKE-3A-PLAN-v1.0
- **Author:** Principal Computational Photography Engineer & Systems Architect
- **Date:** 2026-11-09
- **Status:** APPROVED IMPLEMENTATION BLUEPRINT

---

### 1. Implementation Roadmap & Milestones

This engineering implementation plan translates the product requirements of RS-SPIKE-3A into an executable, verifiable sequence of software components:

```
+===================================================================================================+
|                                  RS-SPIKE-3A IMPLEMENTATION PHASES                                 |
+===================================================================================================+

  [ PHASE 1: SCENE & CAMERA FOUNDATION ]
  - StudioScene serializable schema (Camera, Subject, Receivers, Lights, Settings)
  - Deterministic JSON serializer / deserializer
  - Undo/Redo SceneStateManager with snapshot ring buffer
  - Vectorized 3D pinhole camera with image-plane registration

  [ PHASE 2: GEOMETRY ENGINE ]
  - Oriented Bounding Box (OBB) with Kay-Kajiya slab intersection
  - Superquadric Ellipsoid with robust sign-preserving ray intersection
  - Low-Poly Mesh with triangle Möller-Trumbore intersection & BVH
  - Parametric Receivers: Infinite/Bounded Ground Plane & Curved Cyclorama Fillet

  [ PHASE 3: LIGHTING & SHADOW ENGINE ]
  - Rectangular Area Light (position, orientation, width, height, color, temperature)
  - Fixed Radiance vs. Fixed Total Power energy conventions
  - Direct diffuse irradiance with geometric cosine falloff
  - Independent geometric visibility: Direct, Self-Occlusion, Cast Shadow, Contact

  [ PHASE 4: UNCERTAINTY & RECONSTRUCTION SAFEGUARDS ]
  - Multi-channel uncertainty supervisor (sigma_geom^2, sigma_occl^2, sigma_mat^2)
  - Non-destructive linear-light reconstruction contract
  - Texture preservation via E.1 guided-filter log-luminance ratio
  - Gamut protection via C3 Oklab constant-hue chroma mapping

  [ PHASE 5: ARTIST WORKSPACE APPLICATION ]
  - Dual-viewport workspace:
    * Viewport 1: Photograph Viewport (original, relit, before/after, overlays)
    * Viewport 2: Virtual 3D Studio Viewport (camera frustum, 3D proxies, light quad)
  - Inspector with context-sensitive controls for light, proxy, receiver
  - Interactive Gradio/FastAPI application + headless CLI harness

  [ PHASE 6: AUTOMATED TEST SUITE & EXPERIMENTAL EVALUATION ]
  - Comprehensive unit test suite across 6 test domains
  - Experimental validation across 5 product categories (Box, Bottle, Shoe, Watch, Organic)
  - Performance profiling (latency p50/p95, memory, resolutions)
  - Compilation of visual evidence and final milestone documentation
```

---

### 2. Phase-by-Phase Technical Specifications

#### Phase 1: Scene & Camera Foundation (`studio3a/scene.py`, `studio3a/camera.py`)
- **`StudioScene` Dataclass:**
  - `metadata`: Name, creation timestamp, author, version.
  - `camera`: Position $(x, y, z)$, Target $(x, y, z)$, Up vector, FOV (degrees), Image width, Image height, Focal length estimate.
  - `subject`: Proxy geometry type (`OBB`, `SUPERQUADRIC`, `MESH`), Transform (position, rotation euler, scale), Dimensions, Uncertainty parameters.
  - `receivers`: List of receivers (`PLANE`, `CYCLORAMA`), with ground level $Y_{\text{floor}}$, fillet radius $R_{\text{cove}}$, wall distance $Z_{\text{wall}}$.
  - `lights`: List of `AreaLight` definitions (position, rotation, width, height, intensity, color RGB, temperature Kelvin, energy convention, enabled flag).
  - `render_settings`: Quality mode (`PREVIEW`, `FINAL`), shadow sample count, resolution scale.
- **Serialization & Invariants:**
  - Round-trip fidelity: `scene == StudioScene.from_dict(scene.to_dict())`.
  - Finite validation: Check all floats for NaN / Inf before serialization.
  - Coordinate system: World space is Right-Handed ($+X$ right, $+Y$ up, $+Z$ towards camera; origin at ground center $[0, 0, 0]$).

#### Phase 2: Geometry Engine (`studio3a/geometry.py`)
- **OBB:**
  - Slab-based ray-box intersection. Transforms incident rays into local box coordinates via inverse rotation and translation $\mathbf{x}' = \mathbf{R}^T (\mathbf{x} - \mathbf{c})$.
- **Superquadric Ellipsoid:**
  - Canonical equation:
    $$\left( |x/r_x|^{2/\epsilon_2} + |y/r_y|^{2/\epsilon_2} \right)^{\epsilon_2/\epsilon_1} + |z/r_z|^{2/\epsilon_1} = 1$$
  - Solves intersection numerically along ray $\mathbf{p}(t) = \mathbf{o} + t \mathbf{d}$ using robust bounding-sphere interval bracketing and Newton-Raphson refinement.
  - Computes exact analytical gradient $\nabla \mathcal{F}(x, y, z)$ for outward surface normals.
- **Low-Poly Mesh:**
  - Triangular mesh loader and Möller-Trumbore ray-triangle intersection.
  - Includes a representative 280-triangle footwear sole hull fixture.
- **Receivers:**
  - Ground Plane: $Y = Y_{\text{floor}}$.
  - Curved Cyclorama Cove: Piecewise continuous fillet connecting floor at $Z = -0.80$ to vertical wall at $Z = -1.20$, $Y = 0.40$ with radius $R = 0.40$.

#### Phase 3: Lighting & Shadow Engine (`studio3a/lighting.py`, `studio3a/shadows.py`)
- **Area Light Model:**
  - Emitter quad specified by center $\mathbf{c}_L$, normal $\mathbf{n}_L$, tangent $\mathbf{u}_L$, and dimensions $(w_L, h_L)$.
  - Jittered Stratified Monte Carlo sampling: Evaluates $N$ emitter sample points $\mathbf{x}_{L, i} = \mathbf{c}_L + u_i w_L \mathbf{u}_L + v_i h_L \mathbf{v}_L$.
  - Energy Conventions:
    - `FIXED_RADIANCE`: Emitter surface brightness $L_e$ is constant; total emitted power scales with $w_L \times h_L$.
    - `FIXED_POWER`: Total flux $\Phi$ is constant; surface radiance $L_e = \frac{\Phi}{w_L \times h_L}$.
- **Shadow Visibility Decoupling:**
  - Direct Visibility: $V_{\text{direct}}(x, y) \in [0, 1]$.
  - Self-Occlusion: Evaluated on subject surface against proxy geometry.
  - Cast Shadows: Evaluated on receiver geometry by casting shadow rays towards area-light emitter samples.
  - Contact Occlusion: Near-field proximity darkening ($d < 25\text{ px}$).

#### Phase 4: Uncertainty & Reconstruction (`studio3a/uncertainty.py`, `studio3a/reconstruction.py`)
- **Uncertainty Supervisor:**
  - Channel 1 ($\sigma_{\text{geom}}^2$): Surface normal silhouette divergence and depth cliff edge proximity.
  - Channel 2 ($\sigma_{\text{occl}}^2$): Ray travel distance through unobserved space behind proxy.
  - Channel 3 ($\sigma_{\text{mat}}^2$): Original high-frequency texture variance.
- **Image Preservation Contract:**
  - The source photograph is treated as immutable read-only input.
  - The lighting engine computes an irradiance ratio $R(x, y) = \frac{E_{\text{new}}(x, y)}{E_{\text{orig}}(x, y)}$.
  - E.1 Guided Filter regularizes $\ln R$ using the original image luminance as guide, guaranteeing zero texture loss and no edge halos ($DCI \ge 0.998$).

#### Phase 5: Artist Workspace UI (`studio3a/workspace.py`)
- Built using Gradio / FastAPI:
  - **Photograph Viewport:** High-resolution display of original image, relit output, side-by-side / split before-after comparison, and diagnostic overlay toggles (proxy wireframe, shadow mask, error map).
  - **Virtual 3D Studio Viewport:** 3D rendered view of the virtual stage from an adjustable perspective, displaying the camera frustum, subject proxy, receiver, and rectangular area light with position/rotation gizmo.
  - **Inspector Panel:** Full interactive controls for 3D light position, rotation, dimensions, intensity, temperature, proxy selection and dimensions, receiver type, undo/redo, and scene save/load.

#### Phase 6: Automated Test Suite & Validation (`tests/RS-SPIKE-3A/`, `experiments/RS-SPIKE-3A/`)
- Unit test suites across 6 dedicated directories:
  1. `tests/RS-SPIKE-3A/geometry/`: Ray intersections, normals, transformations, bounding checks.
  2. `tests/RS-SPIKE-3A/camera/`: Projection, image alignment, world-camera transforms.
  3. `tests/RS-SPIKE-3A/lighting/`: Area light sampling, energy conservation, distance falloff.
  4. `tests/RS-SPIKE-3A/shadows/`: Cast shadow accuracy on planes and cycloramas, contact grounding.
  5. `tests/RS-SPIKE-3A/reconstruction/`: Original image immutability, detail preservation, gamut safety.
  6. `tests/RS-SPIKE-3A/scene_state/`: JSON serialization, undo/redo, deterministic replay.
- Benchmarking on Apple Silicon hardware, evaluating preview ($< 5\text{ ms}$) and studio ($< 35\text{ ms}$) targets.

---

### 3. Execution Schedule & Deliverable Milestones

| Step | Tasks & Code Modules | Verification Artifacts |
| :---: | :--- | :--- |
| **Step 1** | Implement `studio3a/scene.py` and `studio3a/camera.py` | Unit tests in `tests/RS-SPIKE-3A/scene_state/` and `camera/` |
| **Step 2** | Implement `studio3a/geometry.py` (OBB, Superquadric, Mesh, Cyclorama) | Unit tests in `tests/RS-SPIKE-3A/geometry/` |
| **Step 3** | Implement `studio3a/lighting.py` and `studio3a/shadows.py` | Unit tests in `tests/RS-SPIKE-3A/lighting/` and `shadows/` |
| **Step 4** | Implement `studio3a/uncertainty.py` and `studio3a/reconstruction.py` | Unit tests in `tests/RS-SPIKE-3A/reconstruction/` |
| **Step 5** | Implement `studio3a/renderer.py` and `studio3a/workspace.py` | End-to-end workflow verification |
| **Step 6** | Execute experimental test manifest & hardware benchmarks | Generate output images and benchmark JSONs |
| **Step 7** | Author all 8 remaining documentation reports in `docs/RS-SPIKE-3A/` | Final ratified documentation suite |
