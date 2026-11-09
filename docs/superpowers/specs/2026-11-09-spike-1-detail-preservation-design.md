# RELIGHT STUDIO — SPIKE 1 DESIGN SPECIFICATION & EXECUTION PLAN
## Detail Preservation, Regularized Shading Reconstruction & Color Integrity

**Document ID:** RS-SPEC-SPIKE-1-v1.1  
**Date:** 2026-11-09  
**Status:** VALIDATED ARCHITECTURAL SPECIFICATION — BUILDER CHECK COMPLETE  
**Domain:** Computational Photography, Image-Space Frequency Separation, Color Science  
**Workspace File:** `spike_detail_preservation.py` (Isolated Script)  
**Baseline Isolation:** Strictly isolated; does not import, modify, or depend on `engine/relighter_v4.py`.  

---

## 1. INTENT, GOALS & ANTI-GOALS

### 1.1 Mission Statement
Spike 1 is a controlled, isolated numerical imaging experiment designed to empirically test whether image-space frequency decomposition and regularized illumination reconstruction can alter apparent scene lighting while preserving photographic micro-structure, edge phase, and color fidelity.

### 1.2 Hypotheses to Validate (No Unverified Claims)
- **Hypothesis H1 (Detail Preservation):** Edge-preserving frequency separation retains high-frequency spatial gradients and structural texture ($DCI \ge 0.990$) under moderate exposure adjustments ($\Delta EV \in [-2.0, +2.0]$).
- **Hypothesis H2 (Halo Mitigation):** Multi-scale guided filtering and regularized spatial filtering suppress boundary halos to $< 1.5\text{ pixels}$ width across high-contrast luminance step edges.
- **Hypothesis H3 (Noise Boundedness):** Regularized shading ratios with explicit denominator floors ($\epsilon_{\text{old}} \ge 0.02$) limit sensor read-noise amplification in deep shadows to $\le 3.5\times$, avoiding chromatic speckling.
- **Hypothesis H4 (Color Gamut Preservation):** Oklab lightness remapping with explicit gamut mapping eliminates hue shifts observed under conventional linear RGB scalar scaling during extreme lighting shifts.

### 1.3 Non-Goals and Anti-Goals
- **Anti-Goal 1:** Do not implement 3D geometry, surface normals, or depth map unprojection. Spike 1 evaluates 2D image-space reconstruction only.
- **Anti-Goal 2:** Do not implement GPU Metal compute or C++ acceleration. NumPy and SciPy provide the reference numerical baseline.
- **Anti-Goal 3:** Do not introduce diffusion, GANs, or generative hallucination. Original pixel information is the ground truth.
- **Anti-Goal 4:** Do not claim physically accurate diffuse-specular separation. Specular handling in this 2D spike is strictly an independently evaluated highlight protection approximation.

---

## 2. MATHEMATICAL FORMULATIONS

### 2.1 Radiometric Linearization & Working Color Spaces
All physical and frequency operations occur in linear optical radiance space.

1. **sRGB Opto-Electronic Transfer Function (OETF) Inversion:**
   For each channel $C_{\text{srgb}} \in [0, 1]$:
   $$C_{\text{lin}} = \begin{cases} \frac{C_{\text{srgb}}}{12.92}, & C_{\text{srgb}} \le 0.04045 \\ \left( \frac{C_{\text{srgb}} + 0.055}{1.055} \right)^{2.4}, & C_{\text{srgb}} > 0.04045 \end{cases}$$
2. **Linear Luminance (Rec.709 / CIE 1931):**
   $$Y = 0.2126 R_{\text{lin}} + 0.7152 G_{\text{lin}} + 0.0722 B_{\text{lin}}$$
3. **Oklab Color Space Transformation [Ottosson 2020]:**
   Linear RGB is mapped to LMS cone responses via matrix $\mathbf{M}_1$:
   $$\begin{bmatrix} l \\ m \\ s \end{bmatrix} = \mathbf{M}_1 \begin{bmatrix} R_{\text{lin}} \\ G_{\text{lin}} \\ B_{\text{lin}} \end{bmatrix}, \quad \mathbf{M}_1 = \begin{bmatrix} 0.4122214708 & 0.5363325363 & 0.0514459929 \\ 0.2119034982 & 0.6806995451 & 0.1073969566 \\ 0.0883024619 & 0.2817188376 & 0.6299787005 \end{bmatrix}$$
   Non-linear compression: $l' = l^{1/3}, \; m' = m^{1/3}, \; s' = s^{1/3}$.
   Lightness ($L$) and opponent chromaticities ($a, b$) are obtained via $\mathbf{M}_2$:
   $$\begin{bmatrix} L \\ a \\ b \end{bmatrix} = \mathbf{M}_2 \begin{bmatrix} l' \\ m' \\ s' \end{bmatrix}, \quad \mathbf{M}_2 = \begin{bmatrix} 0.2104542553 & 0.7936177850 & -0.0040720468 \\ 1.9779984951 & -2.4285922050 & 0.4505937099 \\ 0.0259040371 & 0.7827717662 & -0.8086757660 \end{bmatrix}$$

---

### 2.2 Color Reconstruction Methods (Evaluated Orthogonally)
When target luminance $Y_{\text{relit}}$ is computed, original color channels are updated using one of three independent methods:

1. **Method C1: Linear RGB Scalar Scaling:**
   $$\mathbf{C}_{\text{out}}(p) = \mathbf{C}_{\text{lin}}(p) \cdot \left( \frac{Y_{\text{relit}}(p)}{Y(p) + \epsilon} \right)$$
   *Known Vulnerability:* If any channel exceeds 1.0, naive clipping shifts hue toward secondary primaries (e.g. skin tones shifting toward yellow).
2. **Method C2: Oklab Lightness Remapping (Unconstrained):**
   - Compute luminance-scaled reference RGB: $\mathbf{C}_{\text{scaled}} = \mathbf{C}_{\text{lin}} \cdot \left(\frac{Y_{\text{relit}}}{Y_{\text{orig}} + \epsilon}\right)$.
   - Convert $\mathbf{C}_{\text{scaled}}$ to Oklab to extract the exact chromatic lightness: $L_{\text{target}} = \text{Oklab}( \mathbf{C}_{\text{scaled}} )_L$.
   - Reconstruct in Oklab: $(L_{\text{out}}, a_{\text{out}}, b_{\text{out}}) = (L_{\text{target}}, a_{\text{orig}}, b_{\text{orig}})$, then invert to linear RGB.
   *Known Vulnerability:* Increasing $L$ while holding $(a, b)$ constant can push saturated colors outside the sRGB gamut boundary.
3. **Method C3: Oklab with Explicit Gamut Mapping (Chroma Cusp Bisection):**
   If $(L_{\text{target}}, a_{\text{orig}}, b_{\text{orig}})$ inverts to linear RGB with any channel $< 0$ or $> 1$, perform binary search bisection (16 iterations) along the constant-hue ray:
   $$a(t) = t \cdot a_{\text{orig}}, \quad b(t) = t \cdot b_{\text{orig}}, \quad t \in [0, 1]$$
   Find the maximum $t^* \in [0, 1]$ such that $\mathbf{C}_{\text{lin}}(L_{\text{target}}, a(t^*), b(t^*)) \in [0, 1]^3$.
   *Theoretical Advantage:* Preserves perceptual hue and lightness without harsh channel clamping.

---

### 2.3 The Five Competing Reconstruction Paradigms

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                COMPETING RECONSTRUCTION PARADIGMS                                 │
├────┬─────────────────────────────┬────────────────────────────────────────────────────────────────┤
│ ID │ Paradigm Name               │ Core Mathematical Formulation                                  │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ A  │ Conventional Luminance      │ Direct scalar multiplication: Y_relit = Y * R                  │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ B  │ Single-Scale Guided Filter  │ log-luminance split: Y = Y_b * Y_d; Y_relit = (Y_b * R) * Y_d  │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ C  │ Multi-Scale Guided Filter   │ 3-scale split: Y = Y_base + D_fine + D_medium                  │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ D  │ Laplacian Pyramid           │ 5-level pyramid: gain applied only to L_coarse                 │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ E  │ Regularized Shading Ratio   │ Log-ratio spatial regularization with bounded detail coupling  │
└────┴─────────────────────────────┴────────────────────────────────────────────────────────────────┘
```

#### Paradigm A: Conventional Luminance Adjustment (Baseline)
Applies target lighting field $R(p)$ directly to luminance:
$$Y_{\text{relit}}(p) = Y(p) \cdot R(p)$$
*Baseline Role:* Measures the worst-case noise amplification and highlight blowout when no frequency decomposition is used.

#### Paradigm B: Single-Scale Guided Filter Decomposition
1. Guidance image $I = \text{sRGB}(Y)$.
2. Base layer in log domain:
   $$B(p) = \text{GuidedFilter}\big(I, \ln(Y + \epsilon), \text{radius}=r_0, \text{eps}=\epsilon_0\big)$$
3. Detail residual: $D(p) = \ln(Y + \epsilon) - B(p)$.
4. Recomposition:
   $$Y_{\text{relit}}(p) = \exp\big( B(p) + \ln R(p) + D(p) \big) = \exp(B(p)) \cdot R(p) \cdot \exp(D(p))$$

#### Paradigm C: Multi-Scale Guided Filter Decomposition
Decomposes luminance into coarse, medium, and fine bands using two filter passes ($r_{\text{fine}} = 4, \epsilon_{\text{fine}} = 0.04^2$; $r_{\text{med}} = 16, \epsilon_{\text{med}} = 0.02^2$):
$$B_{\text{fine}} = \text{GuidedFilter}(I, Y, r_{\text{fine}}, \epsilon_{\text{fine}}), \quad D_{\text{fine}} = Y - B_{\text{fine}}$$
$$B_{\text{coarse}} = \text{GuidedFilter}(I, B_{\text{fine}}, r_{\text{med}}, \epsilon_{\text{med}}), \quad D_{\text{med}} = B_{\text{fine}} - B_{\text{coarse}}$$
Recomposition applies lighting ratio $R(p)$ primarily to $B_{\text{coarse}}$:
$$Y_{\text{relit}}(p) = B_{\text{coarse}}(p) \cdot R(p) + D_{\text{med}}(p) \cdot R(p)^{\alpha_{\text{med}}} + D_{\text{fine}}(p) \cdot R(p)^{\alpha_{\text{fine}}}$$
Where $\alpha_{\text{fine}} = 0.5$ dampens extreme detail amplification.

#### Paradigm D: Laplacian Pyramid Reconstruction [Burt & Adelson 1983]
1. Construct 5-level Gaussian pyramid $\{G_0, G_1, \dots, G_4\}$ where $G_0 = Y$.
2. Construct Laplacian pyramid $\{L_0, L_1, \dots, L_3\}$ where $L_k = G_k - \text{Upsample}(G_{k+1})$.
3. Modulate coarsest residual $G_4$ by downsampled lighting field $R_4$:
   $$G'_4 = G_4 \odot R_4$$
4. Reconstruct backward:
   $$G'_k = L_k + \text{Upsample}(G'_{k+1}), \quad Y_{\text{relit}} = G'_0$$

#### Paradigm E: Regularized Shading Ratio with Bounded Detail Coupling
1. Base decomposition: $\ln Y = B + D$ via Guided Filter ($Y_b = \exp(B)$).
2. **Explicit Derivation of $S_{\text{old}}$ and $S_{\text{new}}$ from Lighting Field $R(p)$:**
   In 2D image space (without 3D normals), the original smooth illumination is estimated by the base layer:
   $$S_{\text{old}}(p) = Y_b(p) = \exp(B(p)), \quad S_{\text{new}}(p) = Y_b(p) \cdot R(p)$$
   The raw log-ratio with regularization floors is:
   $$\rho(p) = \ln(S_{\text{new}}(p) + \epsilon_{\text{new}}) - \ln(S_{\text{old}}(p) + \epsilon_{\text{old}}) = \ln(Y_b(p) \cdot R(p) + \epsilon_{\text{new}}) - \ln(Y_b(p) + \epsilon_{\text{old}})$$
   Where $\epsilon_{\text{new}} = 0.02 \times \text{mean}(R)$ and $\epsilon_{\text{old}} = 0.02$.
   *Mathematical Behavior:* In deep shadows ($Y_b \to 0$), the ratio automatically asymptotes to $\ln(\epsilon_{\text{new}} / \epsilon_{\text{old}})$, capping noise amplification. In well-lit regions ($Y_b \gg 0.02$), the ratio equals $\ln R(p)$ exactly.
3. **Explicit Log-Ratio Spatial Regularization:**
   The raw ratio is regularized via edge-preserving guided filtering against guidance $I = \text{sRGB}(Y)$ with radius $r_{\text{ratio}} = 24$ and $\epsilon_{\text{ratio}} = 0.01$:
   $$\bar{\rho} = \text{GuidedFilter}(I, \rho, r_{\text{ratio}}, \epsilon_{\text{ratio}})$$
   This guarantees that ratio spatial gradients $\|\nabla \bar{\rho}\|$ are strictly bounded and do not introduce ringing.
4. **Bounded Detail Modulation Exponent $\lambda(p)$:**
   For Spike 1 (2D baseline), $\lambda(p) = 1.0$ by default. A sweep parameter $\lambda \in \{0.7, 1.0, 1.3\}$ is evaluated under Profile P1 to quantify texture contrast compression vs enhancement.
5. Recomposition:
   $$Y_{\text{relit}}(p) = \exp\left( B(p) + \bar{\rho}(p) + D(p) \cdot \lambda \right)$$

---

### 2.4 Highlight & Specular Protection Approximation
Because single 2D images lack physical 3D BRDF parameters, highlight protection is evaluated as an explicit non-linear shoulder operator:

1. **Specular / Highlight Mask:**
   $$M_{\text{high}}(p) = \text{smoothstep}\left( \tau_{\text{low}}=0.75, \; \tau_{\text{high}}=0.98, \; Y(p) \right)$$
2. **Ratio Attenuation in Highlights:**
   Near original specular highlights, the multiplicative lighting ratio is damped toward unity to prevent highlight blowout:
   $$R_{\text{eff}}(p) = (1 - M_{\text{high}}(p)) \cdot R(p) + M_{\text{high}}(p) \cdot 1.0$$
3. **Additive Highlight Injection:**
   Simulated specular lights $H_{\text{add}}(p) \ge 0$ are added *after* the diffuse ratio recomposition:
   $$Y_{\text{final}}(p) = Y_{\text{relit}}(p) + H_{\text{add}}(p)$$

---

## 3. EXPERIMENTAL MATRIX

The test suite evaluates all combinations across the full matrix:

$$\underbrace{5 \text{ Reconstruction Paradigms}}_{(A, B, C, D, E)} \times \underbrace{3 \text{ Color Methods}}_{(C1, C2, C3)} \times \underbrace{4 \text{ Stress Profiles}}_{(P1, P2, P3, P4)} = \mathbf{60 \text{ Experimental Configurations}}$$

### The 4 Stress Profiles:
- **Profile P1 (Moderate Directional Key):** Smooth exposure ramp $(\Delta EV = +1.5$ on left, $-1.5$ on right).
- **Profile P2 (Deep Shadow Rescue):** Extreme exposure lift ($\Delta EV = +3.5$) on an area with initial luminance $Y \le 0.03$. Tests noise amplification.
- **Profile P3 (Steep Spotlight Edge):** High-frequency step edge in lighting ratio ($R = 0.2$ to $R = 3.0$ across a 5-pixel sigmoid boundary). Tests boundary haloing and gradient orientation flip.
- **Profile P4 (Specular Highlight Injection):** Intense localized highlight ($H_{\text{add}} = +2.5$) on a textured reflective surface. Tests highlight detail preservation.

---

## 4. DATASET REQUIREMENTS & TEST SUITE MANIFEST

### 4.1 Synthetic Test Dataset (Generated Procedurally by the Spike)
1. `syn_step_edge.png`: Binary and blurred step edges ($Y = 0.1 \to 0.9$) for sub-pixel halo width and overshoot measurement.
2. `syn_siemens_star.png`: High-frequency radial chirp pattern to detect texture phase distortion and blur.
3. `syn_gradient_noise.png`: Continuous smooth ramp ($0.0 \to 1.0$) with calibrated Gaussian read noise ($\sigma = 0.005$) and Poisson shot noise to measure noise amplification factor ($NAF$).
4. `syn_macbeth_patches.png`: Standard Macbeth 24-patch color array to evaluate gamut clipping and $\Delta E$ color drift.

### 4.2 Photographic Test Dataset (Local Assets & Real Captures)
1. `real_sneaker.jpg`: Fine canvas fabric weave and nylon stitching (`demo_output/nike_sample.jpg`).
2. `real_portrait.png`: Classical statue beauty capture with skin/stone texture (`demo_output/08_full_studio_relit.png`).
3. `real_typography.png`: Procedurally generated vector-rasterized typography on textured background.
4. `real_watch_metal.png`: Chrome and specular highlight asset (`demo_output/nike_test/custom_light_test.png`).
5. `real_deep_shadow.png`: Outdoor high-contrast landscape with deep shadows (`demo_output/01_original.png`).

*Automatic Deep-Shadow ROI Selection:* Deep-shadow analysis automatically masks all pixels where $Y_{\text{orig}}(p) \le 0.05$.

---

## 5. INDEPENDENT METRIC DEFINITIONS & MATHEMATICAL FORMULAS

Every configuration is evaluated across 8 independent numerical metrics:

1. **High-Frequency Detail Conservation Index ($DCI$):**
   To prevent false penalties from intentional exposure changes, $DCI$ evaluates the **structural correlation component** of SSIM on the high-pass Laplacian band:
   $$DCI = \frac{2 \sigma_{xy} + C_3}{2 \sigma_x \sigma_y + C_3}, \quad x = \nabla^2 I_{\text{orig}}, \; y = \nabla^2 I_{\text{relit}}$$
   Where $\sigma_{xy}$ is the local cross-covariance across an $11 \times 11$ Gaussian window. This metric is scale-invariant to uniform exposure amplification and strictly measures structural phase and texture preservation.
2. **Gradient Orientation Error ($GOE$):**
   Measures angular deviation in edge gradients (detecting gradient inversion / emboss artifacts):
   $$\text{GOE} = \frac{1}{|\mathcal{M}|} \sum_{p \in \mathcal{M}} \arccos\left( \frac{\nabla Y_{\text{orig}}(p) \cdot \nabla Y_{\text{relit}}(p)}{\|\nabla Y_{\text{orig}}(p)\| \|\nabla Y_{\text{relit}}(p)\| + \epsilon} \right) \quad [\text{degrees}]$$
   Evaluated over significant gradient pixels ($\|\nabla Y_{\text{orig}}\| > 0.02$).
3. **Halo Width & Overshoot Amplitude ($HWA, HOA$):**
   Evaluated analytically on `syn_step_edge.png` across a 1D slice normal to the step edge:
   $$HOA = \max\left(0, \; \frac{Y_{\text{relit}}(p) - Y_{\text{expected}}(p)}{Y_{\text{step}}}\right), \quad HWA = \text{width in pixels where } HOA > 0.02$$
   On real photographic scenes, halo artifacts are evaluated visually via side-by-side zoom contact sheets.
4. **Noise Amplification Factor ($NAF$):**
   Evaluated in the smooth deep-shadow ROI ($Y_{\text{orig}} \le 0.05$):
   $$NAF = \frac{\sigma(Y_{\text{relit}})}{\sigma(Y_{\text{orig}})}$$
5. **Color Hue Error ($\Delta h_{ab}$) & Gamut Clipping Rate ($GCR$):**
   - $GCR = \frac{1}{N} \sum_{p} \mathbb{I}\left( \mathbf{C}_{\text{linear}}(p) \notin [0, 1]^3 \right) \times 100\%$.
   - $\Delta h_{ab}$: Mean angular hue shift in Oklab space: $\Delta h_{ab} = |\arctan(b_{\text{relit}}/a_{\text{relit}}) - \arctan(b_{\text{orig}}/a_{\text{orig}})|$ evaluated across non-neutral Macbeth color patches.
6. **Texture Contrast Ratio ($TCR$):**
   Evaluates whether fine texture contrast is maintained, muted, or over-amplified:
   $$TCR = \frac{\text{std}(D_{\text{relit}})}{\text{std}(D_{\text{orig}})}$$
7. **Numerical Stability:**
   Count of `NaN`, `Inf`, or negative values; dynamic range ratio $\max(Y) / \min(Y > 0)$.
8. **Runtime Latency & Memory Targets:**
   - Wall-clock time (milliseconds) per 4K ($3840 \times 2160$) image pass.
   - Peak RSS memory allocation (Megabytes).

---

## 6. ACCEPTANCE & FALSIFICATION CRITERIA

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 ACCEPTANCE CRITERIA DECISION GATES                                │
├────┬─────────────────────────────┬───────────────────────────┬────────────────────────────────────┤
│ #  │ Metric                      │ Minimum Pass Threshold    │ Ideal Architectural Target         │
├────┼─────────────────────────────┼───────────────────────────┼────────────────────────────────────┤
│ G1 │ Detail Index (DCI)          │ DCI >= 0.985              │ DCI >= 0.995                       │
│ G2 │ Gradient Orientation (GOE)  │ GOE <= 5.0 degrees        │ GOE <= 1.5 degrees                 │
│ G3 │ Halo Width (HWA, Synthetic) │ HWA <= 2.0 pixels         │ HWA <= 0.5 pixels (imperceptible)  │
│ G4 │ Noise Amplification (NAF)   │ NAF <= 4.0x               │ NAF <= 2.0x                        │
│ G5 │ Gamut Clipping Rate (GCR)   │ GCR <= 0.5% (with C3)     │ GCR = 0.0%                         │
│ G6 │ 4K Latency (CPU Reference)  │ Latency <= 250 ms         │ Latency <= 80 ms                   │
└────┴─────────────────────────────┴───────────────────────────┴────────────────────────────────────┘
```

#### Decision Rules:
- **Rule 1 (Continue to Spike 2):** At least one reconstruction paradigm passes all gates (G1–G6) across both synthetic and real test suites.
- **Rule 2 (Redesign):** If Guided Filtering exhibits haloing ($HWA > 2.0\text{px}$) or gradient inversion ($GOE > 5^\circ$) on steep spotlight boundaries (P3), redesign spatial regularization using bilateral depth weighting or steerable filters.
- **Rule 3 (Reject):** If all frequency-separation paradigms exhibit unacceptable noise explosion ($NAF > 6.0\times$) in deep shadows compared to simple tone mapping, reject image-space ratio relighting for deep shadow recovery.

---

## 7. EXECUTION PLAN

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   SPIKE 1 IMPLEMENTATION PHASES                                   │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 1: TEST HARNESS & DATASET GENERATION                                                        │
│ • Build procedural synthetic test patterns (Siemens, step edges, Macbeth, noisy ramp).            │
│ • Establish image loading, linear Rec.709 conversion, and sRGB OETF roundtripping.                │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 2: ALGORITHM ENGINES (spike_detail_preservation.py)                                         │
│ • Implement Paradigms A, B, C, D, E.                                                              │
│ • Implement Color Methods C1, C2, C3.                                                             │
│ • Implement Highlight/Specular Protection Shoulder.                                              │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 3: METRIC MEASUREMENT SUITE                                                                 │
│ • Implement DCI, GOE, HWA, NAF, GCR, TCR, and timing benchmark functions.                         │
│ • Generate visual contact sheets (side-by-side zoom crops of typography, pores, and edges).       │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 4: BENCHMARK EXECUTION & DOSSIER GENERATION                                                 │
│ • Run 60-configuration matrix.                                                                    │
│ • Export structured JSON results and high-resolution comparison grids.                            │
│ • Compile Spike 1 Evaluation Report with decisive verdict on Hypothesis H1–H4.                    │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---
*Specification updated with builder check resolutions.*
