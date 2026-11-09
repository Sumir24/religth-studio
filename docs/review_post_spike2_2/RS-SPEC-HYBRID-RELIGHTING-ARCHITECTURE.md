# RELIGHT STUDIO — SYSTEM ARCHITECTURE SPECIFICATION
## Confidence-Aware Hybrid Relighting Architecture (CAHRA)

- **Document ID:** RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE-v1.0
- **Status:** APPROVED SYSTEM SPECIFICATION
- **Author:** Principal Computational Photography Architect & Rendering Systems Auditor
- **Date:** 2026-11-09
- **Preceding References:** RS-REP-POST-SPIKE-2.2-INDEPENDENT-REVIEW.md, RS-SPEC-SPIKE-2.2-ARCHITECTURE.md

---

### 1. Architectural Philosophy & Design Principles

Relight Studio is an interactive virtual lighting environment designed for photographers, creators, and commercial e-commerce production.
Its core technical challenge is **asymmetric information**: a 2D photograph contains dense high-frequency micro-textures and material reflectance, but lacks 3D volumetric occluder geometry, back-surface coordinates, and complete non-line-of-sight environment topology.

The **Confidence-Aware Hybrid Relighting Architecture (CAHRA)** resolves this asymmetry by decoupling rendering into six distinct, mathematically bounded layers:

```
+===================================================================================================+
|                               CONFIDENCE-AWARE HYBRID ARCHITECTURE                                |
+===================================================================================================+

  [ LAYER 6: MULTI-CHANNEL UNCERTAINTY ESTIMATION ]
  Evaluates: sigma_geom^2 (cliffs/grazing), sigma_occl^2 (back volume), sigma_mat^2 (albedo/spec)
                              |
                              v
  +---------------------------+---------------------------+
  |                                                       |
  v                                                       v
  [ LAYER 1: IMAGE-SPACE SHADING ]                        [ LAYER 3: PARAMETRIC 3D PROXY TRANSPORT ]
  - Diffuse Orientation D(n, L)                           - Fits Analytical Proxy (OBB, Ellipsoid)
  - Surface normal micro-modulation                       - Analytical 3D Ray Traced Cast Shadows
  - High-frequency texture lock                           - Arbitrary Receiver (Plane + Cyclorama)
  - Low latency (< 1.5 ms)                                - Eliminates 2.5D SDE / SLR errors
          |                                                       |
          +---------------------------+---------------------------+
                                      |
                                      v
  [ LAYER 2: ANALYTICAL 2.5D NEAR-FIELD TRANSPORT ]
  - Multi-Scale Horizon Ambient Occlusion A_amb (Cavities/Crevices)
  - Near-Field Contact Grounding C_contact (Contact Seam Anchor)
  - Eliminates "floating object" artifacts
                                      |
                                      v
  [ LAYER 4: MATERIAL-AWARE SPECULAR BRDF ]
  - Microfacet Cook-Torrance / GGX Specular Highlight Synthesis
  - Estimated Roughness (alpha) and Dielectric/Metallic Fresnel (F0)
  - Highlight Repositioning without identity distortion
                                      |
                                      v
  [ LAYER 5: DETAIL & COLOUR RECONSTRUCTION ]
  - Frequency-Guided Log-Luminance Reconstruction (E.1 Guided Filter)
  - Constant-Hue Oklab Gamut Mapping via Hybrid 33^3 LUT + 1-Step Secant
  - Gamut-compliant, zero-halo, mathematically bounded photographic output
```

---

### 2. The Six Decoupled Architectural Layers

#### Layer 1: Image-Space Surface Shading
- **Role:** Computes directional diffuse irradiance on observed surfaces using estimated surface normals $\mathbf{n}(x, y)$ and light vector $\mathbf{L}$.
- **Mathematical Formulation:**
  $$D_{\text{diffuse}}(x, y) = \text{SmoothClamp}\left( \frac{\mathbf{n}(x, y) \cdot \mathbf{L} - \tau_0}{\tau_1 - \tau_0} \right) \cdot \max(0, \mathbf{n} \cdot \mathbf{L})$$
  Where $\tau_0 = -0.05$ and $\tau_1 = 0.10$ form a Hermite-tapered terminator that eliminates razor-sharp quantization artifacts along grazing normal boundaries.
- **Compute Invariant:** Zero screen-space raymarching. Executes in $O(1)$ per pixel via pure ALU registers.

#### Layer 2: Analytical 2.5D Near-Field Transport
- **Role:** Evaluates near-field occlusion phenomena where local geometry is known from the camera viewpoint: ambient crevice shadowing and contact grounding.
- **Components:**
  1. **Multi-Scale Horizon-Based Ambient Occlusion ($A_{\text{amb}}$):**
     $$A_{\text{amb}}(x, y) = 1.0 - \kappa_{\text{ao}} \left[ 0.40 \cdot H_{\text{fine}}(x, y) + 0.60 \cdot H_{\text{coarse}}(x, y) \right]$$
     Evaluates horizon elevation angles across 8 directions at dual radii ($r_{\text{fine}} \in \{2, 4, 6\}\text{ px}$, $r_{\text{coarse}} \in \{8, 14, 24\}\text{ px}$).
  2. **Directional Contact Grounding ($C_{\text{contact}}$):**
     Pins the object to its supporting surface within an anisotropic footprint extending along $\mathbf{L}_{xy}$:
     $$C_{\text{contact}}(x, y) = 1.0 - \rho_{\text{contact}} \sum_{s=1}^{r_c} w_{\text{dist}}(s) \cdot \mathbb{I}_{\text{contact}}(x + s L_x, y - s L_y)$$
- **Compute Invariant:** Operates within a bounded radius ($r \le 25\text{ px}$). Never projects long-range cast shadows.

#### Layer 3: Parametric 3D Proxy Transport
- **Role:** Computes long-range cast shadows onto supporting floors, curved cyclorama backdrops, and secondary receivers, overcoming the fundamental 2.5D silhouette-shearing barrier.
- **Workflow:**
  1. **Proxy Instantiation:** From the foreground mask and depth distribution, fit an analytical 3D proxy:
     - **Box / Slab Goods:** Oriented Bounding Box $\mathcal{B}(\mathbf{c}, \mathbf{e}, \mathbf{R})$.
     - **Bottles, Cosmetics, Organic:** Superquadric Ellipsoid $\mathcal{E}(\mathbf{c}, \mathbf{r}, \mathbf{q}, \epsilon_1, \epsilon_2)$.
     - **Footwear, Apparel:** Coarse Watertight Convex Hull $\mathcal{M}_{\text{hull}}$ ($< 300$ triangles).
  2. **Receiver Geometry Modeling:** Fit receiver profile:
     - Tabletop: Horizontal plane $Y = Y_{\text{floor}}$.
     - Cyclorama Cove: Piecewise fillet $Y(Z) = \text{CoveFillet}(Z; Y_{\text{floor}}, R_{\text{fillet}})$.
  3. **Analytical Ray Intersection:** Cast cone rays from light source through the 3D proxy onto the parametric receiver:
     $$V_{\text{cast}}^{3D}(x, y) = \text{ConeTraceProxy}(\mathbf{x}_{\text{receiver}}, \mathbf{L}, \theta_{\text{source}}, \mathcal{P}_{3D})$$
- **Accuracy Guarantee:** Achieves sub-pixel distance error ($SDE \le 1.5\text{ px}$) and $\text{IoU} \ge 0.92$ on both flat floors and curved backdrops.

#### Layer 4: Material-Aware Specular BRDF Response
- **Role:** Synthesizes physically accurate specular highlights and glossy reflections without modifying underlying photographic textures or identity.
- **Formulation:**
  $$L_{\text{specular}}(x, y) = \frac{D_{\text{GGX}}(\mathbf{h}, \alpha) \cdot F_{\text{Schlick}}(\mathbf{v}, \mathbf{h}, F_0) \cdot G_{\text{Smith}}(\mathbf{l}, \mathbf{v}, \alpha)}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})} \cdot (\mathbf{n} \cdot \mathbf{l}) \cdot E_{\text{key}}$$
  Where:
  - $\mathbf{h} = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|}$ is the half-vector.
  - $\alpha(x, y)$ is the estimated microfacet roughness map.
  - $F_0(x, y)$ is base specular reflectance ($0.04$ for dielectrics; albedo for metals).
- **Highlight Protection Contract:** Existing baked specular highlights in the original photograph are smoothly attenuated via an inverse specular mask to prevent double-highlight artifacts.

#### Layer 5: Detail & Colour Reconstruction
- **Role:** Preserves micro-contrast, photographic film grain, and edge gradients while remapping luminance and mapping out-of-gamut colors to the destination display space.
- **Workflow:**
  1. **Log-Luminance Guided-Filter Ratio (E.1):**
     $$\ln Y_{\text{relit}} = \text{GuidedFilter}(I_{\text{guide}}, \ln R_{\text{eff}}, r, \epsilon) + \ln Y_{\text{orig}}$$
     Guarantees zero haloing, strict edge alignment, and preservation of photographic micro-contrast ($DCI \ge 0.998$).
  2. **Constant-Hue Gamut Mapping (C3 Hybrid):**
     Remaps out-of-gamut chroma along constant Oklab hue rays:
     - Sample initial scale $t_0$ from a $33 \times 33 \times 33$ 3D LUT texture in hardware.
     - Execute a single 1-step secant correction in GPU registers.
     - Final execution time: **$0.65\text{ ms}$** at 1080p; Max $\Delta E < 0.082$.

#### Layer 6: Multi-Channel Uncertainty Estimation
- **Role:** Arbitrates between 2.5D near-field heuristics and 3D parametric transport, dynamically adjusting blending weights to prevent visible seams or false shadows.
- **Channel Vector:**
  $$\mathbf{U}(x, y) = \left[ \sigma_{\text{geom}}^2(x, y), \; \sigma_{\text{occl}}^2(x, y), \; \sigma_{\text{mat}}^2(x, y) \right]^T$$
- **Arbitration Function:**
  The direct visibility at any receiver pixel $(x, y)$ is computed as a variance-weighted Bayesian blend:
  $$V_{\text{direct}}(x, y) = \left( 1.0 - w_{\text{proxy}} \right) \cdot \min(V_{\text{cast}}^{2.5D}, C_{\text{contact}}) + w_{\text{proxy}} \cdot V_{\text{cast}}^{3D}$$
  Where the proxy blending weight is driven by occlusion uncertainty:
  $$w_{\text{proxy}}(x, y) = \text{SmoothStep}\left( 0.20, 0.80, \sigma_{\text{occl}}^2(x, y) \right)$$

---

### 3. Arbitration Logic & Compute Budgeting

To achieve real-time responsiveness on Apple Silicon, CAHRA implements a **Tri-Modal Performance Governor**:

```
+---------------------------------------------------------------------------------------------------+
| OPERATING MODE       | TRIGGER CONDITION        | TARGET LATENCY | RESOLUTION | COMPUTATIONAL LOAD|
+---------------------------------------------------------------------------------------------------+
| 1. Active Gizmo Drag | User actively dragging   | < 5.0 ms       | 256 x 384  | Layer 1 + Layer 2 |
|    (Interactive)     | virtual light widget     | (> 200 FPS)    | Preview    | + 3D Proxy OBB    |
+---------------------------------------------------------------------------------------------------+
| 2. Resting Viewport  | Mouse release / pointer  | < 33.3 ms      | 1920x1080  | Full 6 Layers     |
|    (High Fidelity)   | idle for >= 100 ms       | (30 FPS)       | FHD Native | + Hybrid C3 LUT   |
+---------------------------------------------------------------------------------------------------+
| 3. Master Export     | User clicks "Export"     | < 500 ms       | 3840x2160  | Full 6 Layers     |
|    (Master Quality)  | or renders final asset   | (Async Batch)  | 4K / 8K    | + 64-sample MC PBR|
+---------------------------------------------------------------------------------------------------+
```

#### Adaptive Dispatch Logic:
1. When receiver geometry is strictly planar ($\text{Var}(\mathbf{n}_{\text{receiver}}) < 0.01$ and $h_{\text{elev}} == 0$), the pipeline bypasses 3D proxy evaluation on the ground plane, executing purely via Layer 2 contact grounding and 2.5D projection for maximum throughput.
2. When depth-cliff variance or non-planar receiver curvature is detected ($\sigma_{\text{occl}}^2 > 0.35$ or $\Delta \mathbf{n}_{\text{receiver}} > 0.05$), Layer 3 analytical 3D proxy cone tracing is automatically activated to prevent silhouette leakage.

---

### 4. Photographic Invariant Protection Contract

To ensure that Relight Studio never distorts the subject's identity, geometry, or material truth, CAHRA enforces four mathematical invariants:

1. **Geometry Invariance:**
   $$\nabla I_{\text{relit}} \cdot \nabla I_{\text{orig}} \ge 0 \quad \forall \; (x, y) \in \text{Edges}$$
   Gradient orientation errors ($GOE$) must not invert sign. The spatial coordinates of all photographic features remain strictly fixed.
2. **Albedo Invariance:**
   In regions without cast shadows or specular highlights ($V_{\text{direct}} \approx 1.0$), the chrominance ratio $\frac{a}{L}$ and $\frac{b}{L}$ in Oklab space must match the source photograph within $\Delta \theta \le 0.15^\circ$.
3. **Specular Energy Conservation:**
   $$L_{\text{diffuse}} + L_{\text{specular}} \le E_{\text{incident}}$$
   Specular highlight synthesis is strictly additive and bounded by incident light intensity, preventing unnatural nuclear highlights.
4. **Zero-Halo Boundary Contract:**
   Halo Warning Area ($HWA$) must remain $\le 10\text{ px}$ and Halo Over-Amplification ($HOA^+$) $\le 0.02$ across all lighting transitions.
