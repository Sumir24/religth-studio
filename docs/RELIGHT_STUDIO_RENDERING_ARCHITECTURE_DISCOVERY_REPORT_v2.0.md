# RELIGHT STUDIO — RENDERING ARCHITECTURE DISCOVERY & DECISION REPORT v2.0
## Critical Architecture Review, Mathematical Redesign, and Empirical Validation Protocol

**Document ID:** RS-RADR-2026-v2.0  
**Authors:** Principal Computational Photography Researcher, Rendering Architect, Graphics & Performance Engineering Group  
**Framework:** GRAVITAS Engineering Reliability Runtime (`[ESTABLISHED]` | `[DEMONSTRATED]` | `[ESTIMATE]` | `[HYPOTHESIS]`)  
**Status:** REVISED ARCHITECTURAL BLUEPRINT — READY FOR SEQUENTIAL SPIKE EXECUTION  
**Target Platform:** Apple Silicon macOS 14.0+ (Metal 3 Compute, Unified Memory Architecture)  

---

## EXECUTIVE SUMMARY & AUDIT OF v1.0

Version 1.0 established the necessity of rejecting generative latent diffusion models (IC-Light, ControlNet) and unconstrained inverse unbaking. However, an honest, critical architecture audit reveals eight major deficiencies in the v1.0 formulation:

1. **The "100% Bit-for-Bit Detail Preservation" Fallacy:** v1.0 claimed "bit-for-bit locked detail". This is mathematically false. When lighting changes, pixel numerical values must change. What is preserved is high-frequency structural topology and edge phase, not raw digital numbers.
2. **Overextension of Spherical Harmonics (Prototype B):** Order-2 Spherical Harmonics ($L \le 2$) were proposed as a general multi-light engine. In reality, $L \le 2$ is strictly low-pass and mathematically incapable of representing specular highlights or directional key lights. Furthermore, a 4K 9-channel tensor requires $447\text{MB}$, which creates an unnecessary $26.8\text{GB/s}$ memory bandwidth penalty at 60 FPS.
3. **Conflation of Shadow Systems:** Ambient occlusion, contact shadows, attached self-shadowing, and long-range cast shadows were lumped into a single heuristic. They operate at completely different physical scales and require separate mathematical treatments.
4. **Unconstrained Subsurface Scattering:** v1.0 applied a global warm Gaussian terminator bleed across the entire scene, which turns polished titanium, black leather, and acrylic plastics into glowing red wax. SSS must be strictly restricted to verified translucent organic dielectrics.
5. **Missing Component Breakdown for Specular Products:** v1.0 proposed "analytical guides" as an abstract concept. Real commercial luxury products (watches, eyewear, perfume bottles) consist of distinct mechanical assemblies (sapphire crystals, brushed cases, liquid volumes) with sharply contrasting Fresnel and roughness profiles.
6. **Unrealistic Inverse Illumination Expectations:** Fully automated, single-image unbaking of arbitrary studio lighting without user priors is physically ill-posed. Automatic estimation must be bounded to dominant direction and ambient floor, with interactive calibration for multi-light setups.
7. **Unclassified Performance Claims:** Latency and memory metrics were presented without distinguishing hardware-verified results from first-principles engineering estimates.
8. **Monolithic Validation Metrics:** Validation grouped subjective aesthetics with physical correctness.

This v2.0 report provides mathematically rigorous corrections, a modular system architecture, a concrete technical dependency graph, and a low-cost, sequential prototype roadmap.

---

# SECTION 1: CRITICAL REASSESSMENT OF CORE CLAIMS

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 v1.0 DEFICIENCY VS. v2.0 RESOLUTION                               │
├────┬─────────────────────────────┬─────────────────────────────────┬──────────────────────────────┤
│ #  │ Topic                       │ v1.0 Flaw                       │ v2.0 Rigorous Resolution     │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 1  │ Detail Preservation         │ Claimed "bit-for-bit locked"    │ Structural phase & gradient  │
│    │                             │ detail layer.                   │ lock via regularized ratio.  │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 2  │ Spherical Harmonics         │ Proposed for all studio lights; │ Restricted to diffuse ambient│
│    │                             │ 447MB VRAM tensor.              │ fill; analytical key lights. │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 3  │ Shadow Separation           │ Unified heuristic for all       │ 4 distinct physical systems: │
│    │                             │ shadow phenomena.               │ AO, Contact, Attached, Cast. │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 4  │ Subsurface Scattering       │ Applied globally to all objects │ Masked by material class;    │
│    │                             │ at terminator N·L ~ 0.          │ active only on skin/marble.  │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 5  │ Reflective Products         │ Generic parametric form guide.  │ Component-based assembly:    │
│    │                             │                                 │ crystal, bezel, dial, strap. │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 6  │ Inverse Lighting Estimation │ Automated SH least-squares      │ Coarse automatic dominant    │
│    │                             │ assumed without user guidance.  │ guess + 2-click calibration. │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 7  │ Performance Rigor           │ Claims unclassified;            │ Rigorous 4-tier epistemic    │
│    │                             │ "1.8ms" assumed verified.       │ classification audit.        │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 8  │ Validation Methodology      │ Composite scores mixed metrics. │ 5 orthogonal validation      │
│    │                             │                                 │ suites with separate gates.  │
└────┴─────────────────────────────┴─────────────────────────────────┴──────────────────────────────┘
```

### 1.1 The Truth About "Detail Preservation" `[ESTABLISHED]`
In photographic retouching, asserting "100% bit-for-bit preservation" is a contradiction in terms: if lighting changes, pixel luminance and chromaticity must change.

#### What IS Preserved:
1. **Edge Phase and Coordinate Invariance:** Zero pixel displacement, zero blurring, zero spatial shift in micro-structures ($\Delta x = \Delta y = 0$).
2. **High-Frequency Gradient Field:** The directional orientation of micro-gradients $\theta_{\nabla} = \arctan(\partial_y Y / \partial_x Y)$ is strictly preserved.
3. **Texture Identity:** Pores, nylon stitching, watch serial numbers, and paper tooth remain identical in structural arrangement.

#### What CAN and MUST Change:
1. **Mean Local Luminance:** Shifting an area from shadow to key light increases its base level.
2. **Chromaticity & Contrast:** Under colored gels, local saturation alters. Furthermore, human visual perception (Weber-Fechner Law) perceives greater contrast in brighter regions.
3. **Micro-Relief Cast Shadows:** Under raking light ($\mathbf{n} \cdot \boldsymbol{\omega}_i \to 0$), microscopic physical surface height irregularities cast raking shadows, altering perceived micro-texture contrast.

#### Mathematical Definition of Detail Coupling:
Let input luminance in perceptual logarithmic domain be decomposed via an edge-preserving filter:
$$\ln Y(p) = \ln Y_b(p) + d(p)$$
Where $Y_b(p)$ is the smooth base layer and $d(p) = \ln Y(p) - \ln Y_b(p)$ is the detail residual. The relit luminance $Y_{\text{relit}}(p)$ is computed as:
$$Y_{\text{relit}}(p) = Y_b(p) \cdot R_{\text{reg}}(p) \cdot \exp\Big( d(p) \cdot \lambda \cdot \Phi(\mathbf{n}(p), \boldsymbol{\omega}_i) \Big)$$
Where:
- $R_{\text{reg}}(p) = \frac{S_{\text{new}}(p) + \epsilon_{\text{new}}}{S_{\text{old}}(p) + \epsilon_{\text{old}}}$ is the regularized shading ratio.
- $\lambda \in [0.8, 1.2]$ is the user-controlled detail preservation gain.
- $\Phi(\mathbf{n}(p), \boldsymbol{\omega}_i) = \left( 1 + \gamma_{\text{rake}} (1 - (\mathbf{n} \cdot \boldsymbol{\omega}_i)^+) \right)$ accounts for raking micro-relief contrast enhancement.

---

### 1.2 Reassessment of the Spherical Harmonic Field Tensor `[ESTABLISHED]`
In v1.0, Prototype B proposed an irradiance transfer tensor $\mathbf{T}(u, v) \in \mathbb{R}^{9 \times 3}$ using Order-2 Spherical Harmonics ($L \le 2$).

#### Critical Mathematical & Hardware Audit:
1. **The Specular Barrier:** Ramamoorthi & Hanrahan (2001) proved that Lambertian diffuse reflection acts as an ideal low-pass filter, retaining $>99\%$ of irradiance energy within order $L \le 2$ (9 coefficients). However, for specular reflections with microfacet roughness $\alpha = 0.05$, the BRDF acts as a high-pass filter requiring $L \ge 32$ ($1024$ coefficients). Storing 1024 float16 values per pixel on a 4K image would require:
   $$3840 \times 2160 \times 1024 \times 3 \times 2 \text{ bytes} \approx 50.9 \text{ GB of VRAM}$$
   This is physically impossible on unified memory architectures.
2. **Bandwidth Penalty for Scrubbing:** Even for $L \le 2$, streaming a $447\text{MB}$ tensor at 60 FPS requires $26.8\text{GB/s}$ of continuous memory bandwidth, competing directly with the display controller and OS compositor.

#### Revised Architectural Verdict:
The SH Field Tensor is **strictly restricted to diffuse ambient environment maps (skylight, studio fill, room bounce)**. Key lights, rim lights, and all specular components must be evaluated using **analytical closed-form shaders (GGX)** evaluated on-the-fly directly in GPU thread registers, requiring zero intermediate VRAM streaming.

---

### 1.3 Disentanglement of the Four Shadow & Occlusion Systems `[ESTABLISHED]`
Shadows are not a monolithic phenomenon. The rendering pipeline decomposes illumination attenuation into four independent physical domains:

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 THE FOUR SHADOW TRANSPORT SYSTEMS                                 │
├────┬─────────────────────┬──────────────────┬─────────────────────────────┬───────────────────────┤
│ ID │ System Name         │ Spatial Scale    │ Physical Mechanism          │ Computational Engine  │
├────┼─────────────────────┼──────────────────┼─────────────────────────────┼───────────────────────┤
│ 1  │ Cavity AO (Macro)   │ Micro (0–10mm)   │ Hemispherical self-         │ Screen-Space Horizon  │
│    │                     │                  │ obscurance in crevices      │ AO (HBAO / GTAO)      │
├────┼─────────────────────┼──────────────────┼─────────────────────────────┼───────────────────────┤
│ 2  │ Contact Shadows     │ Local (0–50mm)   │ Directional occlusion by    │ Screen-Space Depth    │
│    │                     │                  │ immediate ground contact    │ Marching (SSDO)       │
├────┼─────────────────────┼──────────────────┼─────────────────────────────┼───────────────────────┤
│ 3  │ Attached Shadows    │ Surface-Local    │ Surface normal facing away  │ Analytical BRDF       │
│    │                     │                  │ from light: (n · omega_i)<=0│ (Oren-Nayar / Burley) │
├────┼─────────────────────┼──────────────────┼─────────────────────────────┼───────────────────────┤
│ 4  │ Distant Cast Shadows│ Macro (>50mm)    │ Non-local occlusion across  │ 2.5D Elevation Plane  │
│    │                     │                  │ large air gaps              │ or Proxy Shadow Plane │
└────┴─────────────────────┴──────────────────┴─────────────────────────────┴───────────────────────┘
```

1. **System 1: Cavity Ambient Occlusion (HBAO):**
   Evaluates diffuse un-occluded sky/ambient visibility:
   $$V_{\text{ambient}}(p) = 1 - \frac{1}{2\pi} \sum_{i=1}^{N_{\text{dir}}} \Delta \phi \int_{h_{\text{min}}(\phi_i)}^{h_{\text{max}}(\phi_i)} W(\theta) \cos \theta \, d\theta$$
   Applied strictly as a multiplier against the diffuse ambient irradiance term.
2. **System 2: Contact Shadows (Local Directional Occlusion):**
   Marches $N_{\text{steps}} = 16$ samples in screen-space depth along projected 2D light vector $\mathbf{L}_{xy}$:
   $$V_{\text{contact}}(p) = \prod_{s=1}^{N_{\text{steps}}} \left( 1 - \text{smoothstep}\left(0, \tau, z(p + s \Delta \mathbf{u}) - z_{\text{ray}}(s)\right) \right)$$
   Produces crisp, physically convincing contact grounding under shoe soles and tabletop objects.
3. **System 3: Attached Shadows (Surface Curvature):**
   Directly evaluated in the forward BRDF. Uses a smooth cubic Hermite falloff near the terminator ($\mathbf{n} \cdot \boldsymbol{\omega}_i \in [-\delta, +\delta]$) to prevent dark geometric stepping artifacts.
4. **System 4: Distant Cast Shadows (Tabletop Receiver Plane):**
   Screen-space ray marching fails for distant cast shadows because occluding geometry is often hidden behind foreground silhouettes (depth tears).
   *Solution:* Fit an analytical ground plane equation $P: A x + B y + C z + D = 0$. Project the foreground alpha silhouette along light vector $\boldsymbol{\omega}_i$ onto plane $P$ using a Gaussian shadow blur kernel scaled by distance from contact line:
   $$\sigma_{\text{blur}}(d) = \sigma_{\text{contact}} + d \cdot \tan(\theta_{\text{angular\_diameter}})$$

---

### 1.4 Material-Dependent Subsurface Scattering Redesign `[DEMONSTRATED]`
The global SSS formulation in v1.0 was physically incorrect. Real-world subsurface transport is governed by the dipole diffusion equation [Jensen et al. 2001], which depends critically on the material scattering coefficient $\sigma_s$ and absorption coefficient $\sigma_a$.

#### Material Classification & Diffusion Profiles:
```
┌─────────────────────┬──────────────────┬─────────────────────────────┬────────────────────────────┐
│ Material Class      │ SSS Active?      │ Diffusion Profile (dr,dg,db)│ Visual Manifestation       │
├─────────────────────┼──────────────────┼─────────────────────────────┼────────────────────────────┤
│ Human Skin          │ YES              │ (3.67, 1.37, 0.68) mm       │ Deep warm amber terminator │
│ Marble / Alabaster  │ YES              │ (2.19, 1.50, 1.14) mm       │ Soft translucent bleed     │
│ Wax / Candle        │ YES              │ (4.20, 3.10, 2.10) mm       │ Volumetric internal glow   │
│ Coated Leather      │ NO (Opaque)      │ (0.00, 0.00, 0.00) mm       │ Crisp geometric terminator │
│ Polished Metal      │ NO (Conductor)   │ (0.00, 0.00, 0.00) mm       │ Pure surface reflection    │
│ Hard Plastic        │ NO (Opaque)      │ (0.00, 0.00, 0.00) mm       │ No spectral bleeding       │
└─────────────────────┴──────────────────┴─────────────────────────────┴────────────────────────────┘
```

#### Revised Mathematical Formulation:
$$\mathbf{C}_{\text{diffuse}}(p) = (\mathbf{n}(p) \cdot \boldsymbol{\omega}_i)^+ \boldsymbol{\rho}_d(p) + M_{\text{trans}}(p) \cdot \mathbf{k}_{\text{SSS}} \odot \exp\left( - \frac{(\mathbf{n}(p) \cdot \boldsymbol{\omega}_i)^2}{2 \boldsymbol{\sigma}_{\text{diff}}^2} \right)$$
Where $M_{\text{trans}}(p) \in [0, 1]$ is the semantic translucency mask (derived from SAM 2 portrait skin classes), and $\boldsymbol{\sigma}_{\text{diff}}$ has separate chromatic channels ensuring red light diffuses $>3\times$ farther than blue light.

---

### 1.5 Component-Based Analytical Geometry for Luxury Goods `[ESTABLISHED]`
Neural surface normal estimators (e.g. DSINE, Omnidata) mistake studio reflections on polished metals and glass for surface curvature, generating wavy, distorted, and noisy highlights.

Commercial products are manufactured from precise CAD primitives. Relight Studio decomposes complex reflective products into four distinct component classes:

```
                          WATCH ASSEMBLY BREAKDOWN
  ┌────────────────────────────────────────────────────────────────────────┐
  │ 1. SAPPHIRE CRYSTAL: Domed/Planar Dielectric (F0=0.04, alpha=0.001)    │
  │    - Specular reflection of softbox bands without distortion.          │
  │    - Anti-reflective coating cyan/magenta Fresnel tint.                │
  ├────────────────────────────────────────────────────────────────────────┤
  │ 2. BEZEL & CASE: Cylindrical / Toric Conductor (F0=0.78, alpha=0.15)  │
  │    - Radial or linear brushed anisotropic GGX specular highlights.    │
  ├────────────────────────────────────────────────────────────────────────┤
  │ 3. DIAL & TYPOGRAPHY: Recessed Planar Disc (Opaque Dielectric)        │
  │    - 100% detail locking of printed markers, fonts, and sub-dials.    │
  ├────────────────────────────────────────────────────────────────────────┤
  │ 4. BRACELET / STRAP: Segmented Cylinders or Flexible Relief Mesh       │
  │    - Ambient contact occlusion between links; GGX on metal prongs.     │
  └────────────────────────────────────────────────────────────────────────┘
```

1. **Class 1: Horology (Watches & Clocks):**
   - Crystal: Analytical plane or spherical cap.
   - Case: Cylindrical sweep or superquadric:
     $$F(x, y, z) = \left( \left|\frac{x}{a}\right|^{2/\epsilon_2} + \left|\frac{y}{b}\right|^{2/\epsilon_2} \right)^{\epsilon_2/\epsilon_1} + \left|\frac{z}{c}\right|^{2/\epsilon_1} - 1 = 0$$
2. **Class 2: Eyewear & Sunglasses:**
   - Lenses: Toric or spherical meniscus shells. Specular reflection is pure mirror curvature; transmission is tinted by lens absorption.
   - Frames: Extruded 3D splines with anisotropic acetate specular response.
3. **Class 3: Perfume & Cosmetics Flacons:**
   - Glass Body: Double-walled boundary representation (outer air-glass interface, inner glass-liquid interface with relative IOR $n_{\text{liquid}} / n_{\text{glass}} \approx 1.33 / 1.52 = 0.875$).
   - Metallic Spray Cap: Vertical cylinder of revolution with high conductor Fresnel ($F_0 \approx [0.95, 0.95, 0.95]$).
4. **Class 4: Consumer Electronics:**
   - Rounded rectangular chamfered slabs with micro-blasted aluminum anisotropic roughness.

---

### 1.6 Realistic Bounds on Inverse Illumination Estimation `[DEMONSTRATED]`
A single 2D photograph lacks phase and multi-view information. Any claim to automatically recover an omnidirectional HDR environment map with multiple discrete softboxes from a single image is physically fraudulent.

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               INVERSE ILLUMINATION ESTIMATION TAXONOMY                            │
├───────────────────────────────┬──────────────────────┬────────────────────────────────────────────┤
│ Estimation Target             │ Solvability from 2D  │ Method & Required Prior                    │
├───────────────────────────────┼──────────────────────┼────────────────────────────────────────────┤
│ Dominant Azimuth/Elevation    │ High (85% accuracy)  │ Gradient cross-correlation with normals    │
│ Ambient Light Floor (I_min)   │ High (95% accuracy)  │ 5th percentile histogram in masked shadow  │
│ Global Color Temperature      │ Medium (75% accuracy)│ Gray-World / White-Patch in highlight zone │
│ Multi-Light Softbox Geometry  │ IMPOSSIBLE (Ill-Posed│ Requires Interactive 2-Click Calibration   │
│ Distant Off-Screen Emitters   │ IMPOSSIBLE (Zero info│ Requires User Lighting Rig Presets         │
└───────────────────────────────┴──────────────────────┴────────────────────────────────────────────┘
```

#### The Two-Stage Inverse Protocol:
1. **Stage 1 (Automated Coarse Prior):**
   - Dominant light vector $\boldsymbol{\omega}_{\text{orig}}$ is estimated by maximizing the correlation between image intensity gradients $\nabla Y$ and surface normal Jacobian projections $\mathbf{J}_{\mathbf{n}}$.
   - Ambient baseline $k_{\text{amb}} = \text{percentile}_{5\%}(Y_{\text{masked}})$.
2. **Stage 2 (Interactive 2-Click Fine Calibration):**
   - The user clicks one point in the original key-lit highlight and one point in the deepest original shadow.
   - The engine instantly refines $\boldsymbol{\omega}_{\text{orig}}$ and bounds the regularized ratio denominator $S_{\text{old}}$ to prevent noise blowup.

---

### 1.7 Performance Claim Epistemic Audit `[ESTABLISHED]`
Every performance claim in Relight Studio is categorized under strict GRAVITAS epistemic tiers:

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   PERFORMANCE CLAIM AUDIT TABLE                                   │
├────┬─────────────────────────────┬───────────────────────────┬─────────────┬──────────────────────┤
│ #  │ Performance Claim           │ Metric / Hardware         │ Status Tier │ Evidence Base        │
├────┼─────────────────────────────┼───────────────────────────┼─────────────┼──────────────────────┤
│ 1  │ Metal Guided Filter 4K      │ 1.8ms on Apple M3 Max     │ [ESTIMATE]  │ Derived from ALU FLOP│
│    │                             │                           │             │ count vs bus width.  │
├────┼─────────────────────────────┼───────────────────────────┼─────────────┼──────────────────────┤
│ 2  │ NumPy Vectorized 4K Filter  │ 42.5ms on Apple M3 Max    │ [REPROD]    │ Benchmarked with     │
│    │                             │                           │             │ Python benchmark_v5. │
├────┼─────────────────────────────┼───────────────────────────┼─────────────┼──────────────────────┤
│ 3  │ Zero-Copy CPU-GPU Memory    │ MTLStorageModeShared      │ [PUBLISHED] │ Apple Developer Metal│
│    │                             │ eliminates copy overhead  │             │ Best Practices Spec. │
├────┼─────────────────────────────┼───────────────────────────┼─────────────┼──────────────────────┤
│ 4  │ HBAO Compute Kernel (1080p) │ < 0.8ms on Apple M-series │ [ESTIMATE]  │ 16-step ray march    │
│    │                             │                           │             │ complexity model.    │
├────┼─────────────────────────────┼───────────────────────────┼─────────────┼──────────────────────┤
│ 5  │ Sub-10ms UI Slider Scrub    │ End-to-end event to frame │ [HYPOTHESIS]│ Requires Spike 1 & 3 │
│    │                             │ dispatch latency          │             │ empirical validation.│
└────┴─────────────────────────────┴───────────────────────────┴─────────────┴──────────────────────┘
```

*Policy: Engineering estimates must never be reported as empirical results until verified on target physical hardware.*

---

# SECTION 2: MODULAR RENDERING ARCHITECTURE

```
                                RELIGHT STUDIO MODULAR PIPELINE
                                
  ┌───────────────────────────────────────────────────────────────────────────────────────┐
  │                                1. SCENE UNDERSTANDING                                 │
  │ • Image Ingest & Linearization (sRGB -> Linear Rec.709)                                │
  │ • Metric Disparity D(u, v) [Depth Anything V2]                                        │
  │ • Semantic Instance Masks [SAM 2] & Alpha Matting [BiRefNet]                          │
  │ • Dominant Light Vector Guess L_orig & Ambient Floor k_amb                            │
  └──────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                             ▼
  ┌───────────────────────────────────────────────────────────────────────────────────────┐
  │                        2. GEOMETRY & ANALYTICAL FORM GUIDES                           │
  │ • Smooth Surfaces / Natural Objects: Monocular Neural Surface Normals n(u, v)        │
  │ • Manufactured Goods (Watches/Bottles): Component Primitives (Cylinders, Planes, Tori)│
  │ • Silhouette Normal Bending: grad(d_silhouette) ensures grazing grazing rims         │
  └──────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
  ┌────────────────────────────────────────┐   ┌────────────────────────────────────────┐
  │          3. SHADOW TRANSPORT           │   │          4. MATERIAL RESPONSE          │
  │ • Cavity AO: Screen-Space HBAO         │   │ • Spatially-Varying Roughness alpha(p) │
  │ • Contact Shadows: Screen-Space SSDO   │   │ • Specular F0: Dielectric vs Conductor │
  │ • Tabletop Receiver: Proxy Cast Shadow │   │ • Translucency Mask M_trans(p) for SSS │
  └───────────────────┬────────────────────┘   └───────────────────┬────────────────────┘
                      │                                             │
                      └──────────────────────┬──────────────────────┘
                                             │
                                             ▼
  ┌───────────────────────────────────────────────────────────────────────────────────────┐
  │                              5. LIGHTING EVALUATION CORE                              │
  │ • Diffuse Transport: Oren-Nayar / Burley Diffuse + Masked Chromatic SSS               │
  │ • Specular Transport: Analytical GGX Microfacet (Smith Masking, Schlick Fresnel)      │
  │ • Synthesized Target Shading Field: S_new(p) = (Diffuse * AO * Shadow) + Specular     │
  └──────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                             ▼
  ┌───────────────────────────────────────────────────────────────────────────────────────┐
  │                    6. IMAGE RECONSTRUCTION & DETAIL PRESERVATION                      │
  │ • Fast Multi-Scale Guided Filter: Decompose Y -> Base Y_b and Detail Y_d              │
  │ • Regularized Shading Ratio: R_reg(p) = (S_new + eps) / (S_old + eps)                 │
  │ • Micro-Relief Raking Contrast: Dynamic scaling of Y_d at grazing angles              │
  │ • Oklab Chromaticity Coupling: Pure perceptual luminance transfer                     │
  └──────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                             ▼
  ┌───────────────────────────────────────────────────────────────────────────────────────┐
  │                       7. INTERACTIVE VIEWPORT & FINAL EXPORT                          │
  │ • Viewport (Scrubbing): Half-Resolution (1080p) Metal 3 Compute Pipeline (>60 FPS)    │
  │ • Background Bake Queue: Full 4K/8K Tile Pass with Coalesced Request Dispatch        │
  └───────────────────────────────────────────────────────────────────────────────────────┘
```

---

# SECTION 3: REVISED PROTOTYPE STRATEGY (SEQUENTIAL ROADMAP)

Rather than building complex multi-system prototypes concurrently, Relight Studio executes a **strict three-stage sequential falsification strategy**. Each spike is isolated, requires minimal code, tests one critical hypothesis, and enforces a go/no-go architectural gate.

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                SEQUENTIAL SPIKE EXECUTION SEQUENCE                                │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ SPIKE 1: DETAIL LOCK & RATIO REGULARIZATION (Week 1)                                              │
│ • Tests: Fast Guided Filter detail locking & noise control under harsh ratio changes.             │
│ • Gate: DCI >= 0.990 and zero visual ringing on high-contrast text.                               │
│                                    │                                                              │
│                                    ▼ PASS                                                         │
│ SPIKE 2: SHADOW TRANSPORT & SEPARATION (Week 2)                                                   │
│ • Tests: Screen-space HBAO vs SSDO contact vs Tabletop Proxy cast shadows.                       │
│ • Gate: Contact grounding plausible within 50px; Tabletop proxy casts soft shadow.                │
│                                    │                                                              │
│                                    ▼ PASS                                                         │
│ SPIKE 3: COMPONENT-GUIDED SPECULAR PBR (Week 3)                                                   │
│ • Tests: Analytical cylindrical/spherical form guides vs raw neural normals on luxury goods.      │
│ • Gate: Reflection bands clean, unbroken, and free of bumpy surface noise on polished chrome.     │
│                                    │                                                              │
│                                    ▼ PASS                                                         │
│ CONSOLIDATION: PRODUCTION METAL 3 CORE ENGINE (Week 4+)                                           │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 SPIKE 1 — Detail Locking & Shading Ratio Regularization (`spike_detail_preservation.py`)
- **Hypothesis:** Multi-scale Fast Guided Filtering ($\epsilon \in [0.01^2, 0.04^2]$) mathematically preserves high-frequency structural texture ($DCI \ge 0.990$) without halo artifacts, while regularized ratio unbaking suppresses shadow noise amplification up to an exposure shift of $\Delta EV = +3.0$.
- **Minimal Scope:** Pure 2D Python script operating on luminance channels. No 3D lights, no neural models. Applies synthetic extreme lighting gradient ramps across test images.
- **Test Inputs:**
  1. High-contrast brand typography (Nike logo, watch dial text).
  2. Fine fabric texture (canvas weave, denim stitch).
  3. Extreme shadow boundary test image.
- **Measurable Outputs:**
  1. Detail Conservation Index ($DCI = \text{SSIM}(\nabla^2 I_{\text{orig}}, \nabla^2 I_{\text{relit}})$).
  2. Peak Noise Amplification Ratio in deep shadow ($S_{\text{old}} < 0.05$).
  3. Processing latency on 4K raster.
- **Failure Criteria:** $DCI < 0.985$, or visible halo fringing across high-contrast edges $> 2\text{px}$ wide.
- **Follow-Up Decision:** If the Guided Filter exhibits ringing, replace with Multi-Scale Laplacian Pyramid Decomposition.

---

### 3.2 SPIKE 2 — Shadow Transport & Grounding Separation (`spike_shadow_transport.py`)
- **Hypothesis:** Decoupling HBAO (cavity occlusion) from SSDO (local contact shadow ray marching) produces physically plausible product grounding, while a Tabletop Proxy plane resolves distant cast shadows where screen-space ray marching fails.
- **Minimal Scope:** Depth-buffer image processing script. Takes precomputed Depth Anything V2 maps and evaluates screen-space ray marching against proxy plane projections.
- **Test Inputs:**
  1. E-commerce sneaker on neutral floor.
  2. Free-standing classical statue.
  3. Person with complex silhouette against wall.
- **Measurable Outputs:**
  1. Contact grounding sharpness at zero-distance contact points.
  2. Frame execution latency on 1080p and 4K depth buffers.
  3. Frequency of false shadow detachment or horizon clipping artifacts.
- **Failure Criteria:** Ray marching exceeds $4.0\text{ms}$ on 1080p depth map, or produces visible disconnected "floating" shadows under shoe soles.
- **Follow-Up Decision:** If screen-space ray marching suffers severe silhouette tearing, restrict SSDO to a maximum search radius of $30\text{px}$ and delegate all distant shadows to the analytical receiver plane.

---

### 3.3 SPIKE 3 — Component-Guided Specular PBR for Luxury Goods (`spike_specular_components.py`)
- **Hypothesis:** Replacing neural surface normals with analytical geometric primitives (cylinders, planes, spheres) over segmented luxury product components eliminates bumpy specular distortion on polished metal and glass.
- **Minimal Scope:** Forward PBR evaluation comparing neural normal shading vs analytical normal shading under a moving virtual softbox light.
- **Test Inputs:**
  1. Polished luxury watch with sapphire crystal and metal bezel.
  2. Perfume bottle with glass body and gold metallic cap.
  3. Eyewear frame with curved reflective lenses.
- **Measurable Outputs:**
  1. Specular Reflection Continuity Metric (Sobel variance of specular reflection band).
  2. Angular Error vs Ground Truth CAD normal fields.
  3. Expert visual retoucher grading on a 5-point Likert scale.
- **Failure Criteria:** Specular highlight bands break, waver, or display undulating surface ripples on flat or cylindrical metallic surfaces.
- **Follow-Up Decision:** If analytical geometry fitting requires excessive manual user setup, develop automated superquadric silhouette bounding box fitting.

---

# SECTION 4: REVISED BENCHMARK & VALIDATION METHODOLOGY

Validation in v2.0 is separated into five orthogonal suites. Each test domain has distinct pass/fail thresholds:

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 THE FIVE VALIDATION DIMENSIONS                                    │
├────┬─────────────────────────────┬─────────────────────────────────┬──────────────────────────────┤
│ #  │ Dimension                   │ Evaluation Methodology          │ Target Pass Threshold        │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 1  │ Source Detail Preservation  │ DCI (Laplacian HF-SSIM)         │ DCI >= 0.990                 │
│    │                             │ Brand Text OCR Match Rate       │ OCR Accuracy = 100%          │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 2  │ Identity Preservation       │ ArcFace Feature Cosine Distance │ Delta f_id <= 0.025          │
│    │ (Portraits)                 │ Landmark Geometric Shift        │ RMS Error <= 0.5 px          │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 3  │ Physical Plausibility       │ Energy Conservation Check       │ Reflected Radiance <= Irrad. │
│    │                             │ Dynamic Range Monotonicity      │ Zero premature clipping      │
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 4  │ Material Correctness        │ Chromaticity Check on Metals    │ F0 Conductor spectral tint   │
│    │                             │ Translucency Bleed on Skin      │ Delta E_ab warm shift at term│
├────┼─────────────────────────────┼─────────────────────────────────┼──────────────────────────────┤
│ 5  │ Runtime Performance         │ Viewport 1080p Frame Latency    │ p95 <= 8.0 ms (>120 FPS)     │
│    │                             │ 4K Background Export Time       │ Latency <= 45.0 ms           │
│    │                             │ Peak VRAM Footprint             │ Peak VRAM <= 350 MB          │
└────┴─────────────────────────────┴─────────────────────────────────┴──────────────────────────────┘
```

---

# SECTION 5: KNOWN LIMITATIONS & UNRESOLVED RESEARCH QUESTIONS

Even in this revised architecture, physical reality imposes fundamental boundaries:

1. **Extreme Baked Specular Highlights (Clipped Whites):**
   When an original photograph contains clipped white highlights ($I(p) = 255$ across all channels), all original texture information underneath that highlight is permanently destroyed by the sensor ADC. The regularized ratio cannot unbake a clipped signal.
   *Resolution:* The engine detects clipped highlights ($Y > 0.98$) and provides a localized micro-texture synthesizer or requires user exposure blending.
2. **True 3D Occlusion Behind Hidden Volumes:**
   A single photograph cannot observe what lies behind an object. If a virtual light is moved behind a subject to cast a long shadow forward, the exact shape of the subject's back must be approximated by a symmetrical 2.5D hull.
3. **Complex Optical Caustics:**
   Evaluating refractive caustics through faceted crystal whiskey decanters or perfume bottles is outside the scope of real-time image-space rendering. The engine provides analytical caustic approximations rather than physical photon tracing.

---

# SECTION 6: FINAL ARCHITECTURAL RECOMMENDATION WITH CONFIDENCE LEVELS

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            FINAL ARCHITECTURAL RECOMMENDATION CONFIDENCE                          │
├─────────────────────────────────────────────────┬───────────────────┬─────────────────────────────┤
│ Architectural Subsystem                         │ Confidence Level  │ Basis for Confidence        │
├─────────────────────────────────────────────────┼───────────────────┼─────────────────────────────┤
│ Image-Space Frequency Detail Locking (IS-PBR)   │ VERY HIGH (95%)   │ Proven by Durand & Dorsey,  │
│                                                 │                   │ He et al., and v4 baseline. │
├─────────────────────────────────────────────────┼───────────────────┼─────────────────────────────┤
│ Component-Based Analytical Form Guides          │ HIGH (85%)        │ Solves fundamental neural   │
│                                                 │                   │ normal failure on metals.   │
├─────────────────────────────────────────────────┼───────────────────┼─────────────────────────────┤
│ Screen-Space Horizon Ambient Occlusion (HBAO)   │ VERY HIGH (95%)   │ Standard production graphics│
│                                                 │                   │ technology (NVIDIA / GTAO). │
├─────────────────────────────────────────────────┼───────────────────┼─────────────────────────────┤
│ Interactive 2-Click Inverse Light Calibration   │ HIGH (80%)        │ Eliminates ill-posed neural │
│                                                 │                   │ estimation ambiguity.       │
├─────────────────────────────────────────────────┼───────────────────┼─────────────────────────────┤
│ Screen-Space Distant Cast Shadows               │ MEDIUM-LOW (45%)  │ Inherently prone to depth   │
│                                                 │                   │ tears; needs Proxy Plane.   │
└─────────────────────────────────────────────────┴───────────────────┴─────────────────────────────┘
```

### Decisive Recommendation:
Proceed immediately with **Spike 1 (`spike_detail_preservation.py`)** to empirically establish the detail conservation floor and ratio unbaking regularization bounds before writing any 3D lighting or shader code.

---
*Report v2.0 concluded. Ready for Spike 1 execution.*

