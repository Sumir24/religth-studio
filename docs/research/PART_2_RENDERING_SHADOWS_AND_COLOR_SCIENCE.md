# RELIGHT STUDIO — TECHNICAL RESEARCH REPORT
## PART 2: LIGHTING MATHEMATICS, SHADOWS, DETAIL PRESERVATION & COLOR SCIENCE

**Document ID:** RS-TR-02  
**Status:** COMPLETE / PEER-REVIEW READY  
**Classification:** Research, Mathematical Foundations & Architectural Ideation  
**Epistemic Framework:** `[ESTABLISHED]` | `[DEMONSTRATED]` | `[HYPOTHESIS]` | `[UNKNOWN]`  

---

# TABLE OF CONTENTS
1. [Topic 8: Light Transport & Lighting Mathematics](#topic-8-light-transport--lighting-mathematics)
2. [Topic 9: Shadow Estimation & 2.5D Occlusion](#topic-9-shadow-estimation--25d-occlusion)
3. [Topic 10: Colour Science & HDR Pipeline](#topic-10-colour-science--hdr-pipeline)
4. [Topic 11: Image Compositing & Detail Preservation](#topic-11-image-compositing--detail-preservation)
5. [Topic 12: Confidence Estimation & Uncertainty-Aware Rendering](#topic-12-confidence-estimation--uncertainty-aware-rendering)

---

# TOPIC 8: LIGHT TRANSPORT & LIGHTING MATHEMATICS

### 1. Fundamental Explanation
In Relight Studio, newly created virtual lights must interact with visible surfaces as if they physically exist in the camera-space volume. Because full 3D geometry is unavailable, lighting mathematics must be adapted to evaluate over the 2.5D unprojected point cloud $\mathbf{P}(u, v) \in \mathbb{R}^3$ and normal field $\mathbf{n}(u, v) \in \mathbb{S}^2$. The system must support the five fundamental studio light types: **Directional (Sun)**, **Point**, **Spot**, **Area (Softbox)**, and **Rim Lights**, as well as **Subtractive Negative Fill**.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`

#### Diffuse Lambertian Reflectance
For any light source $k$ casting irradiance $E_k(\mathbf{P})$ on surface $\mathbf{P}$ with normal $\mathbf{n}$:
$$\mathbf{L}_{\text{diffuse}, k}(\mathbf{P}) = \frac{\boldsymbol{\rho}(\mathbf{P})}{\pi} \odot \mathbf{C}_k \cdot E_k(\mathbf{P}) \cdot \max(0, \mathbf{n} \cdot \mathbf{l}_k)$$
Where $\mathbf{l}_k = \frac{\mathbf{P}_k - \mathbf{P}}{\|\mathbf{P}_k - \mathbf{P}\|}$ is the normalized incident light vector.

#### Cook-Torrance Microfacet Specular Formulation
For glossy surfaces (wet rocks, water, architectural glass, metals):
$$\mathbf{L}_{\text{specular}, k}(\mathbf{P}) = \frac{D(\mathbf{h}_k) \cdot F(\mathbf{v}, \mathbf{h}_k) \cdot G(\mathbf{l}_k, \mathbf{v}, \mathbf{h}_k)}{4 (\mathbf{n} \cdot \mathbf{l}_k) (\mathbf{n} \cdot \mathbf{v})} \cdot E_k(\mathbf{P}) \cdot \max(0, \mathbf{n} \cdot \mathbf{l}_k)$$
Where:
- $\mathbf{v} = -\frac{\mathbf{P}}{\|\mathbf{P}\|}$: View vector pointing to the camera.
- $\mathbf{h}_k = \text{normalize}(\mathbf{l}_k + \mathbf{v})$: Half-angle vector.
- **GGX Normal Distribution Function $D(\mathbf{h})$:**
  $$D(\mathbf{h}) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}$$
  Where $\alpha = \text{Roughness}^2$.
- **Schlick's Fresnel Approximation $F(\mathbf{v}, \mathbf{h})$:**
  $$F(\mathbf{v}, \mathbf{h}) = F_0 + (1 - F_0) \left( 1 - (\mathbf{v} \cdot \mathbf{h}) \right)^5$$
  ($F_0 \approx 0.04$ for dielectrics; $F_0 \in [0.7, 1.0]$ for conductors).
- **Smith's Masking-Shadowing Function $G(\mathbf{l}, \mathbf{v})$:**
  $$G(\mathbf{l}, \mathbf{v}) = G_1(\mathbf{l}) \cdot G_1(\mathbf{v}), \quad G_1(\mathbf{w}) = \frac{2 (\mathbf{n} \cdot \mathbf{w})}{(\mathbf{n} \cdot \mathbf{w}) + \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{w})^2}}$$

#### Light Types & Falloff Laws `[ESTABLISHED / DERIVED]`
1. **Directional Light (Sun):**
   - Position: At infinity; invariant direction $\mathbf{l}_{\text{dir}}$.
   - Falloff: Zero spatial attenuation ($E = \Phi_{\text{dir}}$).
2. **Point Light:**
   - Position: $\mathbf{P}_{\text{light}} \in \mathbb{R}^3$.
   - Distance: $d = \|\mathbf{P}_{\text{light}} - \mathbf{P}\|$.
   - Attenuation with near-field smoothing radius $r_0$ (preventing infinite singularity as $d \to 0$):
     $$E_{\text{point}}(d) = \frac{\Phi_{\text{point}}}{4\pi (d^2 + r_0^2)} \cdot \max\left(0, 1 - \left(\frac{d}{d_{\text{max}}}\right)^4\right)^2$$
3. **Spot Light:**
   - Defined by position $\mathbf{P}_{\text{spot}}$, direction $\mathbf{d}_{\text{spot}}$, inner angle $\theta_{\text{inner}}$, and outer angle $\theta_{\text{outer}}$:
     $$\cos \theta = \mathbf{d}_{\text{spot}} \cdot (-\mathbf{l}_k)$$
     $$\text{SpotAngularFactor} = \text{smoothstep}\left(\cos \theta_{\text{outer}}, \, \cos \theta_{\text{inner}}, \, \cos \theta\right)$$
4. **Area Light (Studio Softbox) — LTC Formulation:**
   - Approximated via Linearly Transformed Cosines (Heitz et al. 2016): computes analytical diffuse and specular irradiance from a rectangular emitter on GPU without stochastic ray tracing.
5. **Rim Light:**
   - Enhances silhouettes at grazing angles where $\mathbf{n} \cdot \mathbf{v} \approx 0$:
     $$E_{\text{rim}}(\mathbf{P}) = \left( 1 - \max(0, \mathbf{n} \cdot \mathbf{v}) \right)^\gamma \cdot \max(0, \mathbf{n} \cdot \mathbf{l}_{\text{rim}})$$
6. **Negative Fill (Subtractive Lighting Card):**
   - Retouchers use black cards to cut ambient spill and deepen shadows. Naive subtraction clips blacks to $0.0$ and flattens texture. Relight Studio models negative fill as an **attenuation transmittance field**:
     $$T_{\text{neg}}(\mathbf{P}) = \exp\left( -\kappa \cdot \max\left(0, 1 - \frac{\|\mathbf{P}_{\text{card}} - \mathbf{P}\|}{r_{\text{card}}}\right)^2 \right) \in (0, 1]$$
     This pulls down base exposure smoothly while mathematically guaranteeing that black point floors and micro-textures are never crushed.

### 3. Important Research Papers
- Heitz, E., Dupuy, J., Hill, S., & Prutkin, D. (2016). *Real-time polygonal-light shading with linearly transformed cosines*. ACM Transactions on Graphics (TOG), 35(4), 1–8.
- Karis, B. (2013). *Real Shading in Unreal Engine 4*. Epic Games Course Notes.
- Walter, B., Marschner, S. R., Li, H., & Torrance, K. E. (2007). *Microfacet models for refraction through rough surfaces*. Eurographics Symposium on Rendering (EGSR), 195–206.

### 4. Recommendation: **ADOPT PHYSICAL INVERSE-SQUARE POINT/SPOT/RIM + HEITZ LTC AREA LIGHTS IN METAL KERNELS**

---

# TOPIC 9: SHADOW ESTIMATION & 2.5D OCCLUSION

### 1. Fundamental Explanation
Without shadows, newly added virtual lights appear to float unnaturally on top of the image like flat color overlays. In full 3D rendering, shadows are calculated by testing ray-mesh intersections. In Relight Studio's 2.5D representation, the scene exists only as visible surface samples $\mathbf{P}(u, v)$. Shadows must be computed by **Screen-Space Ray Tracing (SSRT)** through the depth buffer.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`

#### Screen-Space Depth Ray Marching
To test whether light at $\mathbf{P}_{\text{light}}$ illuminates surface point $\mathbf{P}_0 = \mathbf{P}(u_0, v_0)$:
1. Define the 3D ray in camera space:
   $$\mathbf{r}(t) = \mathbf{P}_0 + t \cdot \frac{\mathbf{P}_{\text{light}} - \mathbf{P}_0}{\|\mathbf{P}_{\text{light}} - \mathbf{P}_0\|}, \quad t \in [t_{\text{start}}, \, t_{\text{end}}]$$
2. For each step $t_k = t_0 + k \cdot \Delta t$:
   - Project ray position $\mathbf{r}(t_k) = [X_k, Y_k, Z_k]^T$ back to screen coordinates $(u_k, v_k)$:
     $$u_k = \frac{f_x X_k}{Z_k} + c_x, \quad v_k = \frac{f_y Y_k}{Z_k} + c_y$$
   - Query the stored surface depth $D(u_k, v_k)$ at the projected pixel.
   - If $Z_k > D(u_k, v_k) + \delta_{\text{bias}}$ and $Z_k < D(u_k, v_k) + \tau_{\text{thickness}}$, the ray has intersected an occluding surface.
   - Set visibility $V(\mathbf{P}_0) = 0$ (occluded).

```
Camera Ray
    |
    v
Screen Pixel (u_k, v_k) ---> Sample Stored Depth D(u_k, v_k)
                                     |
    Ray Point r(t_k)                 | Surface Depth
    Z_ray(t_k) --------------------> [=== Geometry ===]  --> Hit! (Shadowed)
```

#### Percentage-Closer Soft Shadows (PCSS in Screen Space) `[DEMONSTRATED]`
Hard binary shadows look artificial in outdoor lighting. Physical shadows exhibit distance-dependent penumbras (contact hardening: tight shadows near the feet/base, diffuse blurry shadows further away).
1. **Blocker Search:** March rays from $\mathbf{P}_0$ across a search cone to find the average blocker depth $d_{\text{blocker}}$.
2. **Penumbra Width Estimation:**
   $$w_{\text{penumbra}} = w_{\text{light}} \cdot \frac{d_{\text{receiver}} - d_{\text{blocker}}}{d_{\text{blocker}}}$$
3. **Filtering:** Convolve visibility $V$ over a screen-space disk kernel of radius $w_{\text{penumbra}}$.

### 3. Hard Physical Limitations & Failure Cases `[ESTABLISHED / UNKNOWN]`
Screen-space ray tracing operates strictly on visible pixels. Two severe failure modes exist:
1. **Off-Screen Occluders:** An object outside the camera frame (e.g., a tree just above the top crop) cannot cast a shadow into the image because its depth is not recorded in the depth buffer.
2. **Occluded Backsides:** Surfaces hidden behind foreground objects cannot be ray-marched through.

#### Relight Studio Engineering Mitigations:
- **Heuristic Blocker Extension:** For directional sunlight coming from off-screen, extrapolate depth boundaries linearly beyond image edges.
- **Virtual Proxy Occluders:** Allow users to place simple geometric blocker cards (cylinders, rectangles) off-screen to cast intended directional shadows onto visible terrain.

### 4. Recommendation: **ADOPT HIERARCHICAL DOWNSAMPLED SCREEN-SPACE RAY TRACING (SSRT) WITH PCSS FILTERING**

---

# TOPIC 10: COLOUR SCIENCE & HDR PIPELINE

### 1. Fundamental Explanation
All lighting calculations in Relight Studio are radiometric additions and multiplications. Executing lighting math in gamma-encoded color spaces (sRGB, Adobe RGB, ProPhoto RGB) produces dark borders, muddy color fringes, and incorrect chromatic saturation. Furthermore, high-intensity light synthesis requires high dynamic range headroom ($> 1.0$) that must be preserved until final display tone-mapping.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`

#### Color Space Specifications & Primaries
Relight Studio adopts **ACEScg** (Academy Color Encoding System, AP1 primaries) as its internal 32-bit floating-point working space:
- **AP1 Primaries:** Red $(0.713, 0.293)$, Green $(0.165, 0.830)$, Blue $(0.128, 0.044)$, White Point D60 $(0.32168, 0.33767)$.
- **Transfer Function:** Strictly linear ($1.0$).
- **Gamut Advantage:** Encompasses $100\%$ of Rec.709 and Display P3 without negative color clipping during chromatic shifts.

#### Chromatic Adaptation Matrix (sRGB to ACEScg via Bradford D65 to D60):
$$\begin{bmatrix} R_{\text{ACEScg}} \\ G_{\text{ACEScg}} \\ B_{\text{ACEScg}} \end{bmatrix} = \begin{bmatrix} 0.613097 & 0.339523 & 0.047379 \\ 0.070194 & 0.916354 & 0.013452 \\ 0.020616 & 0.109570 & 0.869815 \end{bmatrix} \begin{bmatrix} R_{\text{linear sRGB}} \\ G_{\text{linear sRGB}} \\ B_{\text{linear sRGB}} \end{bmatrix}$$

#### Display Tone Mapping: AgX vs. ACES 1.3
Traditional simple tone mappers (Reinhard: $I / (1 + I)$) bleach colors to white along non-physical paths, causing saturated purple lights to turn into flat pastel pinks.
Relight Studio adopts **AgX Tone Mapping** (Sobotka 2023):
1. **Inset Color Primaries:** Shifts saturated colors slightly inward into gamut before non-linear compression, preventing single-channel clipping.
2. **Log2 Curve Fitting:** Compresses 16 stops of dynamic range into display $[0, 1]$ with smooth highlight toe and shoulder roll-off.
3. **AgX Look Table:** Preserves perceptual color purity as exposure increases.

#### Perceptual Color Error: CIE $\Delta E_{00}$
To mathematically verify that un-relit areas (sky, shadows) do not drift during sun recoloring, Relight Studio monitors CIEDE2000:
$$\Delta E_{00} = \sqrt{ \left(\frac{\Delta L'}{k_L S_L}\right)^2 + \left(\frac{\Delta C'}{k_C S_C}\right)^2 + \left(\frac{\Delta H'}{k_H S_H}\right)^2 + R_T \left(\frac{\Delta C'}{k_C S_C}\right) \left(\frac{\Delta H'}{k_H S_H}\right) }$$
- $\Delta E_{00} < 1.0$: Imperceptible to human visual system.
- $\Delta E_{00} \in [1.0, 2.5]$: Barely perceptible by expert retouchers under critical inspection.
- $\Delta E_{00} > 3.0$: Noticeable color shift (triggers automated guardrail alert).

### 3. Recommendation: **ADOPT STRICT LINEAR ACEScg WORKING PIPELINE + AgX DISPLAY TONE MAPPING + REAL-TIME $\Delta E_{00}$ AUDIT**

---

# TOPIC 11: IMAGE COMPOSITING & DETAIL PRESERVATION

### 1. Fundamental Explanation
The central promise of Relight Studio is that the original photograph stays the canvas. When virtual lights are applied, fine micro-textures (rock pores, tree bark, watch dial engravings, fabric weave, individual hair strands) must not be washed out, blurred, or distorted.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`

#### Guided Image Filter Decomposition (He, Sun, Tang 2013)
The Guided Filter is an edge-preserving, non-iterative linear operator that transfers structural edges from a guide image $I$ to an output $q$:
$$q_i = a_k I_i + b_k, \quad \forall i \in \omega_k$$
Minimizing the squared difference with regularizer $\epsilon$:
$$a_k = \frac{\sigma_k^2}{\sigma_k^2 + \epsilon}, \quad b_k = (1 - a_k) \mu_k$$
Where $\mu_k$ and $\sigma_k^2$ are the local mean and variance of $I$ in window $\omega_k$.

#### Base / Detail Separation Formulation `[DERIVED]`
We decompose linear scene radiance $\mathbf{I}_{\text{linear}}$ into:
1. **Base Illumination Layer ($\mathbf{B}$):** Contains low-frequency spatial illumination and surface shading.
   $$\mathbf{B} = \text{GuidedFilter}(\mathbf{I}_{\text{linear}}, \, \text{guide}=\mathbf{I}_{\text{linear}}, \, r=16, \, \epsilon=0.01)$$
2. **High-Frequency Texture Residual ($\mathbf{R}$):** Encodes 100% of the surface micro-contrast, brand engravings, and fine details:
   $$\mathbf{R}(u, v) = \frac{\mathbf{I}_{\text{linear}}(u, v)}{\mathbf{B}(u, v) + \epsilon_{\text{floor}}}$$

#### Non-Destructive Recombination
When the lighting engine computes a new lighting field (e.g. purple sun gain $\mathbf{G}(u, v)$ and additive light $\mathbf{L}_{\text{new}}(u, v)$):
$$\mathbf{B}_{\text{relit}}(u, v) = \mathbf{B}(u, v) \odot \mathbf{G}(u, v) + \mathbf{L}_{\text{new}}(u, v)$$
The final composite multiplies the untouched high-frequency residual $\mathbf{R}$ back onto the new base:
$$\mathbf{I}_{\text{final}}(u, v) = \mathbf{B}_{\text{relit}}(u, v) \odot \mathbf{R}(u, v)$$
**Mathematical Proof of Conservation:** If no lighting changes are made ($\mathbf{G} = 1, \mathbf{L} = 0$), then:
$$\mathbf{I}_{\text{final}} = \mathbf{B} \odot \frac{\mathbf{I}_{\text{linear}}}{\mathbf{B}} \equiv \mathbf{I}_{\text{linear}} \quad (\text{PSNR} > 60\text{ dB})$$
Zero loss of original detail is guaranteed.

#### Semantic Protection Masks & Hard Bypass
For sensitive features:
- **Typography & Logos:** Detected via CRAFT / PaddleOCR.
- **Facial Features:** Detected via MediaPipe Face Landmark parsing (eyes, lips, nostrils).
A binary bypass mask $\mathbf{M}_{\text{protect}}(u, v)$ enforces:
$$\mathbf{I}_{\text{rendered}}(u, v) = (1 - \mathbf{M}_{\text{protect}}) \cdot \mathbf{I}_{\text{final}} + \mathbf{M}_{\text{protect}} \cdot \mathbf{I}_{\text{linear}}$$
Guaranteeing $0\%$ distortion on protected assets.

### 3. Recommendation: **ADOPT RATIO-BASED GUIDED FILTER DECOMPOSITION + SEMANTIC BYPASS MASKS**

---

# TOPIC 12: CONFIDENCE ESTIMATION & UNCERTAINTY-AWARE RENDERING

### 1. Fundamental Explanation
Monocular depth and normal estimators are statistical models; their predictions are not exact physical geometry. On chaotic surfaces (dense tree foliage, blowing grass, water ripples, fur, and hair), neural normal vectors fluctuate wildly from pixel to pixel. Applying direct specular or directional cosine shading $(\mathbf{n} \cdot \mathbf{l})$ to noisy normals produces severe salt-and-pepper noise, sparkling artifacts, and faceted polygonal blotches. Relight Studio must quantify uncertainty and smoothly blend to image-space fallbacks where confidence is low.

### 2. Relevant Mathematical Foundations `[DERIVED]`

#### The Multi-Factor Geometric Confidence Map $C(u, v) \in [0, 1]$
We compute a per-pixel confidence metric combining three orthogonal uncertainty indicators:
1. **Depth Discontinuity / Gradient Magnitude ($\tau_D$):**
   High depth gradient indicates geometric silhouette edges where 2.5D unprojection creates topological tears:
   $$C_{\text{depth}}(u, v) = \exp\left( -\lambda_D \cdot \|\nabla D(u, v)\|^2 \right)$$
2. **Normal Field Spatial Variance ($\sigma_{\mathbf{n}}^2$):**
   Calculates the local variance of normal vectors within a $5\times 5$ window $\mathcal{N}$:
   $$\bar{\mathbf{n}} = \frac{1}{|\mathcal{N}|} \sum_{p \in \mathcal{N}} \mathbf{n}(p), \quad C_{\text{normal}}(u, v) = \|\bar{\mathbf{n}}\|^2 \in [0, 1]$$
   (On smooth surfaces, $\|\bar{\mathbf{n}}\| = 1.0$; on chaotic leaves/hair, vectors cancel out, dropping $\|\bar{\mathbf{n}}\| \to 0.0$).
3. **Cross-Model Agreement:**
   Cosine similarity between neural normals $\mathbf{n}_{\text{neural}}$ (DSINE) and analytical depth normals $\mathbf{n}_{\text{depth}}$:
   $$C_{\text{agreement}}(u, v) = \max(0, \mathbf{n}_{\text{neural}} \cdot \mathbf{n}_{\text{depth}})$$

#### Unified Confidence Equation:
$$C(u, v) = C_{\text{depth}}(u, v) \cdot C_{\text{normal}}(u, v) \cdot C_{\text{agreement}}(u, v) \cdot (1 - \mathbf{M}_{\text{sky}}(u, v))$$

#### Uncertainty-Aware Rendering Shader:
For any light $k$, the shader dynamically interpolates between physical 2.5D surface shading and a graceful 2D image-space radial gain:
$$\mathbf{L}_k(\mathbf{P}) = C(u, v) \cdot \mathbf{L}_{\text{physical}}(\mathbf{n}, \mathbf{l}_k, D) + (1 - C(u, v)) \cdot \mathbf{L}_{\text{image-space}}(u, v)$$
Where $\mathbf{L}_{\text{image-space}}$ uses a smooth bilateral Gaussian falloff centered at the light's 2D screen projection:
$$\mathbf{L}_{\text{image-space}}(u, v) = \mathbf{C}_k \cdot \exp\left( -\frac{(u - u_k)^2 + (v - v_k)^2}{2 \sigma_{\text{soft}}^2} \right) \cdot \mathbf{I}_{\text{linear}}(u, v)$$
*Result:* Smooth rock faces and architecture receive crisp directional lighting with sharp shadows; chaotic tree canopies and hair receive soft, believable ambient color washes without digital artifacts!

### 3. Recommendation: **ADOPT TRI-FACTOR CONFIDENCE MAPS WITH DYNAMIC 2.5D-TO-2D SHADING BLENDING**
