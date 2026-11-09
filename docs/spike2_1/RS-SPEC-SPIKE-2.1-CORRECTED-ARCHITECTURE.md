# RELIGHT STUDIO — SPIKE 2.1 ARCHITECTURE SPECIFICATION
## Physically Decoupled Light Transport, Compositing Contract & Geometric Uncertainty
**Document Reference:** `RS-SPEC-SPIKE-2.1-CORRECTED-ARCHITECTURE.md`  
**Supercedes:** `docs/superpowers/specs/2026-11-09-spike-2-shadow-transport-design.md`  
**Status:** SPECIFICATION APPROVED FOR SPIKE 2.1 IMPLEMENTATION  
**Author:** Principal Computational Photography Architect & Rendering Systems Engineer  

---

## 1. Architectural Scope & Core Principles

Spike 2.1 corrects the fundamental physical conflations and coordinate ambiguities identified during the forensic audit of Spike 2.

### 1.1 The Central Physical Principle
Light transport in photographic relighting must separate **indirect ambient illumination** from **direct directional radiance**:
1. **Ambient Occlusion ($A_{\text{ambient}}$)** modulates only hemispherical indirect ambient light. It must **never** multiply direct directional radiance. Direct key lights illuminate cavities if the light ray has line-of-sight.
2. **Surface Orientation ($D_{\text{diffuse}}$)** is a local radiometric cosine response ($\mathbf{n} \cdot \mathbf{L}$). It is **not** a visibility term.
3. **Direct Light Visibility ($V_{\text{direct}}$)** is a binary or penumbral occlusion field indicating whether photons along $\mathbf{L}$ are blocked by an occluder.
4. **Contact Grounding ($C_{\text{contact}}$)** represents near-interface obscuration where caster meets receiver, governing both local ambient deprivation and near-field contact shadow onset.

---

## 2. Seven Decoupled Physical Lighting Terms

| Term | Mathematical Symbol | Physical Meaning | Valid Range | Input Dependencies | Compositing Role |
|:---|:---:|:---|:---:|:---|:---|
| **Direct Light Visibility** | $V_{\text{direct}}(\mathbf{x}, \mathbf{L})$ | Fraction of direct key light reaching $\mathbf{x}$ along vector $\mathbf{L}$. | $[0.0, 1.0]$ | $V_{\text{self}}$, $V_{\text{cast}}$, $C_{\text{contact}}$ | Modulates direct key light. |
| **Ambient Visibility** | $A_{\text{ambient}}(\mathbf{x})$ | Fraction of hemispherical diffuse ambient light reaching $\mathbf{x}$. Omnidirectional, light-invariant. | $[0.15, 1.0]$ | Depth $Z$, Normals $\mathbf{n}$, Radius $r_{\text{ao}}$ | Modulates indirect ambient fill floor only. |
| **Contact Grounding** | $C_{\text{contact}}(\mathbf{x}, \mathbf{L})$ | Local geometric obscuration at zero-distance caster-receiver seam ($r \le 25\text{ px}$). | $[0.10, 1.0]$ | Depth $Z$, Normals $\mathbf{n}$, Contact Seam | Eliminates light leaks under soles and pedestals. |
| **Diffuse Orientation** | $D_{\text{diffuse}}(\mathbf{x}, \mathbf{L})$ | Local Lambertian surface response to light angle: $\max(0, \mathbf{n} \cdot \mathbf{L})$ with Hermite terminator taper. | $[0.0, 1.0]$ | Normals $\mathbf{n}$, Light direction $\mathbf{L}$ | Modulates direct diffuse radiance. |
| **Self-Occlusion** | $V_{\text{self}}(\mathbf{x}, \mathbf{L})$ | Ray-marched binary/soft occlusion of foreground geometry by other parts of the foreground. | $[0.0, 1.0]$ | Depth $Z$, Light direction $\mathbf{L}$ | Prevents light reaching recessed surfaces facing $\mathbf{L}$. |
| **Cast Shadow Visibility** | $V_{\text{cast}}(\mathbf{x}, \mathbf{L})$ | Receiver proxy projection of foreground silhouette with distance-dependent penumbra $\sigma(d)$. | $[0.15, 1.0]$ | Silhouette $\Omega_{\text{fg}}$, Light $\mathbf{L}$, Receiver Plane $\Pi$ | Projects long-range shadow onto background/floor. |
| **Geometric Confidence** | $U_{\text{geometry}}(\mathbf{x})$ | Spatial confidence field in depth and normal estimates ($1.0 = \text{certain}$, $0.0 = \text{unknown/cliff}$). | $[0.0, 1.0]$ | Depth gradient $\|\nabla Z\|$, Boundary ring $\partial \Omega$ | Dampens screen-space effects at depth cliffs. |

---

## 3. Mathematical Definitions of Transport Components

### 3.1 Ambient Occlusion ($A_{\text{ambient}}$)
Horizon-Based Ambient Occlusion (HBAO) computes horizon angle $\theta_h$ across $N_{\text{dirs}}$ radial directions in screen space:
$$\sin(\theta_h) = \max_{r \in [r_{\text{min}}, r_{\text{ao}}]} \left( \frac{Z(\mathbf{x}) - Z(\mathbf{x} + r \mathbf{u}_d)}{r} \cdot W_{\text{falloff}}(r) \right)$$
where $W_{\text{falloff}}(r) = \max\left(0, 1 - (r / r_{\text{ao}})^2\right)$.
$$A_{\text{ambient}}(\mathbf{x}) = 1.0 - \kappa_{\text{ao}} \cdot \frac{1}{N_{\text{dirs}}} \sum_{d=1}^{N_{\text{dirs}}} \text{clamp}(\sin(\theta_h), 0, 1)$$
where $\kappa_{\text{ao}} = 0.85$, clamping $A_{\text{ambient}} \in [0.15, 1.0]$.

### 3.2 Contact Grounding ($C_{\text{contact}}$)
Bounded screen-space depth raymarching along projected light direction $\mathbf{u}_L = (L_x, -L_y) / \|(L_x, -L_y)\|$:
For step $s \in [1, r_{\text{contact}}]$ with $r_{\text{contact}} = 25\text{ px}$:
$$\Delta Z(s) = \left(Z(\mathbf{x}) - s \cdot \frac{L_z}{\|\mathbf{u}_L\|} \cdot \delta_z\right) - Z(\mathbf{x} + s \mathbf{u}_L)$$
$$O_{\text{contact}}(\mathbf{x}) = \max_{s} \left( \mathbb{I}\left( \tau_{\text{min}} < \Delta Z(s) < \tau_{\text{max}} \right) \cdot e^{-s / \lambda_c} \right) \cdot U_{\text{geometry}}(\mathbf{x})$$
$$C_{\text{contact}}(\mathbf{x}) = 1.0 - \kappa_c \cdot O_{\text{contact}}(\mathbf{x})$$
where $\tau_{\text{min}} = 0.002$, $\tau_{\text{max}} = 0.15$, $\lambda_c = 10.0\text{ px}$, $\kappa_c = 0.90$.

### 3.3 Diffuse Orientation ($D_{\text{diffuse}}$)
$$\cos\theta = \mathbf{n}(\mathbf{x}) \cdot \mathbf{L}$$
$$D_{\text{diffuse}}(\mathbf{x}) = \text{smoothstep}(-\epsilon_{\text{taper}}, \epsilon_{\text{taper}}, \cos\theta) \cdot \max(0, \cos\theta)$$
where $\epsilon_{\text{taper}} = 0.05$ eliminates staircased shadow terminator ridges on coarse normal maps.

### 3.4 Foreground Self-Occlusion ($V_{\text{self}}$)
Raymarching along $-\mathbf{L}$ across foreground pixels only:
For step $s \in [2, r_{\text{self}}]$ with $r_{\text{self}} = 60\text{ px}$:
$$\text{Hit}(s) = \mathbb{I}\left( Z(\mathbf{x}) - s \cdot \frac{L_z}{\|\mathbf{u}_L\|} \cdot \delta_z < Z(\mathbf{x} - s \mathbf{u}_L) - \tau_{\text{bias}} \right)$$
$$V_{\text{self}}(\mathbf{x}) = 1.0 - \kappa_s \cdot \max_s (\text{Hit}(s))$$
where $\tau_{\text{bias}} = 0.005$ prevents self-acne.

### 3.5 Distant Cast Shadowing ($V_{\text{cast}}$)
Analytical projection of foreground silhouette $\Omega_{\text{fg}}$ onto planar receiver proxy $\Pi_{\text{receiver}}$:
For each pixel $\mathbf{p} \in \Omega_{\text{fg}}$ at elevation $h(\mathbf{p}) = \max(0, y_{\text{receiver}} - p_y)$:
$$\mathbf{p}_{\text{proj}} = \left( p_x + h(\mathbf{p}) \cdot \frac{L_x}{\max(L_y, 0.15)}, \; y_{\text{receiver}} + h(\mathbf{p}) \cdot \frac{L_z}{\max(L_y, 0.15)} \cdot \alpha_z \right)$$
Accumulate footprint $F(\mathbf{x}) = \sum \delta(\mathbf{x} - \mathbf{p}_{\text{proj}})$, close single-pixel raster gaps via morphological structuring element $K_{5 \times 5}$.
Distance-dependent penumbra width:
$$d_{\text{cast}}(\mathbf{x}) = \frac{h_{\text{mean}}}{\max(L_y, 0.15)}$$
$$\sigma_{\text{penumbra}}(\mathbf{x}) = \max(\sigma_{\text{min}}, \; d_{\text{cast}}(\mathbf{x}) \cdot \omega_{\text{source}})$$
where $\sigma_{\text{min}} = 2.0\text{ px}$, $\omega_{\text{source}} = 0.08$.
$$V_{\text{cast}}(\mathbf{x}) = 1.0 - 0.85 \cdot (F * G_{\sigma_{\text{penumbra}}})(\mathbf{x}) \quad \text{for } \mathbf{x} \notin \Omega_{\text{fg}}$$

### 3.6 Geometric Confidence ($U_{\text{geometry}}$)
Normalized depth gradient:
$$g_Z(\mathbf{x}) = \frac{1}{8} \sqrt{\left(\text{Sobel}_x(Z)\right)^2 + \left(\text{Sobel}_y(Z)\right)^2}$$
$$C_{\text{cliff}}(\mathbf{x}) = g_Z(\mathbf{x}) > \tau_{\text{cliff}} \cdot \text{range}(Z)$$
where $\tau_{\text{cliff}} = 0.04$.
$$U_{\text{geometry}}(\mathbf{x}) = 1.0 - \text{dilate}(C_{\text{cliff}}(\mathbf{x}), K_{3 \times 3})$$
At depth cliffs, $U_{\text{geometry}} = 0$, suppressing screen-space raymarching and eliminating silhouette tears.

---

## 4. Physically Defensible Compositing Contract

The central flaw of Spike 2 was multiplying all components into a single scalar multiplier. Spike 2.1 establishes a strict physical radiance separation.

### 4.1 Radiance Separation Formulation
Let $Y_{\text{orig}}(\mathbf{x})$ be the linear input luminance, decomposed via guided filtering into base $Y_b$ and detail $D$.
The relit luminance is composed of two independent additive components:
$$Y_{\text{relit}}(\mathbf{x}) = Y_{\text{indirect}}(\mathbf{x}) + Y_{\text{direct}}(\mathbf{x})$$

#### 1. Indirect Ambient Radiance:
$$Y_{\text{indirect}}(\mathbf{x}) = Y_b(\mathbf{x}) \cdot R_{\text{ambient}} \cdot A_{\text{ambient}}(\mathbf{x}) \cdot C_{\text{contact}}(\mathbf{x})$$
- $R_{\text{ambient}} \in [0.05, 0.20]$ sets the global fill floor.
- $A_{\text{ambient}}$ darkens crevices and cavities.
- $C_{\text{contact}}$ darkens the immediate contact seam.
- **Critical rule:** $A_{\text{ambient}}$ affects **only** this term.

#### 2. Direct Key-Light Radiance:
$$Y_{\text{direct}}(\mathbf{x}) = Y_b(\mathbf{x}) \cdot (R_{\text{key}} - R_{\text{ambient}}) \cdot D_{\text{diffuse}}(\mathbf{x}, \mathbf{L}) \cdot V_{\text{direct}}(\mathbf{x}, \mathbf{L})$$
where direct visibility $V_{\text{direct}}$ is defined by spatial zone:
- **On Foreground ($\mathbf{x} \in \Omega_{\text{fg}}$):**
  $$V_{\text{direct}}(\mathbf{x}) = V_{\text{self}}(\mathbf{x}, \mathbf{L})$$
- **On Receiver Plane ($\mathbf{x} \notin \Omega_{\text{fg}}$):**
  $$V_{\text{direct}}(\mathbf{x}) = \min\left(V_{\text{cast}}(\mathbf{x}, \mathbf{L}), \; C_{\text{contact}}(\mathbf{x}, \mathbf{L})\right)$$
  (Taking the minimum provides a smooth, physical union between near-field contact shadow and projected far-field penumbra, preventing artificial double-darkening).

### 4.2 Downstream Detail Reconstruction
The effective target lighting ratio is:
$$R_{\text{target}}(\mathbf{x}) = \frac{Y_{\text{relit}}(\mathbf{x})}{\max(Y_b(\mathbf{x}), 10^{-4})}$$
Modulated by highlight protection shoulder:
$$M_{\text{high}} = \text{smoothstep}(0.75, 0.98, Y_{\text{orig}})$$
$$R_{\text{eff}} = (1 - M_{\text{high}}) \cdot R_{\text{target}} + M_{\text{high}} \cdot 1.0$$
Reconstructed via Spike 1 Paradigm E.1 (Guided-Filter Ratio) + Method C3 (Oklab 16-step constant-hue bisection).

---

## 5. Uncertainty-Aware Fallbacks

When single-view monocular evidence is insufficient, Relight Studio must fall back gracefully rather than hallucinating geometry:

1. **Grazing Backlights ($L_z < -0.80$):**
   - Unseen backside geometry cannot be reconstructed.
   - Fallback: Transition $V_{\text{cast}}$ smoothly from directional extrusion to an omnidirectional elliptical contact pool beneath the object base.
2. **Depth Discontinuities ($U_{\text{geometry}} = 0$):**
   - Screen-space raymarching fails across cliffs.
   - Fallback: $C_{\text{contact}} \to 1.0$ at cliff edges; rely strictly on analytical receiver proxy $V_{\text{cast}}$ which is evaluated in receiver coordinate space.
3. **Non-Planar Receivers:**
   - When receiver depth gradient indicates vertical walls or curved surfaces, proxy projection coordinates are warped by receiver depth disparity:
     $$p_{y,\text{proj}} = y_{\text{receiver}} + h(\mathbf{p}) \cdot \frac{L_z}{\max(L_y, 0.15)} \cdot \left(\frac{Z_{\text{receiver}}(\mathbf{x})}{Z_{\text{caster}}}\right)$$

---
*Specification approved for Spike 2.1 implementation and testing.*
