# RS-SPIKE-3C.2 — Diffuse & Specular Energy Accounting
## Two-Scale Photographic Reconstruction & Energy Conservation

**Document ID:** RS-SPIKE-3C.2-04  
**Milestone:** RS-SPIKE-3C.2  
**Author:** Principal Physically Based Rendering Engineer & Computational Photography Researcher  
**Status:** VALIDATED (Two-Scale Linear Energy Accounting Formulated)

---

## 1. Executive Summary

A central challenge in physically based relighting of existing photographs is reconciling microfacet specular reflection with the E.1 Guided-Filter detail preservation pipeline.

In pure diffuse relighting (RS-SPIKE-3C.1), the ratio $\rho = \log(E_{\text{target}} / E_{\text{orig}})$ is regularized using the original photograph as a structural guide. However, microfacet specular highlights produce steep, localized radiant energy peaks that do not exist in the original photograph guide. If added directly inside the log ratio, these peaks violate the local linear model of the Guided Filter, causing specular highlights to smear and form visible edge halos.

This document formalizes the **Two-Scale Physical Energy Decomposition**, which mathematically separates diffuse surface relighting (regularized via E.1) from additive microfacet specular transport (added linearly in radiant energy space). This preserves fine photographic microtexture while rendering optically crisp, unblurred studio reflections.

---

## 2. Radiometric Transport Formulation

For each light $i \in \{1 \dots M\}$ emitting radiance $L_{e, i}$ across area $A_i$ sampled at $S$ stratified points:

### 2.1 Diffuse Surface Irradiance
Diffuse transport represents photons that penetrate the surface interface, undergo multiple internal scatterings, and re-emerge isotropically:
$$\mathbf{E}_{\text{target, diffuse}}(\mathbf{x}) = \sum_{i=1}^M \sum_{s=1}^S \frac{L_{e, i} A_i}{S} \cdot \frac{\cos\theta_{e, i, s} \max(0, \mathbf{n} \cdot \mathbf{l}_{i, s})}{d_{i, s}^2} \cdot (1 - F_{i, s}) \cdot (1 - \text{metallic}) \cdot V_i(\mathbf{x}, \mathbf{y}_s)$$

Where:
- $(1 - F_{i, s})$ accounts for Fresnel transmission into the medium.
- $(1 - \text{metallic})$ accounts for conductor electron absorption (zero diffuse reflection for pure metals).
- $V_i(\mathbf{x}, \mathbf{y}_s) \in \{0, 1\}$ is geometric visibility.

### 2.2 Specular Surface Radiance
Specular transport represents direct microfacet surface reflection:
$$\mathbf{L}_{\text{target, specular}}(\mathbf{x}) = \sum_{i=1}^M \sum_{s=1}^S \frac{L_{e, i} A_i}{S} \cdot \frac{\cos\theta_{e, i, s} \max(0, \mathbf{n} \cdot \mathbf{l}_{i, s})}{d_{i, s}^2} \cdot f_{\text{specular}}(\mathbf{l}_{i, s}, \mathbf{v}) \cdot V_i(\mathbf{x}, \mathbf{y}_s)$$

Where:
- $f_{\text{specular}}(\mathbf{l}, \mathbf{v}) = D(\mathbf{h}, \alpha) \cdot F(\mathbf{v}, \mathbf{h}, F_0) \cdot V(\mathbf{l}, \mathbf{v}, \alpha)$ is the Cook-Torrance BRDF.
- $F_0 = \text{mix}(\text{specular\_f0} \cdot \text{specular\_intensity}, \text{base\_color}, \text{metallic})$.

---

## 3. Failure Mode of Naive Unified Ratio Regularization

Consider the naive combination where total incoming radiance is summed before taking the logarithm:
$$\rho_{\text{naive}}(\mathbf{x}) = \log\left( \frac{\mathbf{E}_{\text{target, diffuse}} + \pi \mathbf{L}_{\text{target, specular}} + \epsilon}{\mathbf{E}_{\text{orig, diffuse}} + \pi \mathbf{L}_{\text{orig, specular}} + \epsilon} \right)$$

When the Guided Filter is applied:
$$\hat{\rho} = \text{GuidedFilter}(\rho_{\text{naive}}, I_{\text{guide}}, r=16, \epsilon_{\text{gf}}=0.01)$$

The Guided Filter assumes that within every local window $\omega_k$, the output is a linear transform of the guide:
$$\hat{\rho}_i = a_k I_i + b_k, \quad \forall i \in \omega_k$$

Where the target contains a sharp specular glint of a softbox that does **not** exist in $I_{\text{guide}}$, $a_k$ and $b_k$ cannot fit both the sharp glint and the underlying texture. The filter minimizes $L_2$ error by smoothing out the specular peak across the radius $r$, producing:
1. **Highlight Smear:** The sharp specular reflection of the softbox is blurred into an amorphous patch.
2. **Edge Halos:** Negative overshoot at highlight borders creates dark rings around reflections.

---

## 4. The Two-Scale Physical Energy Decomposition

To solve this, we decouple diffuse microtexture modulation from additive specular reflection:

```
                                      Original Photograph I_orig
                                                  |
                    +-----------------------------+-----------------------------+
                    |                                                           |
                    v                                                           v
       [ Diffuse Ratio Channel ]                                   [ Specular Radiance Channel ]
                    |                                                           |
  rho_diffuse = log(E_target,diff / E_orig,diff)                Delta_L_spec = (L_target,spec - L_orig,spec)
                    |                                                           |
       Guided Filter against I_orig                                     Linear Radiant Energy
                    |                                                           |
  I_diffuse_relit = I_orig * exp(rho_diffuse)                                   |
                    |                                                           |
                    +-----------------------------+-----------------------------+
                                                  |
                                                  v
                              L_composite = I_diffuse_relit + Delta_L_spec
                                                  |
                                                  v
                                      C3 Oklab Chroma Compression
                                                  |
                                                  v
                                      Final Gamut-Safe Image
```

### 4.1 Mathematical Formulation
1. **Diffuse Ratio Computation:**
   $$\rho_{\text{diffuse}}(\mathbf{x}) = \log\left( \frac{\mathbf{E}_{\text{target, diffuse}}(\mathbf{x}) \cdot \text{exposure} + \text{ambient\_fill}}{\mathbf{E}_{\text{orig, diffuse}}(\mathbf{x}) \cdot \text{exposure} + \text{ambient\_fill}} \right)$$

2. **E.1 Detail Preservation Regularization:**
   $$\hat{\rho}_{\text{diffuse}} = \text{GuidedFilter}\left(\rho_{\text{diffuse}}, I_{\text{orig}}, r=16, \epsilon_{\text{gf}}=0.01\right)$$
   $$\mathbf{L}_{\text{diffuse, relit}}(\mathbf{x}) = I_{\text{orig}}(\mathbf{x}) \cdot \exp\left( \hat{\rho}_{\text{diffuse}}(\mathbf{x}) \right)$$

3. **Additive Specular Injection:**
   $$\Delta \mathbf{L}_{\text{specular}}(\mathbf{x}) = \left( \mathbf{L}_{\text{target, specular}}(\mathbf{x}) - \mathbf{L}_{\text{orig, specular}}(\mathbf{x}) \right) \cdot \text{exposure}$$
   $$\mathbf{L}_{\text{relit}}(\mathbf{x}) = \mathbf{L}_{\text{diffuse, relit}}(\mathbf{x}) + \Delta \mathbf{L}_{\text{specular}}(\mathbf{x})$$

---

## 5. Key Physical Guarantees

### 5.1 Bitwise Identity Under Inactive Specular
When `enable_specular = False`:
$$\mathbf{L}_{\text{target, specular}} \equiv 0, \quad \mathbf{L}_{\text{orig, specular}} \equiv 0 \implies \Delta \mathbf{L}_{\text{specular}} = 0$$
$$\mathbf{L}_{\text{relit}}(\mathbf{x}) \equiv \mathbf{L}_{\text{diffuse, relit}}(\mathbf{x})$$
The pipeline collapses bitwise to the validated RS-SPIKE-3C.1 multi-light diffuse engine with zero overhead.

### 5.2 Baseline Identity
If the target studio lights match the estimated original lighting:
$$\mathbf{E}_{\text{target, diffuse}} = \mathbf{E}_{\text{orig, diffuse}} \implies \rho_{\text{diffuse}} = 0 \implies \mathbf{L}_{\text{diffuse, relit}} = I_{\text{orig}}$$
$$\mathbf{L}_{\text{target, specular}} = \mathbf{L}_{\text{orig, specular}} \implies \Delta \mathbf{L}_{\text{specular}} = 0$$
$$\mathbf{L}_{\text{relit}} \equiv I_{\text{orig}}$$
The original photograph is reconstructed with bitwise zero error ($0.0000000000$).

### 5.3 Gamut Safety via C3 Oklab Chroma Compression
High-intensity specular highlights naturally cause values in $\mathbf{L}_{\text{relit}}$ to exceed $1.0$.
Rather than hard clipping in RGB (which causes harsh hue skewing and cyan/magenta banding), $\mathbf{L}_{\text{relit}}$ is transformed into Oklab perceptual color space $(L, a, b)$. If luminance $L > 1.0$, chroma is compressed towards the neutral axis while preserving constant perceptual hue:
$$C_{\text{compressed}} = C \cdot \min\left(1.0, \frac{1.0 - L_{\text{clamped}}}{L - L_{\text{clamped}}}\right)$$
This produces natural, photographic specular highlights that roll smoothly into white highlights without edge discoloration.

---

## 6. Verification Status

The two-scale energy decomposition prevents highlight blurring and guarantees backward compatibility.

Phase 4 is complete. Authorized to proceed to **Phase 5: CPU Reference & Native Metal Implementation**.
