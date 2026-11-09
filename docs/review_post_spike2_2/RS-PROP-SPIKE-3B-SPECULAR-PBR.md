# RELIGHT STUDIO — MILESTONE PROPOSAL
## RS-SPIKE-3B: Specular PBR, Microfacet Reflection & Material Decomposition

- **Document ID:** RS-PROP-SPIKE-3B-SPECULAR-PBR-v1.0
- **Status:** APPROVED PROPOSAL FOR SEQUENTIAL / PARALLEL TRACK
- **Author:** Principal Optical Systems Researcher & Physically Based Rendering Engineer
- **Date:** 2026-11-09
- **Preceding Milestones:** RS-SPIKE-1 (Detail Preservation), RS-SPIKE-2.2 (Decoupled Additive Radiance)

---

### 1. Executive Summary & Problem Statement

Spike 1 and Spike 2 established diffuse log-ratio re-lighting, ambient occlusion, and contact grounding under an assumed Lambertian reflectance model.
However, real studio commercial photography (e.g. leather footwear, glossy cosmetics bottles, metallic electronics, glazed ceramics, human skin) is heavily defined by **specular highlights, Fresnel reflections, and surface roughness**.

Under the current diffuse-only engine:
1. Moving a virtual light source re-shades diffuse irradiance, but leaves original baked specular reflections static in their captured locations, producing conflicting visual cues ("dead highlights").
2. High-roughness glossy highlights are unmodeled, preventing the synthesis of realistic rim lights, softbox reflections, and metallic sheen.
3. Simply brightening diffuse luminance to simulate highlights blows out surface texture and causes chromatic clipping.

**Milestone Objective:**
Build and validate a **Material-Aware Microfacet Specular PBR Subsystem** that separates the input photograph into diffuse base albedo and specular reflection components, synthesizes new specular highlights driven by virtual light positions and source shapes using the Cook-Torrance / GGX microfacet model, and guarantees photographic detail preservation without identity or texture distortion.

---

### 2. Core Research Questions

1. **RQ-3B.1 (Highlight Separation & Inpainting):** How accurately can baked specular highlights in the original photograph be detected, suppressed, and inpainted into diffuse base albedo without manual user brushing?
2. **RQ-3B.2 (Microfacet Parameter Estimation):** Can lightweight monocular roughness estimation $\alpha(x, y)$ and dielectric/metallic classification $F_0(x, y)$ provide sufficient guidance for convincing GGX highlight synthesis on real commercial products?
3. **RQ-3B.3 (Energy Conservation & Saturation):** Does the additive radiance combination $L_{\text{total}} = L_{\text{diffuse}} + L_{\text{specular}}$ maintain strict physical energy conservation and avoid clipping when mapped through C3 Oklab gamut mapping?
4. **RQ-3B.4 (Area-Light Reflection Shaping):** Can studio area lights (softboxes, strip lights, umbrella reflectors) be accurately modeled as shaped specular reflections rather than point-source delta glints?

---

### 3. Mathematical Foundations

```
                            PHYSICALLY BASED SPECULAR TRANSPORT
                            
                      Light Source (L)           Camera View (V)
                             \                       /
                              \                     /
                               \       Half (H)    /
                                \         |       /
                                 \        |      /
                                  \       |     /
                                   \      |    /
       -----------------------------+-----+---+------------------------------ Surface (N)
                                    \     |
                                     \    |  Microfacet Roughness (\alpha)
                                      \   |  Base Reflectance (F0)
```

#### 3.1 Cook-Torrance Microfacet Specular BRDF
For surface normal $\mathbf{n}$, view direction $\mathbf{v}$, and light incident direction $\mathbf{l}$, the half-angle vector is $\mathbf{h} = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|}$.
The specular BRDF $f_r^s(\mathbf{l}, \mathbf{v})$ is:

$$f_r^s(\mathbf{l}, \mathbf{v}) = \frac{D(\mathbf{h}) \cdot F(\mathbf{v}, \mathbf{h}) \cdot G(\mathbf{l}, \mathbf{v})}{4 \, (\mathbf{n} \cdot \mathbf{l}) \, (\mathbf{n} \cdot \mathbf{v})}$$

1. **GGX / Trowbridge-Reitz Normal Distribution Function $D(\mathbf{h})$:**
   $$D(\mathbf{h}) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}$$
   Where $\alpha = \text{Roughness}^2 \in [0.001, 1.0]$.
2. **Schlick Fresnel Approximation $F(\mathbf{v}, \mathbf{h})$:**
   $$F(\mathbf{v}, \mathbf{h}) = F_0 + (1 - F_0) \left( 1 - \max(0, \mathbf{v} \cdot \mathbf{h}) \right)^5$$
   - Dielectrics (leather, plastic, glass): $F_0 = 0.04$ (monochromatic).
   - Metals (brass, gold, chrome): $F_0 = \text{Albedo}_{\text{linear}}$ (colored Fresnel).
3. **Smith Height-Correlated Shadowing-Masking Term $G(\mathbf{l}, \mathbf{v})$:**
   $$G(\mathbf{l}, \mathbf{v}) = \frac{2 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}{(\mathbf{n} \cdot \mathbf{v}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{l})^2} + (\mathbf{n} \cdot \mathbf{l}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{v})^2}}$$

#### 3.2 Area-Light Specular Approximation (Karis / Representative Point)
Studio photographers rarely use point lights; they use rectangular softboxes.
To model softbox reflections without Monte Carlo noise, we employ Brian Karis's **Representative Point Method**:
The light vector $\mathbf{l}$ is dynamically shifted to the closest point $\mathbf{p}_{\text{rep}}$ on the rectangular light quad to the ideal reflection ray $\mathbf{r} = 2 (\mathbf{n} \cdot \mathbf{v}) \mathbf{n} - \mathbf{v}$, and the roughness $\alpha$ is widened proportionally to the solid angle subtended by the softbox:
$$\alpha_{\text{eff}} = \sqrt{\alpha^2 + \frac{\text{Area}_{\text{softbox}}}{2 \pi d^2}}$$

#### 3.3 Original Highlight Suppression & Inpainting Contract
To prevent duplicate highlights:
1. Detect baked highlights: $M_{\text{spec\_orig}} = \text{SmoothStep}(0.85, 0.98, Y_{\text{orig}}) \cdot [1.0 - \text{Saturation}(I_{\text{orig}})]$.
2. Suppress baked specular component from base albedo:
   $$Y_{\text{base}} = Y_{\text{orig}} \cdot (1.0 - M_{\text{spec\_orig}}) + \text{GuidedInpaint}(Y_{\text{orig}}, M_{\text{spec\_orig}}) \cdot M_{\text{spec\_orig}}$$
3. Synthesize new specular highlight:
   $$L_{\text{relit}} = Y_{\text{base}} \cdot R_{\text{diffuse}} + L_{\text{specular}}(\mathbf{l}_{\text{new}}, \mathbf{v})$$

---

### 4. Experimental Methodology & Test Manifest

Evaluated in `spike3b/` across synthetic ground-truth BRDF spheres and real commercial photography:

| Case ID | Material Type | Roughness ($\alpha$) | F0 / Class | Key Verification Objective |
| :--- | :--- | :---: | :---: | :--- |
| **S_PBR_dielectric_gloss** | Polished Plastic Sphere | $0.05$ | $0.04$ (Dielectric) | Validate GGX peak intensity and tight highlight contour |
| **S_PBR_dielectric_matte** | Rough Rubber / Ceramic | $0.45$ | $0.04$ (Dielectric) | Validate broad specular lobe and smooth falloff |
| **S_PBR_metal_gold** | Anodized Metal Sphere | $0.15$ | $[1.0, 0.77, 0.34]$ | Validate colored Fresnel tinting in highlight |
| **S_PBR_softbox_quad** | Glossy Cylinder | $0.10$ | $0.04$ | Validate rectangular softbox reflection deformation |
| **R1_sneaker_leather** | Real Leather Footwear | $0.20 - 0.50$ | Multi-material | Suppress original flash highlight; synthesize rim reflection |
| **R2_cosmetic_bottle** | Glossy Glass + Metallic Cap | $0.02, 0.15$ | Dual Material | Relocate sharp studio strip-light reflection |

---

### 5. Quantitative Acceptance Gates

| Metric | Target Acceptance Gate | Measurement Protocol |
| :--- | :---: | :--- |
| **Highlight Centroid Repositioning Error** | **$\le 3.0\text{ px}$** | Distance between synthesized highlight center and 3D ground-truth specular peak |
| **Specular Energy Conservation** | **$\le 1.000$** | $\max(L_{\text{diffuse}} + L_{\text{specular}}) \le E_{\text{incident}}$ at all pixels |
| **Albedo Invariance ($DCI_{\text{diffuse}}$)** | **$\ge 0.990$** | Structural similarity of underlying texture in non-specular zones |
| **Baked Highlight Suppression Ratio** | **$\ge 85\%$** | Attenuation of original specular reflection prior to re-lighting |
| **Gamut Mapping Integrity ($C3_{\text{Oklab}}$)** | **$\Delta \theta \le 0.15^\circ$** | Hue preservation when bright highlights compress into destination gamut |
| **GPU Metal Latency (1080p)** | **$\le 3.5\text{ ms}$** | Execution time of complete GGX kernel on Apple Silicon Metal |

---

### 6. Dependencies, Risks & Mitigation Strategies

1. **Risk 1: Monocular Roughness Estimation Error**
   - *Risk:* If roughness is misestimated, highlights may appear unnaturally sharp (plastic-like) or overly diffuse.
   - *Mitigation:* Provide interactive material preset selectors (e.g. "Matte", "Satin", "Patent Leather", "Polished Metal") that override heuristic estimates.
2. **Risk 2: Color Fringing at Gamut Boundaries**
   - *Risk:* Intense specular highlights exceeding display maximum luminance ($L > 1.0$) can desaturate or shift hue.
   - *Mitigation:* Integrate with CAHRA Layer 5 Hybrid Oklab constant-hue gamut mapping, guaranteeing radial hue preservation.
3. **Dependencies:**
   - Dependent on CAHRA Layer 5 (Oklab Gamut Mapping) and Layer 1 (Surface Normals).
   - Can proceed in parallel with Spike 3A (Shadow Transport).

---

### 7. Expected Deliverables

- `spike3b/spike3b_specular_engine.py`: GGX microfacet BRDF evaluator and area-light approximation.
- `spike3b/spike3b_material_decompose.py`: Specular highlight detection and inpainting module.
- `docs/spike3b/RS-REP-SPIKE-3B-RESULTS.md`: Quantitative verification report with angular error tables.
- `docs/spike3b/RS-DECISION-SPIKE-3B.md`: Formal milestone ratification.
