# RELIGHT STUDIO — SPIKE 2.2 ARCHITECTURE SPECIFICATION
## Physically Decoupled Radiance Formulation, Transport Decomposition & Radiometric Linearity
**Document Reference:** `RS-SPEC-SPIKE-2.2-ARCHITECTURE.md`  
**Supercedes:** `docs/spike2_1/RS-SPEC-SPIKE-2.1-CORRECTED-ARCHITECTURE.md`  
**Milestone:** RS-SPIKE-2.2 — Shadow Transport Corrective Validation  
**Date:** 2026-11-09  
**Status:** COMPLETE & APPROVED FOR SPIKE 2.2 IMPLEMENTATION  
**Author:** Principal Computational Photography Architect & PBR Rendering Engineer  

---

## 1. Architectural Scope & Core Physical Principles

Spike 2.2 establishes an uncompromising physical audit of the light transport formulation, correcting the double-counting of contact grounding and defining strict radiometric units across all terms.

### 1.1 The Seven Decoupled Light Transport Terms

| Term | Symbol | Physical Definition | Mathematical Domain | Radiometric Domain | Role in Transport Equation |
|:---|:---:|:---|:---:|:---:|:---|
| **Ambient Visibility** | $A_{\text{ambient}}(\mathbf{x})$ | Fraction of indirect hemispherical ambient irradiance reaching surface point $\mathbf{x}$. Omnidirectional, light-direction invariant. | $[0.15, 1.00]$ | Unitless transmittance $\in [0, 1]$ | Modulates indirect ambient fill floor ONLY. |
| **Contact Grounding** | $C_{\text{contact}}(\mathbf{x}, \mathbf{L})$ | Directional direct occlusion in near-field zone ($r \le 25\text{ px}$) between caster base and receiver plane. | $[0.10, 1.00]$ | Unitless direct visibility $\in [0, 1]$ | Contributes to direct key-light visibility $V_{\text{direct}}$ on receiver. |
| **Diffuse Orientation** | $D_{\text{diffuse}}(\mathbf{x}, \mathbf{L})$ | Local Lambertian cosine radiometric response to directional key light with Hermite terminator taper. | $[0.00, 1.00]$ | Normalized cosine response $\max(0, \mathbf{n} \cdot \mathbf{L})$ | Modulates direct key-light diffuse irradiance. |
| **Self-Occlusion** | $V_{\text{self}}(\mathbf{x}, \mathbf{L})$ | Screen-space binary/soft line-of-sight occlusion of foreground surfaces by foreground protrusions along $\mathbf{L}$. | $[0.00, 1.00]$ | Unitless direct visibility $\in [0, 1]$ | Sets $V_{\text{direct}}$ on foreground surfaces $\mathbf{x} \in \Omega_{\text{fg}}$. |
| **Cast Shadow Visibility** | $V_{\text{cast}}(\mathbf{x}, \mathbf{L})$ | Receiver proxy projection of foreground silhouette with 3D distance-dependent penumbral blur $\sigma(d)$. | $[0.15, 1.00]$ | Unitless direct visibility $\in [0, 1]$ | Sets far-field direct visibility on receiver $\mathbf{x} \in \Pi_{\text{receiver}}$. |
| **Direct Light Visibility** | $V_{\text{direct}}(\mathbf{x}, \mathbf{L})$ | Total directional fraction of direct key light reaching surface $\mathbf{x}$. Unified visibility field. | $[0.00, 1.00]$ | Unitless direct visibility $\in [0, 1]$ | Modulates direct key-light radiance on all surfaces. |
| **Geometric Confidence** | $U_{\text{geometry}}(\mathbf{x})$ | Independent spatial confidence field ($1.0 = \text{continuous}$, $0.0 = \text{cliff/occlusion boundary}$). | $[0.00, 1.00]$ | Unitless confidence weight $\in [0, 1]$ | Suppresses screen-space raymarching at depth boundaries. |

---

## 2. Audit of the Additive Radiance Compositing Contract

### 2.1 The Historical Flaw: Double-Counting of Contact Grounding
In Spike 2.1, the compositing equation was formulated as:
$$Y_{\text{relit}} = \underbrace{Y_b \cdot R_{\text{ambient}} \cdot A_{\text{ambient}} \cdot C_{\text{contact}}}_{Y_{\text{indirect}}} + \underbrace{Y_b \cdot (R_{\text{key}} - R_{\text{ambient}}) \cdot D_{\text{diffuse}} \cdot V_{\text{direct}}}_{Y_{\text{direct}}}$$
with $V_{\text{direct}} = \min(V_{\text{cast}}, C_{\text{contact}})$ on the receiver plane.

**The Physical Violation:**
1. $C_{\text{contact}}(\mathbf{x}, \mathbf{L})$ is explicitly computed along the **directional light vector $\mathbf{L}$** (marching along $\mathbf{u}_L$ towards the light). Therefore, it is a **directional direct-occlusion term**.
2. Ambient illumination is **omnidirectional** hemispherical scatter. Multiplying a directional vector-dependent term ($C_{\text{contact}}$) into indirect ambient radiance is physically indefensible.
3. Furthermore, on the receiver plane, $C_{\text{contact}}$ was multiplied into $Y_{\text{indirect}}$ AND took the minimum in $V_{\text{direct}}$ for $Y_{\text{direct}}$, causing double-darkening at the contact seam.
4. Hemispherical cavity obscuration is ALREADY the physical definition of **Ambient Occlusion ($A_{\text{ambient}}$)**. Multi-scale HBAO naturally darkens crevices under ambient light.

### 2.2 Corrected Radiance Separation Formulation
All calculations operate in **Linear Photometric Luminance** ($Y \in [0, \infty)$, non-gamma-encoded, CIE 1931 $Y = 0.2126 R + 0.7152 G + 0.0722 B$).

$$Y_{\text{relit}}(\mathbf{x}) = Y_{\text{indirect}}(\mathbf{x}) + Y_{\text{direct}}(\mathbf{x})$$

#### 1. Indirect Ambient Radiance ($Y_{\text{indirect}}$):
$$Y_{\text{indirect}}(\mathbf{x}) = Y_b(\mathbf{x}) \cdot R_{\text{ambient}} \cdot A_{\text{ambient}}(\mathbf{x})$$
- $Y_b(\mathbf{x}) \in [0.0, 1.0]$: Base luminance extracted via guided filtering of original linear input.
- $R_{\text{ambient}} \in [0.05, 0.25]$: Global ambient fill floor ratio (default $0.15$).
- $A_{\text{ambient}}(\mathbf{x}) \in [0.15, 1.00]$: Multi-scale HBAO modulating ambient light ONLY.
- **Strict Rule:** $C_{\text{contact}}$ does **not** modulate $Y_{\text{indirect}}$.

#### 2. Direct Key-Light Radiance ($Y_{\text{direct}}$):
$$Y_{\text{direct}}(\mathbf{x}) = Y_b(\mathbf{x}) \cdot (R_{\text{key}} - R_{\text{ambient}}) \cdot D_{\text{diffuse}}(\mathbf{x}, \mathbf{L}) \cdot V_{\text{direct}}(\mathbf{x}, \mathbf{L})$$
- $R_{\text{key}} \ge R_{\text{ambient}}$: Direct key light intensity ratio (default $1.0$).
- $D_{\text{diffuse}}(\mathbf{x}, \mathbf{L}) \in [0.0, 1.0]$: Hermite-tapered surface cosine response:
  $$D_{\text{diffuse}}(\mathbf{x}, \mathbf{L}) = \text{HermiteTaper}(\mathbf{n}(\mathbf{x}) \cdot \mathbf{L})$$
- $V_{\text{direct}}(\mathbf{x}, \mathbf{L}) \in [0.0, 1.0]$: Unified direct visibility:
  - **On Foreground ($\mathbf{x} \in \Omega_{\text{fg}}$):**
    $$V_{\text{direct}}(\mathbf{x}) = V_{\text{self}}(\mathbf{x}, \mathbf{L})$$
  - **On Receiver Plane ($\mathbf{x} \in \Pi_{\text{receiver}}$):**
    $$V_{\text{direct}}(\mathbf{x}) = \min\left(V_{\text{cast}}(\mathbf{x}, \mathbf{L}), \; C_{\text{contact}}(\mathbf{x}, \mathbf{L})\right)$$
    Taking the minimum forms a smooth geometric union between near-contact grounding and projected far-field penumbra without double-counting.

---

## 3. Mathematical Details of Transport Components

### 3.1 Multi-Scale Horizon-Based Ambient Occlusion ($A_{\text{ambient}}$)
To properly ground contact seams under ambient light without heuristic multipliers, $A_{\text{ambient}}$ evaluates two spatial scales:
1. **Fine Contact Horizon ($r_{\text{fine}} = 6\text{ px}$):** Resolves tight creases, sole treads, and contact crevices.
2. **Coarse Ambient Horizon ($r_{\text{coarse}} = 24\text{ px}$):** Resolves broad geometric self-occlusion.

Across $N_{\text{dirs}} = 8$ screen directions:
$$\sin(\theta_{h, d}) = \max_{r \in [2, r_{\text{ao}}]} \left( \frac{Z(\mathbf{x}) - Z(\mathbf{x} + r \mathbf{u}_d)}{r \cdot \Delta z_{\text{scale}}} \cdot \left(1 - \frac{r^2}{r_{\text{ao}}^2}\right) \right)$$
$$A_{\text{ambient}}(\mathbf{x}) = 1.0 - 0.85 \cdot \left( 0.40 \cdot \overline{\sin(\theta_{h,\text{fine}})} + 0.60 \cdot \overline{\sin(\theta_{h,\text{coarse}})} \right)$$
Clamped to $[0.15, 1.00]$.

### 3.2 Directional Contact Grounding ($C_{\text{contact}}$)
Bounded screen-space depth raymarching along projected light vector $\mathbf{u}_L = (-L_x, L_y) / \|(-L_x, L_y)\|$:
- Search radius: $r_{\text{contact}} = 25\text{ px}$.
- Evaluated on receiver plane near caster base.
- Occlusion accumulation weighted by quadratic distance falloff $(1 - s/r_{\text{contact}})^2$ and modulated by caster geometric confidence $U_{\text{geom}}$.
- At verified contact points ($\text{dist} \le 2\text{ px}$, $\Delta Z \le \epsilon_Z$), $C_{\text{contact}}$ reaches maximum darkening ($0.10$).

### 3.3 Perspective-Corrected 2.5D Proxy Projection ($V_{\text{cast}}$)
To address the $SDE$ and $\text{IoU}$ divergence identified in Investigation C:
Rather than crude 2D affine shear, $V_{\text{cast}}$ unprojects foreground pixels into camera-space 3D coordinates:
$$\mathbf{P}_{\text{cam}}(x, y) = \left( \frac{x - c_x}{f_x} Z(x, y), \; \frac{y - c_y}{f_y} Z(x, y), \; Z(x, y) \right)$$
1. Rays are cast from $\mathbf{P}_{\text{cam}}$ along light vector $-\mathbf{L}$.
2. The intersection with the receiver plane $\mathbf{n}_{\text{rec}} \cdot \mathbf{X} + d_{\text{rec}} = 0$ is computed analytically:
   $$t_{\text{rec}} = -\frac{\mathbf{n}_{\text{rec}} \cdot \mathbf{P}_{\text{cam}} + d_{\text{rec}}}{\mathbf{n}_{\text{rec}} \cdot (-\mathbf{L})}$$
   $$\mathbf{P}_{\text{floor}} = \mathbf{P}_{\text{cam}} - t_{\text{rec}} \mathbf{L}$$
3. $\mathbf{P}_{\text{floor}}$ is re-projected back to screen coordinates $(u_{\text{proj}}, v_{\text{proj}})$.
4. Footprint is rasterized and filtered with distance-dependent penumbra $\sigma(d) = \max(\sigma_{\text{min}}, d_{\text{cast}} \cdot \omega_{\text{source}})$.
This eliminates the perspective foreshortening error that degraded Spike 2.1.

### 3.4 Independent Geometric Confidence ($U_{\text{geometry}}$)
$U_{\text{geometry}}(\mathbf{x}) \in [0, 1]$ represents confidence in local depth and normal estimates:
$$U_{\text{geometry}}(\mathbf{x}) = \exp\left( -\frac{\|\nabla Z(\mathbf{x})\|^2}{2 \sigma_Z^2} \right) \cdot \max\left(0, \mathbf{n}(\mathbf{x}) \cdot \mathbf{v}_{\text{cam}}\right)$$
- Drops to $0.0$ at depth cliffs ($\|\nabla Z\| \gg \sigma_Z$) and at grazing silhouettes ($\mathbf{n} \cdot \mathbf{v}_{\text{cam}} \to 0$).
- When $U_{\text{geometry}} < 0.5$, screen-space raymarching is suppressed, eliminating silhouette tearing.

---

## 4. Radiometric Linearity & Detail Reconstruction

1. All transport components ($A_{\text{ambient}}$, $C_{\text{contact}}$, $D_{\text{diffuse}}$, $V_{\text{direct}}$) are evaluated in linear light.
2. Shading ratio target:
   $$R_{\text{target}}(\mathbf{x}) = \frac{Y_{\text{relit}}(\mathbf{x})}{\max(Y_b(\mathbf{x}), 10^{-4})}$$
3. Regularized via Spike 1 Paradigm E.1 (Guided-Filter Ratio Regularization) with parameter $\epsilon = 0.01$, preserving high-frequency surface detail.
4. Gamut mapped via Spike 1 Method C3 (Oklab 16-step constant-hue bisection), ensuring zero out-of-gamut clipping and zero perceptual hue distortion.

---
*Specification certified for Spike 2.2 implementation.*

