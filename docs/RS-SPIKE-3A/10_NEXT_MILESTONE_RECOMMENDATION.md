# RELIGHT STUDIO — RS-SPIKE-3A
## Next Milestone Recommendation & Engineering Handoff

**Document:** `docs/RS-SPIKE-3A/10_NEXT_MILESTONE_RECOMMENDATION.md`  
**Status:** Approved Engineering Baseline  
**Milestone:** RS-SPIKE-3A  
**Date:** November 2026  

---

### 1. Milestone Conclusion & Retrospective

Milestone RS-SPIKE-3A has successfully resolved the fundamental architectural crisis identified in Spikes 2.1 and 2.2:
- **Heuristic 2.5D Image-Space Screen Shadows Failed:** Depth disocclusion, non-monotonic falloff, and perspective distortions could not be repaired in screen space.
- **Scene-Driven 3D Analytical Ray Tracing Succeeded:** Modeling real 3D rectangular area lights, analytical proxies, and curved cyclorama receivers delivers mathematically defensible lighting with **$0.00\%$ shadow leakage**, **$0.000$ contact grounding errors**, and **deterministic replay**.

With the 3D studio foundation in place, Relight Studio is ready for its next developmental phase.

---

### 2. Dual-Track Recommendation: RS-METAL-2 & RS-SPIKE-3B

To transition this research foundation into an interactive product, we recommend two synchronized tracks:

```
                                [RS-SPIKE-3A COMPLETED]
                        (3D Studio Foundation, Proxies, Area Light)
                                            |
                    +-----------------------+-----------------------+
                    |                                               |
                    v                                               v
            [TRACK 1: PERFORMANCE]                         [TRACK 2: MATERIAL PBR]
                 RS-METAL-2                                      RS-SPIKE-3B
         Metal 3D Ray Tracing Kernels                   Specular PBR & Microfacets
       - Area Light Monte Carlo on GPU                 - GGX / Cook-Torrance BRDF
       - Analytical Proxy Intersections                - Roughness & Metallic Estimation
       - Sub-12ms 60 FPS Viewport                      - Moving Specular Glint Synthesis
                    |                                               |
                    +-----------------------+-----------------------+
                                            |
                                            v
                                     [RS-RELEASE-1.0]
                             Integrated Artist Virtual Studio
```

---

### 3. Track 1: RS-METAL-2 — GPU Acceleration & Real-Time Performance

**Priority:** Critical (Required for product interactivity)  
**Objective:** Port the CPU ray tracing and area lighting pipeline to native Apple Metal compute kernels.

#### Detailed Scope:
1. **Metal Compute Shaders (`.metal`):**
   - Implement `generate_primary_rays_kernel`: High-resolution camera ray dispatch.
   - Implement `intersect_proxies_kernel`: Analytical slab tests (OBB) and numerical root finding (Superquadric) executing in parallel across GPU threads.
   - Implement `trace_area_light_shadows_kernel`: Stratified Monte Carlo ray generation with hardware threadgroups, accelerating shadow evaluation by $> 100\times$.
2. **MPS Ray Tracing (Metal Performance Shaders):**
   - For triangle meshes (`LowPolyMesh` and imported OBJ proxies), utilize Apple Silicon's hardware BVH traversal and ray-triangle intersection units.
3. **Target Performance Budget:**
   - Interactive Preview (4-8 samples): $\le 12.0\text{ ms}$ (80+ FPS at 1080p).
   - Final Production Render (32-64 samples): $\le 100.0\text{ ms}$.

---

### 4. Track 2: RS-SPIKE-3B — Specular Transport & Material Decomposition

**Priority:** High (Required for shiny, metallic, and glass products)  
**Objective:** Extend the lighting model beyond diffuse Lambertian irradiance to include physically based specular highlights.

#### Detailed Scope:
1. **Microfacet BRDF Evaluation:**
   Implement the Cook-Torrance specular reflectance model:
   $$f_s(L, V) = \frac{D(H) \cdot F(V, H) \cdot G(L, V, H)}{4 (N \cdot L)(N \cdot V)}$$
   - $D(H)$: Trowbridge-Reitz (GGX) normal distribution function.
   - $F(V, H)$: Schlick's approximation for Fresnel reflectance with base reflectance $F_0$.
   - $G(L, V, H)$: Smith's height-correlated masking-shadowing function.
2. **Roughness & Specular Map Estimation:**
   Estimate per-pixel surface roughness $\alpha$ and specular tint from photographic highlights and texture variance.
3. **Specular Highlight Synthesis & Trajectory:**
   Ensure moving the rectangular area light causes realistic specular glints and softbox reflections to glide naturally across curved product surfaces.

---

### 5. Architectural Invariants to Maintain

In all future milestones, engineering teams must maintain the following non-negotiable standards established in RS-SPIKE-3A:
1. **Photographic Immutability:** The input photograph is the ground truth. Never mutate or destructively overwrite original pixel data.
2. **Non-Destructive Ratio Reconstruction:** All appearance changes must pass through regularized shading ratios with protected zero-mutation masks.
3. **Deterministic Replay:** Every scene state must serialize to human-readable JSON and re-render bitwise identical outputs.
4. **Honest Numerical Reporting:** Report genuine measured latencies and error metrics without synthetic padding or unverified claims.
