# RELIGHT STUDIO — SPIKE 1 DESIGN SPECIFICATION & EXECUTION PLAN (v1.2)
## Rigorous Image-Space Frequency Decomposition, Regularization & Color Gamut Validation

**Document ID:** RS-SPEC-SPIKE-1-v1.2  
**Date:** 2026-11-09  
**Status:** REVISED ARCHITECTURAL SPECIFICATION — PENDING USER APPROVAL  
**Domain:** Computational Photography, Numerical Imaging, Color Science  
**Workspace File:** `spike_detail_preservation.py` (Strictly Isolated Script)  
**Baseline Isolation:** Strictly isolated; does not import, modify, or depend on `engine/relighter_v4.py`.  

---

## 1. INTENT, GOALS & SCIENTIFIC METHODOLOGY

### 1.1 Objective
Spike 1 is an isolated, controlled numerical imaging experiment. Its objective is to determine which image-space frequency decomposition and regularized illumination reconstruction method provides the best measurable balance of:
1. **Controllability:** Freedom to reshape apparent scene illumination across wide dynamic ranges ($\Delta EV \in [-2.0, +3.5]$).
2. **Structural Detail Preservation:** Quantitative retention of high-frequency photographic texture, edge phase, and gradient orientation.
3. **Color & Gamut Integrity:** Prevention of hue shifts, chroma clipping, and saturation collapse.
4. **Noise Boundedness:** Suppression of sensor read/shot noise amplification in deep shadows.
5. **Computational Efficiency:** Minimal CPU latency and predictable memory scaling.

This experiment does not seek to confirm a preferred architecture; it establishes empirical falsification gates to decide whether image-space frequency separation is viable as Relight Studio's core reconstruction engine.

---

## 2. MATHEMATICAL AUDIT & REVISED RECONSTRUCTION FORMULATIONS

### 2.1 Radiometric Calibration & Color Spaces
All operations execute in physical linear radiance space:
$$\mathbf{C}_{\text{lin}} = \text{OETF}^{-1}(\mathbf{C}_{\text{srgb}}), \quad Y = 0.2126 R_{\text{lin}} + 0.7152 G_{\text{lin}} + 0.0722 B_{\text{lin}}$$

Linear RGB is transformed to Oklab $(L, a, b)$ via standard two-step cone-response matrices $\mathbf{M}_1, \mathbf{M}_2$ [Ottosson 2020].

---

### 2.2 Color Reconstruction & Gamut Mapping Suite

When target luminance $Y_{\text{relit}}$ is computed, the color output is derived using one of three independently evaluated methods:

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    COLOR RECONSTRUCTION SUITE                                     │
├────┬─────────────────────────────┬────────────────────────────────────────────────────────────────┤
│ ID │ Method Name                 │ Core Mathematical Formulation                                  │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ C1 │ Linear RGB Scalar Scaling   │ C_out = C_lin * (Y_relit / (Y_orig + eps))                     │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ C2 │ Oklab Lightness Remap       │ L_target = Oklab(C_scaled)_L; keep a_orig, b_orig (Unclamped)  │
├────┼─────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ C3 │ Oklab Gamut Mapping (Cusp)  │ 3-Stage: L-compression -> Neutral guard -> Constant-hue bisect│
└────┴─────────────────────────────┴────────────────────────────────────────────────────────────────┘
```

#### Detailed Formulation of Method C3 (Explicit Gamut Mapping):
1. **Stage 1 (Target Lightness Range Compression):**
   If $L_{\text{target}} > 1.0$, direct display on SDR devices is physically impossible. Apply a soft-shoulder compression curve:
   $$L_{\text{disp}} = \begin{cases} L_{\text{target}}, & L_{\text{target}} \le 0.90 \\ 0.90 + 0.10 \cdot \tanh\left( \frac{L_{\text{target}} - 0.90}{0.10} \right), & L_{\text{target}} > 0.90 \end{cases}$$
2. **Stage 2 (Near-Neutral Singularity Guard):**
   Calculate original chroma $C_{\text{orig}} = \sqrt{a_{\text{orig}}^2 + b_{\text{orig}}^2}$.
   If $C_{\text{orig}} < 10^{-4}$, hue is numerically undefined. Set $a_{\text{out}} = b_{\text{out}} = 0$ (pure neutral gray) to prevent chromatic noise explosion.
3. **Stage 3 (Constant-Hue Chroma Cusp Bisection):**
   For chromatic pixels, test if $\mathbf{C}_{\text{lin}}(L_{\text{disp}}, a_{\text{orig}}, b_{\text{orig}}) \in [0, 1]^3$.
   If out-of-gamut, perform 16 iterations of binary search along the constant-hue ray:
   $$a(t) = t \cdot a_{\text{orig}}, \quad b(t) = t \cdot b_{\text{orig}}, \quad t \in [0, 1]$$
   Find the maximum $t^* \in [0, 1]$ such that $\mathbf{C}_{\text{lin}}(L_{\text{disp}}, a(t^*), b(t^*)) \in [0, 1]^3$.

---

### 2.3 The Five Competing Reconstruction Paradigms

#### Paradigm A: Conventional Luminance Adjustment (Baseline)
Direct linear multiplication:
$$Y_{\text{relit}}(p) = Y(p) \cdot R(p)$$

#### Paradigm B: Single-Scale Guided Filter Decomposition
1. Guidance image $I = \text{sRGB}(Y)$.
2. Base layer in log-luminance: $B(p) = \text{GuidedFilter}\big(I, \ln(Y + \epsilon), r_0=16, \epsilon_0=0.02^2\big)$.
3. Detail residual: $D(p) = \ln(Y + \epsilon) - B(p)$.
4. Recomposition:
   $$Y_{\text{relit}}(p) = \exp(B(p)) \cdot R(p) \cdot \exp(D(p))$$
   *Audit Note:* Guided filtering does *not* guarantee bounded spatial gradients of the ratio or eliminate ringing; it serves as an empirical edge-preserving smoothing baseline.

#### Paradigm C: Multi-Scale Guided Filter Decomposition with Negative-Luminance Diagnostics
1. Octave band decomposition:
   $$B_{\text{fine}} = \text{GuidedFilter}(I, Y, r=4, \epsilon=0.04^2), \quad D_{\text{fine}} = Y - B_{\text{fine}}$$
   $$B_{\text{coarse}} = \text{GuidedFilter}(I, B_{\text{fine}}, r=16, \epsilon=0.02^2), \quad D_{\text{med}} = B_{\text{fine}} - B_{\text{coarse}}$$
2. Recomposition:
   $$Y_{\text{raw}}(p) = B_{\text{coarse}}(p) \cdot R(p) + D_{\text{med}}(p) \cdot R(p)^{0.75} + D_{\text{fine}}(p) \cdot R(p)^{0.50}$$
3. **Negative Luminance Detection & Handling:**
   - Diagnostic count: $N_{\text{neg}} = \sum_p \mathbb{I}(Y_{\text{raw}}(p) < 0)$.
   - Peak negative depth: $\Delta Y_{\text{neg}} = \min(0, \min_p Y_{\text{raw}}(p))$.
   - Reconstructed luminance: Never silently clamp with `np.maximum(0, Y)`. Use an explicit soft-knee floor:
     $$Y_{\text{relit}}(p) = \begin{cases} Y_{\text{raw}}(p), & Y_{\text{raw}}(p) \ge \epsilon \\ \epsilon \cdot \exp\left( \frac{Y_{\text{raw}}(p) - \epsilon}{\epsilon} \right), & Y_{\text{raw}}(p) < \epsilon \end{cases} \quad (\epsilon = 10^{-4})$$

#### Paradigm D: Laplacian Pyramid Reconstruction [Burt & Adelson 1983]
1. Construct 5-level Gaussian pyramid $\{G_0, \dots, G_4\}$ and Laplacian pyramid $\{L_0, \dots, L_3\}$.
2. Modulate coarsest level $G_4$ by downsampled ratio field $R_4$: $G'_4 = G_4 \odot R_4$.
3. Reconstruct backward: $G'_k = L_k + \text{Upsample}(G'_{k+1})$, yielding $Y_{\text{relit}} = G'_0$.
4. Check and record negative-luminance excursions identical to Paradigm C.

#### Paradigm E: Regularized Shading Ratio with Explicit Gradient-Penalized Regularization
1. Base decomposition: $\ln Y = B + D$ via Guided Filter ($Y_b = \exp(B)$).
2. Raw illumination estimates:
   $$S_{\text{old}}(p) = Y_b(p), \quad S_{\text{new}}(p) = Y_b(p) \cdot R(p)$$
   $$\rho_{\text{raw}}(p) = \ln(S_{\text{new}}(p) + \epsilon_{\text{new}}) - \ln(S_{\text{old}}(p) + \epsilon_{\text{old}})$$
3. **Dual Spatial Regularization Comparison:**
   Evaluate two independent spatial regularizers on $\rho_{\text{raw}}$:
   - **E.1 (Guided Filter Regularization):** $\bar{\rho}_{\text{GF}} = \text{GuidedFilter}(I, \rho_{\text{raw}}, r=24, \epsilon=0.01)$.
   - **E.2 (Gradient-Penalized Screened Poisson Regularization):**
     Minimizes the explicit variational energy:
     $$\min_{\bar{\rho}} \sum_p (\bar{\rho}(p) - \rho_{\text{raw}}(p))^2 + \gamma \sum_{\langle p, q \rangle} w_{pq} (\bar{\rho}(p) - \bar{\rho}(q))^2$$
     Where edge weights $w_{pq} = \exp\left( -\frac{\|\nabla I(p)\|^2}{2 \sigma_e^2} \right)$ enforce smoothness across flat areas while penalizing ratio gradients across weak textures.
4. Bounded detail recomposition:
   $$Y_{\text{relit}}(p) = \exp\left( B(p) + \bar{\rho}(p) + D(p) \cdot \lambda \right)$$

---

### 2.4 Highlight & Specular Protection Ablation (Decoupled Control)
Highlight handling is **not** mixed into the core 5-paradigm benchmark. It is evaluated as an isolated ablation (Ablation H+ vs H-):
1. Specular highlight mask: $M_{\text{high}}(p) = \text{smoothstep}(0.75, 0.98, Y(p))$.
2. Effective ratio: $R_{\text{eff}}(p) = (1 - M_{\text{high}}(p)) \cdot R(p) + M_{\text{high}}(p) \cdot 1.0$.
3. Post-recomposition highlight injection: $Y_{\text{final}}(p) = Y_{\text{relit}}(p) + H_{\text{add}}(p)$.

---

## 3. EXPERIMENTAL MATRIX & STRESS PROFILES

$$\underbrace{5 \text{ Reconstruction Paradigms}}_{(A, B, C, D, E)} \times \underbrace{3 \text{ Color Methods}}_{(C1, C2, C3)} \times \underbrace{4 \text{ Stress Profiles}}_{(P1, P2, P3, P4)} = \mathbf{60 \text{ Core Experimental Configurations}}$$

Plus **Ablation Study:** Top 2 performing paradigms evaluated under Highlight Protection (H+ vs H-).

### Stress Profiles:
- **Profile P1 (Directional Key Ramp):** Smooth spatial ramp: $\Delta EV = +1.5$ (left) to $-1.5$ (right).
- **Profile P2 (Deep Shadow Rescue):** Extreme exposure lift ($\Delta EV = +3.5$) on deep shadow regions ($Y \le 0.03$).
- **Profile P3 (Steep Spotlight Step Edge):** Sigmoidal step edge in lighting ratio ($R = 0.2 \to 3.0$ over 5 pixels). Evaluates haloing and gradient orientation flip.
- **Profile P4 (High-Frequency Text/Edge Contrast):** Relighting inverted across a high-contrast binary boundary.

---

## 4. DATASET AUDIT & TEST MANIFEST

### 4.1 Dataset Audit of Workspace Assets
A strict file-system audit of the workspace reveals:
- **Verified Source Photographs:**
  - `demo_output/nike_sample.jpg`: Original camera capture of e-commerce sneaker (fine canvas weave, leather swoosh, rubber sole).
  - `demo_output/01_original.png`: Original camera capture of sunlit alpine landscape (sky, rock texture, deep shadow valley).
  - `/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794143824741_478ce89a.jpg`: Original camera capture of classical marble sculpture (stone texture, carved drapery).
- **Disqualified Files (Previously Misidentified):**
  - `demo_output/08_full_studio_relit.png`: **DISQUALIFIED.** Already processed output of earlier v4 run.
  - `demo_output/nike_test/custom_light_test.png`: **DISQUALIFIED.** Processed test render.
- **Identified Missing Asset Classes:**
  - Real human skin and hair portrait photography.
  - Reflective polished metal / watch luxury product.
  *Protocol for Missing Assets:* Spike 1 will generate procedural, calibrated ground-truth proxies (Siemens star, sub-pixel step edges, Macbeth chart, synthetic noise pairs) and operate on the 3 verified source photographs. Missing classes are formally recorded in the manifest without silent substitution.

### 4.2 Test Dataset Manifest
1. `syn_step_edge`: 1D/2D step edge ($Y = 0.1 \to 0.9$) for halo and edge overshoot analysis.
2. `syn_siemens_star`: Radial high-frequency chirp for texture phase and blur diagnostics.
3. `syn_noise_pair`: Clean continuous ramp $I_{\text{clean}}$ paired with $I_{\text{noisy}} = I_{\text{clean}} + \eta_{\text{read}} + \eta_{\text{shot}}$ ($\sigma_{\text{read}} = 0.005$, gain $g = 0.01$).
4. `syn_macbeth`: 24 standard color patches with known sRGB coordinates.
5. `real_sneaker`: Verified camera photo `demo_output/nike_sample.jpg` (fabric, stitching).
6. `real_landscape`: Verified camera photo `demo_output/01_original.png` (deep shadow valleys).
7. `real_statue`: Verified camera photo `media_1794143824741_478ce89a.jpg` (marble texture).

---

## 5. INDEPENDENT METRIC DEFINITIONS & MATHEMATICAL FORMULAS

Every configuration is evaluated across distinct, orthogonal metrics:

### 5.1 Detail & Structural Preservation Metrics
1. **High-Frequency Detail Conservation Index ($DCI$):**
   Evaluates structural correlation on the high-pass Laplacian band:
   $$DCI = \frac{2 \sigma_{xy} + C_3}{2 \sigma_x \sigma_y + C_3}, \quad x = \nabla^2 I_{\text{orig}}, \; y = \nabla^2 I_{\text{relit}}$$
   Scale-invariant; measures phase and pattern preservation without penalizing exposure changes.
2. **Sub-Pixel Edge Displacement ($\Delta x_{\text{edge}}$):**
   Evaluated on `syn_step_edge` by locating the zero-crossing of the second derivative $\partial_x^2 Y(x)$ via cubic spline interpolation. Unit: pixels.
3. **Multi-Scale Texture Contrast Ratio ($TCR_k$):**
   Across Gaussian pyramid octave bands $k \in \{0, 1, 2\}$:
   $$TCR_k = \frac{\sigma(\text{Band}_k(Y_{\text{relit}}))}{\sigma(\text{Band}_k(Y_{\text{orig}}))}$$

### 5.2 Gradient Orientation & Directional Distortion
4. **Unsigned Gradient Orientation Error ($GOE_{\text{unsigned}}$):**
   Measures structural edge rotation on significant gradient pixels ($\|\nabla Y_{\text{orig}}\| > \tau_{\text{grad}} = 0.03$):
   $$GOE_{\text{unsigned}}(p) = \arccos\left( \frac{|\nabla Y_{\text{orig}}(p) \cdot \nabla Y_{\text{relit}}(p)|}{\|\nabla Y_{\text{orig}}(p)\| \|\nabla Y_{\text{relit}}(p)\| + \epsilon} \right) \times \frac{180^\circ}{\pi} \quad [\text{degrees}]$$
   Values near $0^\circ$ indicate perfect edge orientation preservation; values $> 45^\circ$ indicate gradient inversion or severe optical distortion.

### 5.3 Halo & Boundary Distortion Metrics
5. **Positive Overshoot Amplitude ($HOA^+$) & Negative Undershoot Amplitude ($HOA^-$):**
   On `syn_step_edge` with transition $Y_{\text{expected}}$:
   $$HOA^+ = \max\left(0, \frac{Y_{\text{relit}} - Y_{\text{expected}}}{\Delta Y_{\text{step}}}\right), \quad HOA^- = \max\left(0, \frac{Y_{\text{expected}} - Y_{\text{relit}}}{\Delta Y_{\text{step}}}\right)$$
6. **Halo Width ($HWA$):**
   Spatial distance (pixels) over which $|Y_{\text{relit}}(x) - Y_{\text{expected}}(x)| > 0.02 \times \Delta Y_{\text{step}}$.
7. **Edge Transition Width ($ETW$):**
   The $10\% \to 90\%$ rise distance in pixels across the step edge (distinguishes smoothing from overshoot).

### 5.4 Noise Propagation Metrics
8. **True Noise Amplification Factor ($NAF$):**
   Evaluated strictly on the synthetic clean/noisy pair:
   $$Y_{\text{clean, relit}} = \mathcal{R}(I_{\text{clean}}, R), \quad Y_{\text{noisy, relit}} = \mathcal{R}(I_{\text{noisy}}, R)$$
   $$\mathcal{E}_{\text{noise}}(p) = Y_{\text{noisy, relit}}(p) - Y_{\text{clean, relit}}(p)$$
   $$NAF = \frac{\text{RMS}(\mathcal{E}_{\text{noise}})}{\text{RMS}(I_{\text{noisy}} - I_{\text{clean}})}$$
   Isolates sensor noise amplification from underlying photographic texture.

### 5.5 Color & Gamut Diagnostic Metrics
9. **Gamut Excursion Volume ($V_{\text{excursion}}$):** Percentage of pixels outside $[0, 1]^3$ prior to mapping.
10. **Mean Chroma Loss ($\overline{\Delta C}_{\text{loss}}$):** $\frac{1}{N} \sum_p \max(0, C_{\text{orig}}(p) - C_{\text{out}}(p))$ for out-of-gamut pixels.
11. **Circular Hue Error ($\overline{\Delta h}_{\text{circ}}$):**
    $$\Delta h_{\text{circ}}(p) = \left| \text{atan2}\left( \sin(\theta_{\text{out}} - \theta_{\text{orig}}), \; \cos(\theta_{\text{out}} - \theta_{\text{orig}}) \right) \right| \times \frac{180^\circ}{\pi} \quad [\text{degrees}]$$

### 5.6 Numerical Stability & Performance Metrics
12. **Stability Check:** Counts of `NaN`, `Inf`, negative luminance ($N_{\text{neg}}$), and dynamic range ratio.
13. **Benchmark Timing:** Median ($p50$) and 95th-percentile ($p95$) wall-clock latency (ms) across 10 iterations (3 warm-up runs) on target hardware.
14. **Peak Memory:** Peak Resident Set Size (RSS in MB) recorded via `psutil`.

---

## 6. PROVISIONAL TARGETS, CALIBRATION STAGE & ACCEPTANCE PROTOCOL

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 PROVISIONAL ACCEPTANCE TARGETS                                    │
├────┬─────────────────────────────┬───────────────────────────┬────────────────────────────────────┤
│ #  │ Metric                      │ Provisional Pass Target   │ Ideal Architectural Target         │
├────┼─────────────────────────────┼───────────────────────────┼────────────────────────────────────┤
│ T1 │ Detail Index (DCI)          │ DCI >= 0.985              │ DCI >= 0.995                       │
│ T2 │ Gradient Orientation (GOE)  │ GOE <= 5.0 degrees        │ GOE <= 1.5 degrees                 │
│ T3 │ Halo Width (HWA)            │ HWA <= 2.0 pixels         │ HWA <= 0.5 pixels (imperceptible)  │
│ T4 │ True Noise Amp (NAF)        │ NAF <= 4.0x (P1), <=8x(P2)│ NAF <= 2.5x                        │
│ T5 │ Circular Hue Error          │ Delta h_circ <= 2.0 deg   │ Delta h_circ <= 0.5 deg            │
│ T6 │ Negative Pixels (N_neg)     │ N_neg = 0                 │ N_neg = 0                          │
│ T7 │ 4K Latency (p95, CPU Ref)   │ Latency <= 250 ms         │ Latency <= 80 ms                   │
└────┴─────────────────────────────┴───────────────────────────┴────────────────────────────────────┘
```

### Calibration Stage (Stage 0):
Before evaluating stress profiles, run the **Identity Lighting Baseline** ($R(p) = 1.0$ everywhere) across all paradigms. Measure the intrinsic distortion floor of each decomposition. Any target threshold higher than the baseline calibration noise is adjusted prior to running rejection decisions.

---

## 7. EXECUTION PLAN

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   SPIKE 1 IMPLEMENTATION PHASES                                   │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 0: CALIBRATION & TEST HARNESS SETUP                                                         │
│ • Generate procedural synthetic patterns (syn_step_edge, syn_siemens_star, syn_noise_pair,        │
│   syn_macbeth). Load verified photographic assets. Run identity baseline (R=1.0).                 │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 1: CORE DECOMPOSITION & RECONSTRUCTION ENGINES                                              │
│ • Implement Paradigms A, B, C (with N_neg logging), D, E (E.1 Guided vs E.2 Screened Poisson).    │
│ • Implement Color Methods C1, C2, C3 (3-stage: L-compression -> guard -> bisection).              │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 2: METRIC ENGINE & VISUAL CONTACT SHEET GENERATOR                                           │
│ • Implement DCI, Delta x_edge, TCR_k, GOE_unsigned, HOA+/-, HWA, ETW, NAF, V_excursion,           │
│   Delta C_loss, Delta h_circ, and p50/p95 timing.                                                 │
│ • Generate high-resolution side-by-side zoom contact sheets of edges, fabric, and noise.          │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 3: EXECUTION OF 60-CONFIG MATRIX & HIGHLIGHT ABLATION                                       │
│ • Run full matrix. Record structured JSON and CSV results.                                        │
│ • Run Highlight Protection ablation (H+ vs H-) on top 2 performing paradigms.                     │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 4: EVALUATION REPORT & ARCHITECTURAL VERDICT                                                │
│ • Publish empirical findings against Hypotheses H1–H4.                                            │
│ • Decisive recommendation: Proceed to Spike 2, Redesign, or Reject.                               │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---
*Specification v1.2 completed. Ready for review.*
