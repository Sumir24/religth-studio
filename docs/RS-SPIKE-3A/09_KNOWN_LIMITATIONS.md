# RELIGHT STUDIO — RS-SPIKE-3A
## Known Limitations, Boundary Conditions & Architectural Scope

**Document:** `docs/RS-SPIKE-3A/09_KNOWN_LIMITATIONS.md`  
**Status:** Approved Engineering Baseline  
**Milestone:** RS-SPIKE-3A  
**Date:** November 2026  

---

### 1. Architectural Scope & Explicit Non-Goals

Milestone RS-SPIKE-3A establishes the **Virtual 3D Studio Foundation**: analytical geometry proxies, rectangular area light sampling, cyclorama receivers, decoupled shadow transport, non-destructive reconstruction, and dual-viewport workspace interaction.

To prevent scope creep and maintain experimental focus, several capabilities were intentionally deferred or scoped out:

```
+------------------------------------+---------------------------------------+
| IN SCOPE (RS-SPIKE-3A)             | OUT OF SCOPE (DEFERRED MILESTONES)    |
+------------------------------------+---------------------------------------+
| - Analytical Proxies (OBB, Superq) | - Specular PBR & GGX Microfacets (3B) |
| - Procedural Low-Poly Mesh (280 tri)| - Multi-bounce Global Illumination    |
| - Infinite Plane & Cyclorama Cove  | - Automated AI Geometry Generation    |
| - Monte Carlo Area Light (Direct)  | - Multi-light Studio Rigs (>1 light)  |
| - Soft Penumbras & Contact Occl.   | - Native Metal Compute Kernels (M2)   |
| - Non-destructive E.1/C3 Reconst.  | - Full 3D Mesh Authoring Tools        |
+------------------------------------+---------------------------------------+
```

---

### 2. Known Limitations & Technical Constraints

#### 2.1 Single-Primitive Geometric Proxy Fidelity
- **Problem:** Single analytical primitives (OBB, Superquadric) represent convex, uniform topologies. Real-world products often consist of articulated multi-material assemblies (e.g., a luxury watch with a round bezel, cylindrical crown, and segmented strap).
- **Consequence:** In Case S3A_05 (Metallic Watch), fitting an OBB resulted in $SDE = 141.89\text{ px}$ and $\text{IoU} = 0.051$. The shadow cast by the box did not match the intricate silhouette of the watch strap.
- **Resolution Path:** Future milestones should support composite multi-primitive proxy trees or imported USDZ/OBJ low-poly proxy meshes.

#### 2.2 Monocular Scale & Camera Alignment Ambiguity
- **Problem:** A single 2D photograph lacks absolute physical metric scale. A small perfume bottle photographed close with a 24mm lens can produce a similar image to a larger bottle photographed from afar with a 70mm lens.
- **Consequence:** The artist must manually adjust virtual camera FOV and proxy scale using the 3D wireframe overlay.
- **Resolution Path:** Spike 3C / 4 will integrate camera focal length metadata from EXIF and automatic ground plane estimation.

#### 2.3 Diffuse-Only Illumination (Absence of Specular PBR)
- **Problem:** The lighting model in Spike 3A evaluates Lambertian cosine direct irradiance $E = \max(N \cdot L, 0) / d^2$. It does not model Cook-Torrance microfacet specular reflection, GGX roughness distributions, or Fresnel reflectance equations ($F_0$).
- **Consequence:** Glossy, metallic, and glass products (e.g., chrome watches, polished glass bottles) exhibit diffuse shading changes but do not show moving specular highlight glints.
- **Resolution Path:** This is the core research subject of **RS-SPIKE-3B (Material Decomposition & Specular Transport)**.

#### 2.4 CPU Ray Tracing Performance Bottleneck
- **Problem:** Vectorized ray tracing implemented in pure Python/NumPy evaluates millions of ray-surface tests on the CPU.
- **Consequence:** Preview latency is ~140 ms and mesh final rendering is ~8,000 ms, which is too slow for 60 FPS interactive light dragging.
- **Resolution Path:** This confirms the architectural requirement for **RS-METAL-2 (Metal Compute Kernels)** to run on Apple Silicon GPU hardware.

#### 2.5 Secondary Indirect Illumination (Color Bleeding & Bounce)
- **Problem:** Spike 3A models direct area light illumination and direct receiver shadows. It does not compute inter-reflections (e.g., colored light bouncing off a bright red backdrop back onto the subject).
- **Consequence:** In deep crevices, illumination falls back to ambient floor levels without warm secondary bounce.
- **Resolution Path:** Spherical harmonic or irradiance caching approximations will be evaluated in subsequent milestones.
