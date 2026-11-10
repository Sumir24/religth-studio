# RS-SPIKE-3C.1 — Remaining Risks & Next Steps
## Forward Engineering Roadmap for RS-SPIKE-3C.2

**Document ID:** RS-SPIKE-3C.1-11  
**Milestone:** RS-SPIKE-3C.1  
**Author:** Principal Rendering Engineer & GPU Architect  
**Date:** November 10, 2026  
**Status:** COMPLETE (Roadmap Formulated for RS-SPIKE-3C.2)

---

## 1. Executive Summary

RS-SPIKE-3C.1 successfully established a physically coherent, additive multi-light studio lighting engine capable of interactive rendering ($\ge 85\,\text{FPS}$ at 1080p) on Apple Silicon, with independent area light shadows, high photographic fidelity on real plates ($DCI \ge 0.9575$), and strict gamut safety.

However, studio photography relies heavily on surface finish, material reflections, and specular highlights (e.g., sheen on leather shoes, gloss on sculptural marble, metallic trim, and eye catchlights). The current engine evaluates pure Lambertian diffuse transport.

This document catalogs the remaining technical limitations and outlines the concrete architectural roadmap for **RS-SPIKE-3C.2: Specular Microfacet BRDFs & Material Transport**.

---

## 2. Technical Risk Register

| Risk ID | Category | Description | Severity | Impact | Mitigation Strategy |
|:---:|---|---|:---:|---|---|
| **R-3C1-01** | BRDF Scope | Current pipeline is purely Lambertian diffuse ($f_r = \rho / \pi$). Glossy and metallic highlights cannot be rendered. | Medium | Materials appear matte/chalky under grazing light angles. | Implement Cook-Torrance GGX microfacet specular BRDF in Spike 3C.2. |
| **R-3C1-02** | Specular Area Integration | Evaluating microfacet specular highlights over finite rectangular area lights requires solving spherical polygons or using LTC approximations. | High | Naive sampling of $G \times G$ points on area light causes specular noise or aliasing. | Adopt Linearly Transformed Cosines (LTC) or Karis Representative Point approximation. |
| **R-3C1-03** | Specular Detail Preservation | E.1 Guided Filter regularizes ratio $\rho = \log(E_{\text{target}} / E_{\text{orig}})$. If specular highlights cause extreme localized ratio spikes, edge halos could emerge. | High | Potential halo artifacts around bright studio light reflections. | Decompose into diffuse and specular ratio terms; regularize diffuse with E.1 and add specular additively in linear energy space. |
| **R-3C1-04** | C/Metal Memory Alignment | Adding material properties (`roughness`, `metallic`, `specular_f0`) expands the C/Objective-C/Metal struct layouts. | Medium | Alignment mismatches between Host Python/C++ and GPU Metal kernels cause memory corruption. | Maintain strict 16-byte alignment boundaries for all struct members; add static assertions (`static_assert`). |
| **R-3C1-05** | Geometry Limitations | Scene occlusion is currently driven by a single superquadric geometric proxy. Complex concave geometry or articulated subjects are not represented. | Low | Contact shadows on complex objects (e.g. shoelaces, fingers) are simplified. | Multi-proxy or signed distance field (SDF) proxy support scheduled for Milestone 4. |

---

## 3. Architectural Roadmap for RS-SPIKE-3C.2

### 3.1 Physics & Mathematics of Specular Transport

In RS-SPIKE-3C.2, the surface radiance equation will be extended to the full Cook-Torrance microfacet BRDF model:
$$f_r(\mathbf{l}, \mathbf{v}) = (1 - k_s) f_{\text{diffuse}} + k_s f_{\text{specular}}$$
$$f_{\text{specular}}(\mathbf{l}, \mathbf{v}) = \frac{D(\mathbf{h}, \alpha) \cdot F(\mathbf{v}, \mathbf{h}, F_0) \cdot G(\mathbf{l}, \mathbf{v}, \mathbf{h}, \alpha)}{4 (\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})}$$

Where:
1. **$D(\mathbf{h}, \alpha)$ — GGX Normal Distribution Function (NDF):**
   $$D(\mathbf{h}, \alpha) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}, \quad \alpha = \text{roughness}^2$$
2. **$F(\mathbf{v}, \mathbf{h}, F_0)$ — Schlick Fresnel:**
   $$F(\mathbf{v}, \mathbf{h}, F_0) = F_0 + (1 - F_0) (1 - (\mathbf{v} \cdot \mathbf{h}))^5$$
   With $F_0 = 0.04$ for dielectrics and $F_0 = \text{Albedo}$ for conductors ($k_{\text{metallic}} \to 1$).
3. **$G(\mathbf{l}, \mathbf{v}, \mathbf{h}, \alpha)$ — Smith Height-Correlated Visibility Function:**
   $$G(\mathbf{l}, \mathbf{v}, \mathbf{h}, \alpha) = \frac{2 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}{(\mathbf{n} \cdot \mathbf{v}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{l})^2} + (\mathbf{n} \cdot \mathbf{l}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{v})^2}}$$

### 3.2 Area Light Specular Integration (Linearly Transformed Cosines / MRP)
Evaluating specular highlights over a rectangular area light cannot rely on naive point sampling without introducing high variance.

Two approaches are planned for RS-SPIKE-3C.2:
- **Primary: Linearly Transformed Cosines (Heitz et al., 2016):**
  Transforms the clamped cosine distribution to approximate GGX under arbitrary roughness, computing the analytical integral of a polygonal emitter in closed form using 2D lookup tables.
- **Secondary (Fallback): Most Representative Point (MRP) (Karis, 2013):**
  Picks the point on the rectangular light closest to the reflected view ray $\mathbf{r} = 2 (\mathbf{n} \cdot \mathbf{v})\mathbf{n} - \mathbf{v}$, adjusting the solid angle and roughness according to light size. MRP offers exceptional compute efficiency ($< 0.5\,\text{ms}$ overhead on Metal).

### 3.3 Two-Scale Photographic Ratio Decomposition
To prevent specular reflection spikes from destabilizing the E.1 Guided Filter, we formulate a two-scale energy decomposition:
$$\mathbf{L}_{\text{final}} = I_{\text{orig}} \cdot \exp(\hat{\rho}_{\text{diffuse}}) + \mathbf{L}_{\text{specular, target}} - \mathbf{L}_{\text{specular, orig}}$$
Where:
- $\hat{\rho}_{\text{diffuse}} = \text{GuidedFilter}\left(\log \frac{\mathbf{E}_{\text{target, diffuse}} + \epsilon}{\mathbf{E}_{\text{orig, diffuse}} + \epsilon}, I_{\text{orig}}\right)$ preserves microtexture and surface albedo details.
- $\mathbf{L}_{\text{specular}}$ represents direct glossy specular transport, added linearly to preserve sharp specular reflections without blurring or haloing.

---

## 4. Work Breakdown Structure for RS-SPIKE-3C.2

```
Phase 0: Baseline Verification & Mathematical Formulation
├── Verify 3C.1 codebase & regression tests
├── Mathematical specification of GGX BRDF + LTC / MRP area integration
└── Formulate two-scale diffuse-specular photographic reconstruction

Phase 1: Scene Model & Workspace Integration
├── Extend SubjectProxyData with roughness, metallic, specular_f0, sheen
├── Extend ReceiverData with ground roughness and reflectivity
├── Update StudioScene serialization (v3.2.0 schema)
└── Implement Workspace material parameter UI controls & undo/redo tracking

Phase 2: CPU Reference Implementation
├── Implement Cook-Torrance GGX evaluator in studio3a/lighting.py
├── Implement MRP area light specular integration
├── Extend studio3a/renderer.py for multi-light diffuse + specular transport
└── Verify energy conservation across roughness in [0.05, 1.0]

Phase 3: Native Metal GPU Shader & Bridge Integration
├── Add MaterialParams to metal_bridge.h (64-byte aligned)
├── Update evaluate_multilight_surface_kernel with specular accumulation
├── Implement vectorized MRP reflection calculation in Metal Shading Language
└── Compile and link libmetal2.dylib

Phase 4: Experimental Validation & Parity
├── Validate CPU-Metal numerical parity (Soft IoU >= 0.999, MAE < 0.0005)
├── Verify roughness transitions (mirror sheen -> satin -> rough matte)
└── Measure multi-light specular performance on Apple M5 (Target >= 60 FPS at 1080p)

Phase 5: Photographic Fidelity & Final Acceptance
├── Evaluate real studio plates with glossy highlights (sneaker patent leather, statue polish)
├── Confirm zero edge halos around specular highlights
└── Complete documentation suite and regression testing
```

---

## 5. Summary Recommendation

With the completion and validation of RS-SPIKE-3C.1, the multi-light additive illumination architecture is sound, stable, and highly performant. The team is fully prepared to commence **RS-SPIKE-3C.2**.
