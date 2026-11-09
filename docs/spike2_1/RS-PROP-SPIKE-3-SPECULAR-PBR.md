# RELIGHT STUDIO — SPIKE 3 RESEARCH PROPOSAL
## Physically Based Specular Transport, Microfacet BRDFs & Luxury Goods Materials
**Document Reference:** `RS-PROP-SPIKE-3-SPECULAR-PBR.md`  
**Milestone Target:** RS-SPIKE-3.0 — Specular PBR & Material Decomposition  
**Author:** Principal Computational Photography Architect & Physically Based Rendering Specialist  
**Status:** PROPOSED & READY FOR ARCHITECTURAL REVIEW  

---

## 1. Executive Summary & Problem Motivation

Spikes 1 and 2.1 successfully solved **detail preservation** (Paradigm E.1 + Method C3) and **diffuse shadow transport** (Decoupled 7-term formulation with contact grounding).

However, Relight Studio's current lighting model remains fundamentally **diffuse-dominant**:
$$Y_{\text{relit}} = Y_{\text{indirect}} + Y_{\text{direct}}$$
where direct radiance is governed by the Lambertian cosine law $D_{\text{diffuse}} = \max(0, \mathbf{n} \cdot \mathbf{L})$.

In high-value commercial photography (e.g., luxury timepieces, fine jewelry, cosmetics bottles, patent leather shoes, automotive finishes, polished metals), diffuse reflectance accounts for less than 30% of apparent visual quality. The core value of a virtual studio gaffer lies in **sculpting specular highlights, glints, Fresnel rim glares, and anisotropic reflections**.

Spike 3 addresses this foundational challenge: **Can a single-view computational photography system physically model, reshape, and relocate specular reflections on real luxury objects while preserving original surface engraving and micro-textures?**

---

## 2. Theoretical Mathematical Formulation

Spike 3 expands Relight Studio from a 2-term diffuse engine into a full **Cook-Torrance Microfacet PBR Model**:

### 2.1 The Split-Radiance Transport Equation
Total reflected spectral radiance $L_o(\mathbf{p}, \mathbf{v})$ observed from camera direction $\mathbf{v}$:
$$L_o(\mathbf{p}, \mathbf{v}) = L_{\text{diffuse}}(\mathbf{p}, \mathbf{v}) + L_{\text{specular}}(\mathbf{p}, \mathbf{v})$$

#### 1. Diffuse Term (Spike 2.1 Base):
$$L_{\text{diffuse}}(\mathbf{p}, \mathbf{v}) = (1 - F(\mathbf{v}, \mathbf{h})) \cdot \frac{\boldsymbol{\rho}_d}{\pi} \cdot \left[ E_{\text{ambient}} \cdot A_{\text{ambient}} + E_{\text{key}} \cdot D_{\text{diffuse}} \cdot V_{\text{direct}} \right]$$

#### 2. Specular Microfacet Term (Spike 3 Addition):
$$L_{\text{specular}}(\mathbf{p}, \mathbf{v}) = \frac{D(\mathbf{h}, \alpha) \cdot F(\mathbf{v}, \mathbf{h}, F_0) \cdot G(\mathbf{v}, \mathbf{l}, \alpha)}{4 (\mathbf{n} \cdot \mathbf{v}) (\mathbf{n} \cdot \mathbf{l})} \cdot E_{\text{key}} \cdot V_{\text{direct}}$$
where $\mathbf{h} = \frac{\mathbf{v} + \mathbf{l}}{\|\mathbf{v} + \mathbf{l}\|}$ is the half-vector between view vector $\mathbf{v}$ and light vector $\mathbf{l}$.

### 2.2 Microfacet Component Functions
1. **GGX / Trowbridge-Reitz Normal Distribution Function ($D$):**
   $$D_{\text{GGX}}(\mathbf{h}, \alpha) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}$$
   where $\alpha = \text{Roughness}^2$.
2. **Schlick-Smith Geometric Shadowing-Masking Function ($G$):**
   $$G(\mathbf{v}, \mathbf{l}, \alpha) = G_1(\mathbf{v}, \alpha) \cdot G_1(\mathbf{l}, \alpha)$$
   $$G_1(\mathbf{w}, \alpha) = \frac{2 (\mathbf{n} \cdot \mathbf{w})}{(\mathbf{n} \cdot \mathbf{w}) + \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{w})^2}}$$
3. **Fresnel-Schlick Approximation ($F$):**
   $$F(\mathbf{v}, \mathbf{h}, F_0) = F_0 + (1 - F_0) (1 - (\mathbf{v} \cdot \mathbf{h}))^5$$
   where $F_0 \approx 0.04$ for dielectrics (glass, plastic, leather) and $F_0 = \text{Albedo}$ for conductors (gold, platinum, chrome, brass).

---

## 3. Four Core Research Challenges in Spike 3

### Challenge 1: Single-View Material Decomposition
- **Problem:** A single photograph contains entangled diffuse color, specular reflections, and ambient lighting without polarized ground truth.
- **Hypothesis:** Monocular roughness ($\alpha$) and metalness ($M$) can be inferred via guided bilateral decomposition of the photographic luminance gradient combined with high-light mask detection.
- **Approach:** 
  1. Extract existing highlight regions: $M_{\text{spec}} = \text{smoothstep}(\tau_{\text{spec}}, 1.0, Y_{\text{orig}})$.
  2. Estimate material base $F_0$: dielectrics ($F_0 = 0.04$), metals ($F_0 > 0.50$, tinted by base hue).
  3. Predict roughness field $\alpha(\mathbf{x}) \in [0.05, 0.80]$ from local specular falloff width.

### Challenge 2: Specular Highlight Relocation vs. Inpainting
- **Problem:** When virtual lighting moves, the original photograph's highlight must be removed, and a new highlight synthesized at the new reflection angle.
- **Failure Risk:** Removing the original highlight with crude blur creates muddy gray splotches or destroys surface engravings.
- **Approach:** Implement **Specular Inpainting via Shading Ratio Inversion**:
  $$Y_{\text{diffuse\_albedo}}(\mathbf{x}) = \frac{Y_{\text{orig}}(\mathbf{x}) - L_{\text{spec,old}}(\mathbf{x})}{\max(Y_{\text{diffuse\_est}}(\mathbf{x}), 10^{-3})}$$
  The new specular lobe is added on top of the restored albedo, preserving underlying watch dials and jewelry facets.

### Challenge 3: Clearcoat & Dual-Lobe Reflection (Luxury Leather & Lacquer)
- **Problem:** Luxury shoes, handbags, and fine wood feature a dual-layer BRDF: a rough diffuse-pigment substrate covered by a smooth, glossy protective clearcoat.
- **Approach:** Implement a **Dual-Lobe BRDF**:
  $$L_o = (1 - F_{\text{coat}}) L_{\text{substrate}}(\alpha_{\text{base}}) + F_{\text{coat}} L_{\text{coat}}(\alpha_{\text{smooth}})$$
  where $\alpha_{\text{smooth}} \approx 0.08$ (sharp highlight) and $\alpha_{\text{base}} \approx 0.45$ (broad sheen).

### Challenge 4: Extended Studio Area Lights (Softboxes & Beauty Dishes)
- **Problem:** Studio photographers do not use infinitesimal point lights; they use rectangular softboxes, octabanks, and umbrellas with custom diffusion grids. Point-light specular highlights look artificial and pin-like.
- **Approach:** Implement **Linearly Transformed Cosines (LTC)** (Heitz et al., 2016) for real-time polygonal area-light specular integration on GPU.

---

## 4. Proposed Validation Battery & Ground-Truth Test Suite

Spike 3 will be evaluated against an independent ray-traced reference harness rendering exact Cook-Torrance microfacet materials:

### Synthetic Ground-Truth Test Scenes (S_PBR-1 to S_PBR-6):
1. **S_PBR-1: Gold Chronometer Bezel:** Pure conductor ($F_0 = (1.0, 0.78, 0.34)$, $\alpha = 0.08$) testing metallic highlight relocation and anisotropic brush patterns.
2. **S_PBR-2: Polished Diamond / Gemstone:** High-index dielectric ($n = 2.42$, $F_0 = 0.17$, $\alpha = 0.02$) testing internal transmission and total internal reflection glints.
3. **S_PBR-3: Patent Leather Luxury Shoe:** Dual-lobe clearcoat on black leather testing Fresnel grazing rim glare.
4. **S_PBR-4: Frosted Cosmetic Glass Bottle:** Rough dielectric ($\alpha = 0.35$) testing softbox transmission and broad diffuse-specular blend.
5. **S_PBR-5: Brushed Steel Luxury Pen:** Anisotropic GGX microfacet BRDF testing non-circular highlight elongation along the lathe axis.
6. **S_PBR-6: Satin Silk Fabric:** Microfiber sheen model (Velvet/Cloth BRDF) testing backscatter rim illumination.

### Proposed Diagnostic Metrics:
- **SHRE (Specular Highlight Relocation Error):** Centroid error of relocated specular peak against ray-traced reference ($\le 2.0\text{ px}$).
- **SFPR (Specular Falloff Profile Ratio):** Log-radiance cross-sectional slope correlation against GGX NDF ($\ge 0.95$).
- **FGA (Fresnel Grazing Accuracy):** Radiance error at grazing angles $\theta_v \in [75^\circ, 88^\circ]$ ($\le 5\%$).
- **AER (Albedo Extraction Residual):** Error in recovered diffuse albedo after removing original highlight ($\text{SSIM} \ge 0.96$).

---

## 5. Execution Timeline & Resource Plan

- **Phase 1: Microfacet Reference Renderer:** Build `spike3_reference_renderer.py` implementing Cook-Torrance microfacets and LTC area lights (Days 1–2).
- **Phase 2: Monocular Material Estimator:** Implement single-view roughness and metalness estimation (Days 3–4).
- **Phase 3: Specular Relocation Engine:** Build candidate highlight inpainter and synthesizer (Days 5–6).
- **Phase 4: Metal Compute Shader Prototype:** Implement unified PBR shader pass in Metal (Days 7–8).
- **Phase 5: Benchmark & Architecture Decision:** Execute test battery and deliver `RS-DECISION-SPIKE-3.md` (Days 9–10).

---
*Research proposal prepared for Engineering Review & Approval.*
