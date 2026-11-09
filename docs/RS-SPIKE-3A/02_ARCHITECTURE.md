# RELIGHT STUDIO — RS-SPIKE-3A
## System Architecture Specification: Artist-Controlled Virtual 3D Studio Foundation

**Document:** `docs/RS-SPIKE-3A/02_ARCHITECTURE.md`  
**Status:** Approved Engineering Baseline  
**Milestone:** RS-SPIKE-3A  
**Date:** November 2026  

---

### 1. Executive Architectural Overview

Relight Studio provides a virtual lighting studio ("virtual gaffer") for commercial and product photography. The objective of Milestone RS-SPIKE-3A is to transition the system from historical 2.5D image-space screen-space heuristics (which failed in Spike 2.1/2.2 due to depth disocclusion, non-monotonic light falloff, and geometric distortion) to a **scene-driven hybrid 3D rendering architecture**.

In this architecture:
1. An artist loads an immutable, non-destructive original photograph.
2. A virtual 3D camera is aligned to match the photograph's field of view and viewpoint.
3. Parametric subject proxies (Oriented Bounding Box, Superquadric Ellipsoid, Low-Poly Mesh) and receiver geometry (Infinite Ground Plane, Curved Cyclorama Cove) are positioned in world space.
4. An artist creates and manipulates physical rectangular area lights with real 3D spatial transforms, dimensions, intensities, and blackbody color temperatures.
5. Direct diffuse irradiance and area-light visibility (soft penumbra cast shadows and contact occlusion) are evaluated in 3D world space using analytical ray tracing and stratified Monte Carlo area-light sampling.
6. The resulting physical lighting ratio is transferred back to the original photograph via non-destructive linear-light reconstruction (E.1 Guided-Filter Regularized Shading Ratio + C3 Oklab Gamut Mapping with Constant-Hue Chroma Reduction).

```
                      +---------------------------------------+
                      |         Immutable Photograph          |
                      |        (sRGB -> Linear Radiance)      |
                      +-------------------+-------------------+
                                          |
                                          v
+------------------------+      +-------------------+      +-------------------------+
|   3D Virtual Studio    | ---> | Hybrid Renderer   | <--- | Uncertainty Supervisor  |
| - Camera3D             |      | - Analytical Rays |      | - Sigma_geom (cliff/grez)
| - Proxies (OBB/Mesh)   |      | - Stratified MC   |      | - Sigma_occl (silhouette)
| - Receivers (Cyc/Floor)|      | - Area Light Quad |      | - Sigma_mat (variance)  |
| - RectangularAreaLight |      +---------+---------+      +-------------------------+
+------------------------+                |
                                          v
                                +-------------------+
                                | Shading Ratio R   |
                                +---------+---------+
                                          |
                                          v
                      +---------------------------------------+
                      | E.1 Guided-Filter Detail Preservation |
                      | C3 Oklab Constant-Hue Gamut Mapping   |
                      | Protected Zero-Mutation Pass-Through  |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |     Relit Output / Before-After       |
                      |       (Photographic Fidelity)         |
                      +---------------------------------------+
```

---

### 2. Core Subsystems and Component Responsibilities

#### 2.1 Scene Subsystem (`studio3a/scene.py`)
- **Authoritative Scene Definition (`StudioScene`):** Single source of truth containing `CameraData`, `SubjectProxyData`, `ReceiverData`, `AreaLightData`, and `RenderSettingsData`.
- **Validation Pipeline:** Strict numerical bounds checking (`_validate_finite_float`, positive dimensions, non-zero camera distances). Rejects NaN, Inf, and physically nonsensical values.
- **Serialization & Deserialization:** Complete JSON round-trip serialization ensuring deterministic reloads.
- **State Management (`SceneStateManager`):** Fixed-capacity circular snapshot history supporting lossless undo/redo actions for artist workflows.

#### 2.2 Camera Subsystem (`studio3a/camera.py`)
- **Right-Handed Standard Coordinate System:** $+X$ points right, $+Y$ points up, $+Z$ points backwards towards the viewer.
- **Orthonormal Basis Generation:** Computes forward, right, and up vectors from look-at targets with singularity handling for collinear up vectors.
- **Projection & Ray Generation:**
  - Pin-hole perspective projection with horizontal field-of-view (`fov_deg`).
  - Generates normalized primary ray directions $D(u, v)$ in world space for arbitrary screen resolutions $(W, H)$.

#### 2.3 Geometry Subsystem (`studio3a/geometry.py`)
- **Analytical Geometric Ray Tracers:**
  - `OrientedBoundingBox`: Slab method intersection with world-to-local transformation, computing exact hit positions and surface normals.
  - `SuperquadricEllipsoid`: Numerical root finding via bounded line search and linear interpolation on the inside-outside function $F(x, y, z) = (|x/a|^{2/e_2} + |y/b|^{2/e_2})^{e_2/e_1} + |z/c|^{2/e_1} - 1$, analytical gradient evaluation for exact normal vectors.
  - `LowPolyMesh`: Procedural footwear hull (~280 triangles) with vectorized Möller-Trumbore ray-triangle intersection.
  - `GroundPlaneReceiver`: Infinite analytical horizontal plane $Y = Y_{\text{plane}}$ with normal $[0, 1, 0]^T$.
  - `CycloramaReceiver`: Continuous piecewise smooth surface comprised of:
    1. Flat floor: $Y = Y_{\text{floor}}, Z \ge Z_{\text{cove\_start}}$
    2. Cylindrical fillet cove: $Y_{\text{floor}} \le Y \le Y_{\text{cove\_top}}, Z_{\text{wall}} \le Z < Z_{\text{cove\_start}}$
    3. Vertical seamless wall: $Z = Z_{\text{wall}}, Y \ge Y_{\text{cove\_top}}$
    Intersection evaluates both cylinder quadratic roots to prevent misses on the concave interior surface.

#### 2.4 Lighting Subsystem (`studio3a/lighting.py`)
- **Rectangular Area Light (`RectangularAreaLight`):**
  - Rigid 3D transform (position, pitch, yaw, roll).
  - Explicit physical dimensions: width $w$ and height $h$.
  - Stratified jittered Monte Carlo emitter sampling: breaks rectangular surface into $S_u \times S_v$ grids with uniform stratified random offsets, yielding unbiased area integration.
  - Planckian Blackbody Color Temperature: Converts Kelvin temperature ($1000\text{K} - 12000\text{K}$) to physical chromaticity coordinates and linear RGB multipliers.
  - Dual Energy Conventions:
    - `FIXED_RADIANCE`: Total power scales proportionally with emitter area ($P \propto A$). Intensity represents radiance $L_e$.
    - `FIXED_POWER`: Radiance scales inversely with emitter area ($L_e = I / A$), preserving total scene illumination when resizing softboxes.
- **Direct Diffuse Evaluation:**
  Evaluates Lambertian cosine law $\cos \theta = \max(N \cdot L, 0)$ and inverse-square distance attenuation $1 / d^2$ for each stratified light sample.

#### 2.5 Shadow & Contact Subsystem (`studio3a/shadows.py`)
- **Physical Decoupling:** Separates cast shadow visibility from near-field contact ambient occlusion.
- **Monte Carlo Shadow Penumbra:** Traces shadow test rays from surface points to stratified area-light sample points. Unoccluded fraction yields smooth, physically authentic penumbral transitions without artificial blur kernels.
- **Cyclorama Shadow Transport:** Analytical ray-receiver intersection captures continuous shadow trajectories transitioning seamlessly across the floor, circular fillet, and vertical wall.
- **Contact Grounding ($C_{\text{contact}}$):** Near-field proximity evaluation attenuating ambient illumination at crevices and contact points between proxy geometries and receiver surfaces.

#### 2.6 Uncertainty Supervisor (`studio3a/uncertainty.py`)
- Evaluates per-pixel confidence to prevent artifacts at unconstrained geometry boundaries:
  - $\sigma_{\text{geom}}^2$: Depth cliff discontinuities and grazing surface normal angles ($N \cdot V \approx 0$).
  - $\sigma_{\text{occl}}^2$: Hidden back-volume silhouette distance.
  - $\sigma_{\text{mat}}^2$: Photographic texture variance indicating unmodeled high-frequency surface detail.
- Generates composite confidence map $\alpha = 1 / (1 + \sigma_{\text{total}}^2)$ used to smoothly blend reconstructed illumination back to the original photograph.

#### 2.7 Reconstruction Engine (`studio3a/reconstruction.py`)
- **Non-Destructive Processing:** The original photograph is preserved in memory as the immutable radiometric ground truth.
- **E.1 Guided-Filter Regularized Shading Ratio:**
  Decomposes linear radiance into base and detail layers. The regularized shading ratio $R = Y_{\text{relit}} / (Y_{\text{orig}} + \epsilon)$ modulates the base illumination while high-frequency micro-contrast and photographic textures are preserved without haloing.
- **C3 Oklab Constant-Hue Gamut Mapping:**
  Converts relit linear RGB to the perceptual Oklab color space $(L, a, b)$. For colors exceeding the displayable sRGB gamut, bisection along the radial chroma vector preserves exact perceptual hue and target lightness while eliminating color clipping artifacts.
- **Protected Region Pass-Through:**
  Pixel regions marked as protected (or outside the proxy/receiver footprint) undergo bitwise zero-mutation passthrough.

#### 2.8 Interactive Artist Workspace (`studio3a/workspace.py`)
- **Dual-Viewport Presentation:**
  - Viewport 1 (Photograph Viewport): Displays Original, Relit, Before/After Wipe, and 3D Wireframe Overlay.
  - Viewport 2 (Virtual 3D Stage Viewport): 3/4 perspective isometric render showing the 3D ground plane, cyclorama cove curve, camera frustum, subject proxy wireframe, and 3D rectangular area light quad with normal indicator.
- **Context Inspector:**
  - Real-time parameter sliders for light position $(X, Y, Z)$, rotation (pitch, yaw, roll), dimensions (width, height), intensity, and temperature (Kelvin).
  - Proxy selector (Box, Superquadric, Mesh) and receiver selector (Floor, Cyclorama).
  - Undo, Redo, Save Scene JSON, and Load Scene JSON actions.

---

### 3. Rendering Pipeline Flow

```
[Start Render Frame]
        |
        v
[1. Generate Camera Rays for Image Dimensions (W, H)]
        |
        v
[2. Intersect Rays with Scene Proxy & Receiver Geometry]
        |-- Hit Mask, World Hit Positions P, Surface Normals N
        |
        v
[3. Area Light Stratified Sampling (S samples)]
        |-- Sample positions on emitter quad, normal N_light, sample area
        |
        v
[4. Direct Diffuse Irradiance & Shadow Evaluation]
        |-- For each sample: evaluate distance d, cos(theta_light), cos(theta_surf)
        |-- Trace shadow test ray from P to sample position
        |-- Accumulate unoccluded irradiance: E = sum(V_i * L_e * cos(theta_i) * cos(phi_i) * dA / d^2)
        |
        v
[5. Contact Grounding Evaluation]
        |-- Compute proximity to contact receiver: C_contact in [0, 1]
        |-- Total target illumination: E_total = E * (1 - C_contact * k_contact)
        |
        v
[6. Ratio Computation & Uncertainty Masking]
        |-- Compute reference original illumination: E_orig
        |-- Compute shading ratio: R = E_total / (E_orig + epsilon)
        |-- Apply uncertainty weighting: R_blended = lerp(1.0, R, confidence)
        |
        v
[7. Non-Destructive Reconstruction Pass]
        |-- Guided filter detail decomposition on original photograph
        |-- Modulate base layer with R_blended
        |-- Recombine details to obtain relit linear luminance
        |-- Apply C3 Oklab gamut mapping with constant-hue chroma reduction
        |-- Enforce bitwise zero-mutation on protected pixels
        |
        v
[8. Display Output / Stage Viewport Generation]
```

---

### 4. Deterministic Replay and State Integrity

A core mandate of RS-SPIKE-3A is deterministic replay:
- All scene configurations are fully described by the plain-text JSON structure defined in `studio3a/scene.py`.
- Saving a scene to JSON and reloading it reproduces the exact camera matrix, light transform, proxy geometry, receiver parameters, and rendering settings.
- When re-rendered with identical quality settings and random seeds, the resulting pixel buffers are mathematically identical ($\text{error} = 0.0$).
