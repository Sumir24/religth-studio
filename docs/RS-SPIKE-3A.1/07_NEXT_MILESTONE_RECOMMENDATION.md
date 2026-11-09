# RELIGHT STUDIO — RS-SPIKE-3A.1
## Architectural Roadmap & Next Milestone Recommendation: RS-SPIKE-3B

**Document Reference:** `RS-REC-SPIKE-3B-ROADMAP`  
**Milestone Recommendation:** Progression to **RS-SPIKE-3B (Multi-Light Rigs, Hardware BVH & Bilateral Normal Supervision)**  
**Author:** Principal Graphics Systems Architect & Computational Photography Researcher  
**Date:** November 2026  
**Status:** PROPOSED FOR IMPLEMENTATION AUTHORIZATION  

---

## 1. Context & Architecture Status

With the successful completion and formal pass of **RS-SPIKE-3A.1**, Relight Studio has established a rock-solid, production-ready foundation:
- An authoritative CPU reference renderer with physically grounded area light irradiance, analytical soft penumbras, and contact grounding.
- A high-performance native Apple Silicon Metal GPU renderer achieving real **$715.6\times$ acceleration** on Oklab Gamut Mapping and sub-millisecond frame times on product proxies.
- An interactive, responsive 3D studio workspace (`studio3a/workspace.py`) running at **$88\,\text{FPS}$** with exact bitwise zero-mutation on protected photographic regions.

The single-light geometric shadow and reconstruction pipeline is now validated and production frozen.

---

## 2. Recommended Next Milestone: RS-SPIKE-3B
### Theme: Multi-Light Virtual Photography Rigs, Hardware BVH & Bilateral Surface Normal Supervision

RS-SPIKE-3B should focus strictly on expanding lighting expressiveness and geometric scaling without deviating from the core computational photography architecture.

```
+---------------------------------------------------------------------------------------------------+
|                                 RS-SPIKE-3B ARCHITECTURAL FOCUS                                   |
|                                                                                                   |
|  1. Multi-Light Studio Rig      --> Key, Fill, Rim, and Kickers (up to 8 simultaneous lights)     |
|  2. MPSRayTracing Hardware BVH  --> Scale from 280 to 50,000+ triangles via Apple Silicon RT core |
|  3. Bilateral Normal Supervisor --> Joint bilateral filtering of monocular normals vs photo edges  |
|  4. Photographic Presets Library--> 3-point studio, Rembrandt, Golden Hour, High-Key Commercial   |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Scoped Technical Work Packages for RS-SPIKE-3B

### Work Package 1: Multi-Light Virtual Photography Rigs
- **Objective:** Support up to 8 simultaneous rectangular area lights with independent positional, rotational, dimensional, Kelvin, and energy parameters.
- **Metal Architecture:**
  - Update `LightParams` uniform buffer to a structured array `constant LightParams* lights [[buffer(3)]]`.
  - Pass `uint num_active_lights` to the kernel.
  - Accumulate direct unshadowed irradiance $E = \sum_l E_l$ and direct shadowed visibility $V = \frac{\sum_l V_l \cdot E_l}{\sum_l E_l}$ (energy-weighted composite visibility).
- **Interactive Inspector:**
  - Tabbed or list-based light selection in the Inspector.
  - Per-light solo, mute, and color temperature controls.

### Work Package 2: Hardware-Accelerated BVH via MPSRayTracing
- **Objective:** Scale product proxy geometry from low-poly procedural hulls (~280 triangles) to production-grade scanned product CAD/OBJ meshes ($10,000 - 100,000$ triangles).
- **Metal Architecture:**
  - Integrate Apple's `MetalPerformanceShaders` `MPSRayIntersector` and `MPSTriangleAccelerationStructure`.
  - Build hardware-accelerated bounding volume hierarchy (BVH) once upon mesh import.
  - Leverage Apple Silicon M3/M4/M5 hardware ray tracing acceleration blocks, enabling sub-millisecond shadow ray traversal across arbitrary high-poly geometries.

### Work Package 3: Bilateral Surface Normal Supervisor
- **Objective:** Mitigate high-frequency noise and boundary bleeding in monocular normal estimation maps.
- **Formulation:**
  - Apply cross-bilateral normal filtering guided by original photographic RGB luminance:
    $$\mathbf{n}'(\mathbf{p}) = \frac{1}{W_{\mathbf{p}}} \sum_{\mathbf{q} \in \Omega} G_{\sigma_s}(\|\mathbf{p} - \mathbf{q}\|) \cdot G_{\sigma_r}(|I(\mathbf{p}) - I(\mathbf{q})|) \cdot \mathbf{n}(\mathbf{q})$$
  - Preserves crisp product silhouette edges while smoothing flat surfaces and removing artificial wrinkles.
  - Implemented as a single-pass 2D Metal compute kernel prior to lighting evaluation.

### Work Package 4: Curated Studio Lighting Presets
- **Objective:** Give creators instant 1-click access to professional commercial photography setups:
  1. **Three-Point Commercial:** Warm Key ($45^\circ$, 3200K), Cool Fill ($60^\circ$ opposite, 5600K), Rim Backlight ($135^\circ$, 6500K).
  2. **Rembrandt Portrait/Product:** High-contrast key creating the classic triangular illumination on the cheek/side panel.
  3. **High-Key E-Commerce:** Wrap-around softboxes on cyclorama background for clean white catalog isolation.
  4. **Golden Hour Backlight:** Low-angle warm kicker ($2700\text{K}$) with soft neutral ambient fill.

---

## 4. Anti-Features & Explicit Restrictions for RS-SPIKE-3B

To prevent scope creep, maintain engineering focus, and safeguard the photographic integrity of Relight Studio, the following are strictly prohibited in RS-SPIKE-3B:

1. **NO Generative AI Inpainting / Diffusion Replacements:**
   - Relight Studio is an optical lighting tool, not an image generator. Generative diffusion hallucination violates subject identity preservation and is strictly out of scope.
2. **NO Full Multi-Bounce Monte Carlo Path Tracing:**
   - Secondary diffuse/specular indirect global illumination bounces will degrade interactive frame rates without tangible benefit on 2.5D photographic plates. Ambient occlusion and contact grounding already fulfill grounding needs.
3. **NO Complex Specular Microfacet GGX / Roughness Decomposition:**
   - Full material inverse rendering remains speculative on uncalibrated single photographs. Keep the primary focus on directional diffuse irradiance, geometric shadow transport, and E.1 detail preservation.
4. **NO CPU-GPU Shared Memory Synchronization Overhead:**
   - Preserve zero-copy shared memory (`MTLResourceStorageModeShared`). Do not introduce blit passes or host synchronization locks during interactive dragging.

---

## 5. Transition Plan & Authorization Request

Upon user authorization, the team should proceed immediately to:
1. Initialize the `studio3b/` development branch.
2. Port multi-light uniform packing to `metal2/`.
3. Construct the cross-bilateral normal supervisor kernel.
4. Execute validation benchmarks against multi-light commercial photographic plates.
