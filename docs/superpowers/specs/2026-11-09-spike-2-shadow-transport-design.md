# RELIGHT STUDIO — SPIKE 2 ARCHITECTURE SPECIFICATION
## Shadow Transport, Contact Grounding, and Geometric Uncertainty

**Document ID:** RS-SPEC-SPIKE-2-v1.0  
**Phase:** Stage 2 Experimental Architecture & Validation  
**Preceding Validation Baseline:** Spike 1 (RS-REP-SPIKE-1-v1.1, Git `ed8bdcc`)  
**Provisional Reconstruction Pipeline:** Paradigm E.1 (Guided Ratio Regularization) + Method C3 (Oklab Gamut Mapping)  
**Execution Target:** Isolated Prototype `spike_shadow_transport.py`  
**Date:** 2026-11-09  
**Status:** DRAFT SPECIFICATION — READY FOR REVIEW  

---

## 1. FIRST-PRINCIPLES PROBLEM ANALYSIS & GEOMETRIC UNCERTAINTY

### 1.1 The Fundamental Missing Information in 2.5D Relighting
A single photograph $I(x, y)$ records radiant exitance along primary camera rays. Even when paired with estimated monocular depth $Z(x, y)$ (e.g., Depth Anything V2) and surface normals $\mathbf{n}(x, y)$, the geometric representation is strictly **2.5D (a single-valued heightfield)**:
1. **No Back-Surface Geometry:** The rear, bottom, and occluded flanks of objects are completely unknown.
2. **Invisible Occluders:** Any shadow cast by an object part outside the camera's field of view (or behind another surface) cannot be traced deterministically.
3. **Depth Quantization and Discontinuities:** Monocular depth estimates have ambiguous scale, non-linear metric distortion, and sharp step discontinuities ("depth cliffs") at object silhouettes.
4. **Receiver Ambiguity:** A single image does not state whether the object is resting on a horizontal tabletop, sitting on an infinite floor, or floating in front of a vertical wall.

```
       Light Source L
            \
             \
              \   Foreground Object
               \     (Known Front)
                \       .---.
                 \     /     \
                  \   |       |  <--- Missing Backside Geometry!
                   \   \     /       (Cannot raymarch through thin air)
                    \   `---'
                     \    |  <--- Zero-Distance Contact Seam (Must ground firmly!)
      ════════════════\═══╧════════════════════════════════════════════════
                       \  <--- Distant Cast Shadow on Ground Plane
                        \      (Screen-space raymarching tears at silhouette!)
```

### 1.2 The Five Geometric Information Classes
To prevent false claims of physical correctness, Spike 2 explicitly categorizes every pixel and data source into one of five geometric classes:
- **$\mathcal{G}_1$ — Observed Image Information:** Measured RGB radiant values, native edges, micro-texture gradients. (Immutable ground truth).
- **$\mathcal{G}_2$ — Estimated Depth ($Z$):** Relative distance from camera, subject to scale ambiguity and silhouette blur.
- **$\mathcal{G}_3$ — Estimated Surface Orientation ($\mathbf{n}$):** Local tangent planes, reliable on smooth continuous surfaces, noisy at fine boundaries.
- **$\mathcal{G}_4$ — Assumed Proxy Geometry ($\Pi$):** Planar ground or wall receiver estimated from silhouette contact points: $\Pi \equiv \{\mathbf{x} \in \mathbb{R}^3 : \mathbf{n}_{\pi} \cdot \mathbf{x} + d_{\pi} = 0\}$.
- **$\mathcal{G}_5$ — Unobserved / Ambiguous Geometry ($\mathcal{U}$):** The entire rear volume, underside cavities, and occluded support structures. Must be handled via explicit fallbacks, never hallucinated as physical ground truth.

---

## 2. MANDATORY ARCHITECTURAL SEPARATION: THE FOUR TRANSPORT COMPONENTS

Spike 2 strictly forbids collapsing shadows into an undifferentiated blur or heuristic multiply layer. The transport field $T(\mathbf{x}, \mathbf{L}) \in [0, 1]$ is decomposed into four independently inspectable and measurable physical components:

```
                      LIGHT TRANSPORT DECOMPOSITION
                                   │
      ┌────────────────────────────┼────────────────────────────┐
      ▼                            ▼                            ▼
[Component 1: T_ao]        [Component 2: T_contact]     [Component 3: T_self]
Cavity & Crevice Darkening  Local Contact Grounding      Directional Normal Shading
Omnidirectional, L-invariant Bounded Screen-Space March   n · L with Horizon Clip
      │                            │                            │
      └────────────────────────────┼────────────────────────────┘
                                   │
                                   ▼
                         [Component 4: T_cast]
                         Distant Receiver Cast Shadow
                         Analytical Proxy Plane Projection
                                   │
                                   ▼
                       [Composite Attenuation T]
                       T = T_ao · T_contact · T_self · T_cast
                                   │
                                   ▼
                       [Downstream Spike 1 Pipeline]
                       R_eff = (1 - M_high) · (T · R) + M_high
                       Reconstructed via Paradigm E.1 + Method C3
```

### 2.1 Component 1: Ambient Occlusion ($T_{\text{ao}}$) — Cavity and Crevice Darkening
- **Physical Meaning:** The fraction of the ambient hemisphere blocked by adjacent surfaces within a local radius $R_{\text{ao}}$. It is **omnidirectional** and invariant to the key light direction $\mathbf{L}$.
- **Formulation (Horizon-Based Ambient Occlusion / HBAO):**
  For a point $\mathbf{x}$ with normal $\mathbf{n}$, sample $N_{\text{dir}}$ radial directions $\theta_k$ in screen space. Along each direction, sample $N_{\text{step}}$ points $\mathbf{x}_i$ within radius $R_{\text{ao}}$:
  $$h_k = \max_{i} \left( \frac{Z(\mathbf{x}_i) - Z(\mathbf{x})}{\|\mathbf{x}_i - \mathbf{x}\|} \right)$$
  $$T_{\text{ao}}(\mathbf{x}) = 1.0 - \frac{1}{N_{\text{dir}}} \sum_{k=1}^{N_{\text{dir}}} \left[ \sin(h_k) - \sin(t_k) \right]^+ \cdot W(d)$$
  where $t_k$ is the tangent horizon angle and $W(d) = \max(0, 1 - d^2 / R_{\text{ao}}^2)$ is a distance attenuation weight.
- **Operating Constraints:** $R_{\text{ao}} \in [4, 16]\text{ px}$. Bounded strictly to micro-cavities (sole treads, nostrils, deep folds) to avoid large dark smudges.

### 2.2 Component 2: Contact Shadows ($T_{\text{contact}}$) — Local Object-to-Receiver Grounding
- **Physical Meaning:** High-contrast, sharp directional occlusion at zero-distance and near-distance contact interfaces ($0 \le d \le 25\text{ px}$) where the object touches the support surface.
- **Formulation (Bounded Screen-Space Depth Marching):**
  For a pixel $\mathbf{x}$, march $M_{\text{step}} = 16$ steps along the projected 2D light vector $\mathbf{L}_{2D} = (L_x, -L_y)$:
  $$\mathbf{x}_m = \mathbf{x} + m \cdot \Delta s \cdot \frac{\mathbf{L}_{2D}}{\|\mathbf{L}_{2D}\|}, \quad m \in \{1, \dots, M_{\text{step}}\}$$
  $$Z_{\text{ray}}(m) = Z(\mathbf{x}) + m \cdot \Delta s \cdot \tan(\theta_{\text{light}})$$
  Occlusion occurs when the depth buffer lies in front of the ray within a thickness tolerance $\Delta Z_{\text{thick}}$:
  $$\text{Occ}(m) = \mathbb{I}\left( 0 < Z_{\text{ray}}(m) - Z(\mathbf{x}_m) < \Delta Z_{\text{thick}} \right)$$
  $$T_{\text{contact}}(\mathbf{x}) = 1.0 - \kappa_{\text{contact}} \max_m \left[ \text{Occ}(m) \cdot \exp\left(-\frac{m \cdot \Delta s}{\sigma_{\text{contact}}}\right) \right]$$
- **Operating Constraints:** Maximum search distance is strictly capped at $R_{\text{contact}} = 25\text{ px}$. Bounding the search radius guarantees zero horizon ray leaks into distant background regions and keeps execution under $3\text{ ms}$.

### 2.3 Component 3: Directional Self-Shadowing ($T_{\text{self}}$) — Surface Orientation Attenuation
- **Physical Meaning:** Attenuation of direct illumination due to surface orientation relative to light vector $\mathbf{L}$, including diffuse cosine falloff and self-shadow horizon clipping.
- **Formulation (Cosine Law with Smooth Horizon Taper):**
  $$\cos\theta_i = \mathbf{n}(\mathbf{x}) \cdot \mathbf{L}$$
  $$T_{\text{self}}(\mathbf{x}, \mathbf{L}) = \text{smoothstep}\left(-\epsilon_{\text{horizon}}, +\epsilon_{\text{horizon}}, \cos\theta_i\right) \cdot \max(0, \cos\theta_i)$$
  where $\epsilon_{\text{horizon}} = 0.05$ softens the terminator transition to prevent quantized normal banding.

### 2.4 Component 4: Cast Shadows ($T_{\text{cast}}$) — Object-to-Receiver Proxy Projection
- **Physical Meaning:** Long-range shadow projected by the foreground object onto a receiver plane $\Pi$ (tabletop, studio floor, back wall) across large distances ($30 - 300\text{ px}$).
- **Why Screen-Space Raymarching Fails for Cast Shadows:**
  Screen-space raymarching cannot see through the object silhouette. A ray marching across the floor hits the "cliff edge" of the shoe's depth map and reports infinite occlusion, tearing the shadow into jagged fragments or detaching it entirely.
- **Formulation (Analytical Ground Proxy Projection):**
  1. **Receiver Plane Estimation ($\Pi$):**
     Detect lowest contact points of the segmented foreground silhouette to fit ground plane $\Pi: Z_{\text{floor}}(x, y) = A x + B y + C$.
  2. **Orthographic / Perspective Silhouette Splatting:**
     For each foreground silhouette pixel $\mathbf{x}_{\text{fg}} = (x, y, Z(x, y))$, project along light vector $\mathbf{L} = (L_x, L_y, L_z)$ onto plane $\Pi$:
     $$\mathbf{x}_{\text{proj}} = \mathbf{x}_{\text{fg}} + \frac{Z_{\text{floor}}(\mathbf{x}_{\text{fg}}) - Z(\mathbf{x}_{\text{fg}})}{L_z} \cdot (L_x, L_y)$$
  3. **Distance-Dependent Variable Penumbra:**
     The caster-to-receiver distance is $d_{\text{cast}} = \|\mathbf{x}_{\text{proj}} - \mathbf{x}_{\text{fg}}\|$.
     The shadow footprint is filtered with a Gaussian kernel whose standard deviation scales linearly with distance (simulating an area light of angular diameter $\alpha_{\text{light}}$):
     $$\sigma_{\text{penumbra}}(\mathbf{x}) = \sigma_{\text{min}} + \alpha_{\text{light}} \cdot d_{\text{cast}}(\mathbf{x})$$
     $$T_{\text{cast}}(\mathbf{x}) = 1.0 - \kappa_{\text{cast}} \cdot \left[ \text{Mask}_{\text{proj}} * \mathcal{N}(0, \sigma_{\text{penumbra}}^2) \right](\mathbf{x})$$

---

## 3. GEOMETRIC UNCERTAINTY & ROBUST FALLBACK ARCHITECTURE

A robust 2.5D renderer must not fail catastrophically when depth maps are noisy or incomplete.

```
                         GEOMETRIC UNCERTAINTY PIPELINE
                                       │
           ┌───────────────────────────┴───────────────────────────┐
           ▼                                                       ▼
[Depth Discontinuity Detector]                           [Receiver Confidence Mask]
|∇Z| > τ_cliff                                           Distance from silhouette base
           │                                                       │
           ▼                                                       ▼
Cliff Mask C_cliff                                       Receiver Mask W_receiver
           │                                                       │
           └───────────────────────────┬───────────────────────────┘
                                       │
                                       ▼
                       [Geometric Confidence Mask w_geom]
                       w_geom = (1 - C_cliff) · W_receiver
                                       │
                                       ▼
                       [Uncertainty-Weighted Fallback]
                       T_final = w_geom · T_separated + (1 - w_geom) · T_fallback
```

### 3.1 Depth Discontinuity Detection (Silhouette Cliff Mask)
At silhouette boundaries, estimated depth jumps discontinuously. Any raymarching across a cliff produces false occlusion.
- **Cliff Operator:**
  $$C_{\text{cliff}}(\mathbf{x}) = \mathbb{I}\left( \|\nabla Z(\mathbf{x})\| > \tau_{\text{cliff}} \right)$$
  where $\tau_{\text{cliff}} = 0.15 \cdot \text{range}(Z)$.
- **Fallback Action:** Screen-space raymarching ($T_{\text{contact}}$) is clamped to zero weight ($w_{\text{contact}} = 0$) wherever $C_{\text{cliff}} = 1$, instantly eliminating silhouette halo tears.

### 3.2 Unseen Geometry & Backside Fallback
When the virtual light vector points away from the camera ($L_z < 0$), shadows must theoretically be cast by the object's rear surface. Because the rear surface is completely unobserved ($\mathcal{G}_5$):
- **Extruded Volume Model:** The object is approximated as a solid extruded volume bounded by its 2D silhouette and front depth $Z(x, y)$, extended backward by an assumed thickness $D_{\text{assumed}} = \beta \cdot \text{width}(\text{silhouette})$.
- **Graceful Fallback:** If $L_z < -0.8$ (steep backlighting), cast shadows gracefully transition from extruded projection to an omnidirectional grounding shadow to prevent distorted razor-thin shadow silhouettes.

---

## 4. INTEGRATION CONTRACT WITH SPIKE 1

Spike 2 outputs an inspectable composite shadow attenuation field:
$$T(\mathbf{x}, \mathbf{L}) = T_{\text{ao}}(\mathbf{x}) \cdot T_{\text{contact}}(\mathbf{x}, \mathbf{L}) \cdot T_{\text{self}}(\mathbf{x}, \mathbf{L}) \cdot T_{\text{cast}}(\mathbf{x}, \mathbf{L})$$

### 4.1 Coupling with Shading Ratio $R$
The shadow attenuation field modulates the user's intended lighting ratio $R_{\text{user}}(\mathbf{x})$:
$$R_{\text{target}}(\mathbf{x}) = R_{\text{ambient}} + (R_{\text{user}}(\mathbf{x}) - R_{\text{ambient}}) \cdot T(\mathbf{x}, \mathbf{L})$$
where $R_{\text{ambient}} \in [0.05, 0.20]$ represents the ambient fill light floor, preventing pitch-black unnatural shadows.

### 4.2 Downstream Reconstruction via Paradigm E.1 + Method C3
1. **Highlight Protection:**
   $$M_{\text{high}} = \text{smoothstep}(0.75, 0.98, Y_{\text{orig}})$$
   $$R_{\text{eff}} = (1 - M_{\text{high}}) \cdot R_{\text{target}} + M_{\text{high}} \cdot 1.0$$
2. **Ratio Regularization (Paradigm E.1):**
   $$\rho_{\text{raw}} = \ln(R_{\text{eff}} \cdot Y_b + \epsilon_{\text{new}}) - \ln(Y_b + \epsilon_{\text{old}})$$
   $$\rho_{\text{bar}} = \text{GuidedFilter}(\text{guide}=I_{\text{sRGB}}, \text{src}=\rho_{\text{raw}}, r=16, \epsilon=10^{-3})$$
   $$Y_{\text{relit}} = \exp(B + \rho_{\text{bar}} + D)$$
3. **Color Reconstruction (Method C3):**
   Pass $Y_{\text{relit}}$ through Oklab 4-stage gamut mapping with radial cusp bisection to eliminate highlight clipping.

---

## 5. TEST DATASET MANIFEST

### 5.1 Procedural Synthetic Ground-Truth Scenes (Zero Geometric Uncertainty)
Synthetic targets generated analytically with exact geometry, ground-truth raytraced shadows, ground-truth depth, and ground-truth normals:
- **Scene S1 (Grounded Sphere on Floor):** Radius $R=128\text{ px}$, resting directly on planar floor ($h=0$). Evaluates contact grounding sharpness and penumbra falloff across 3 light angles:
  - Key A: Azimuth $45^\circ$, Elevation $30^\circ$ (long cast shadow).
  - Key B: Azimuth $90^\circ$, Elevation $60^\circ$ (medium grounding shadow).
  - Key C: Azimuth $0^\circ$, Elevation $85^\circ$ (tight contact ring under base).
- **Scene S2 (Calibrated Floating Sphere):** Same sphere placed at controlled elevations $h \in \{0, 5, 20, 50\}\text{ px}$ above ground plane. Evaluates shadow detachment gap ($SDG$) and contact transition from contact shadow to detached penumbra.
- **Scene S3 (Step Box on Floor):** Rectangular block with sharp 90° depth cliffs and planar floor. Evaluates silhouette leakage rate ($SLR$) and depth cliff edge tearing.

### 5.2 Real Photographic Test Cases
- **Case R1 (E-Commerce Sneaker on Studio Floor):**
  - Source: `demo_output/nike_sample.jpg` ($576 \times 1024$ px).
  - Maps: `demo_output/nike_test/depth.png` and `normals.png`.
  - Challenge: Deep sole tread cavities, zero-distance sole contact line, smooth studio floor.
- **Case R2 (Freestanding Classical Statue on Pedestal):**
  - Source: `media_1794143824741_478ce89a.jpg` ($576 \times 1024$ px).
  - Challenge: Complex drapery self-shadowing, marble surface normal raking, pedestal contact seam.
- **Case R3 (Person / Figure Against a Wall):**
  - Challenge: Vertical receiver plane (wall) behind subject, cast shadow projection across variable subject-to-wall distance, hair silhouette boundary.
- **Case R4 (Reflective / Glass Vessel or Watch):**
  - Challenge: Specular ground reflections vs diffuse cast shadow grounding.

---

## 6. QUANTITATIVE EVALUATION METRICS & ACCEPTANCE CRITERIA

| Metric ID | Metric Name | Mathematical Definition | Target Threshold | Physical Significance |
|:---:|:---|:---|:---:|:---|
| **M1** | **Contact Grounding Sharpness ($CGS$)** | $CGS = \min_{\mathbf{x} \in \text{ContactSeam}} T(\mathbf{x})$ | $\le 0.15$ | Object must firmly anchor to ground; no light leaks under shoe soles. |
| **M2** | **Shadow Detachment Gap ($SDG$)** | $SDG = \|\mathbf{x}_{\text{silhouette\_base}} - \mathbf{x}_{\text{shadow\_onset}}\|$ | $\le 1.0\text{ px}$ (for $h=0$) | Detects false "floating object" artifact when contact shadow fails. |
| **M3** | **Shadow Boundary Continuity ($SBC$)** | $SBC = 1.0 - \text{mean}(\|\nabla T_{\text{seam}}\|)$ | $\ge 0.90$ | Shadow must transition smoothly across object silhouette without tearing. |
| **M4** | **Silhouette Leakage Rate ($SLR$)** | $SLR = \frac{1}{N_{\text{bg}}} \sum_{\mathbf{x} \in \text{BgCliff}} \mathbb{I}(T(\mathbf{x}) < 0.85)$ | $\le 2.0\%$ | Background pixels immediately behind depth cliffs must not be falsely shadowed. |
| **M5** | **Shadow Displacement Error ($SDE$)** | $SDE = \|\text{Centroid}(T_{\text{est}}) - \text{Centroid}(T_{\text{gt}})\|$ | $\le 3.0\text{ px}$ (on Synthetic) | Verifies directional accuracy of shadow projection against ground truth. |
| **M6** | **Penumbra Softening Behavior ($PSF$)** | Slope $\frac{d W_{\text{penumbra}}}{d(d_{\text{cast}})}$ | $> 0$ (Monotonic rise) | Shadows must soften with distance from caster to receiver. |
| **M7** | **False Occlusion Rate ($FOR$)** | $FOR = \frac{1}{N_{\text{unshadowed}}} \sum \mathbb{I}(T(\mathbf{x}) < 0.90)$ | $\le 1.0\%$ | Clean surfaces facing the light must not be falsely darkened by depth noise. |
| **M8** | **Frametime Latency (1080p / 4K)** | Execution time of all 4 transport layers | $\le 10\text{ ms}$ (1080p), $\le 35\text{ ms}$ (4K) | Must remain interactive on workstation hardware. |
| **M9** | **Detail Preservation ($DCI_{\text{shadow}}$)** | Laplacian correlation under Spike 1 E.1 | $\ge 0.980$ | Cast shadows must not wipe out underlying photographic surface textures. |

---

## 7. EXECUTION PLAN FOR SPIKE 2

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SPIKE 2 EXECUTION SEQUENCE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Spec Approval & User Alignment (Current Turn)                            │
│ 2. Procedural Synthetic Ground-Truth Engine (Raytraced S1, S2, S3)          │
│ 3. Independent 4-Component Implementation (spike_shadow_transport.py)       │
│ 4. Full Benchmark Execution (Synthetic + Photographic Cases R1, R2, R3, R4) │
│ 5. Metric Extraction & Contact Sheet Generation                             │
│ 6. Comprehensive Evaluation Report v1.0 (spike2_output/)                    │
│ 7. Phase Gate Review & Go/No-Go Recommendation                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---
*Specification compiled by Principal Computational Photography Architect & Rendering Engineer.*  
*Ready for user review and implementation authorization.*
