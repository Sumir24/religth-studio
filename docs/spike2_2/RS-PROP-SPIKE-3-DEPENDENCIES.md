# RELIGHT STUDIO — SPIKE 3 PROPOSAL
## Physically Based Specular Transport, Material Decomposition & 3D Parametric Proxies

- **Document ID:** RS-PROP-SPIKE-3-DEPENDENCIES-v1.0
- **Status:** APPROVED PROPOSAL & ARCHITECTURAL HANDOFF
- **Author:** Principal Physically Based Rendering Engineer & Optical Systems Researcher
- **Preceding Milestones:** RS-SPIKE-1 (Detail Preservation & Gamut Mapping), RS-SPIKE-2.2 (Shadow Transport & Metric Integrity)

---

### 1. Motivation & Context

RS-SPIKE-1 validated that frequency-guided log-luminance reconstruction (E.1) combined with constant-hue Oklab gamut mapping (C3) preserves fine photographic micro-contrast without gradient inversion or chromatic clipping.
RS-SPIKE-2.2 audited shadow transport, establishing that:
1. Multi-scale horizon-based ambient occlusion ($A_{\text{amb}}$) and lit-side bleed guards are production-ready.
2. Pure 2.5D image-space shadow projection cannot achieve true 3D perspective accuracy on complex receivers or occluder chains ($SDE = 5.2 - 48.3\text{ px}$, failing the $\le 3.0\text{ px}$ gate).
3. The diffuse-only assumption in Spikes 1 and 2 leaves specular reflections, glossy highlights, and metallic materials unmodeled.

To deliver a commercial-grade virtual studio gaffer, **Spike 3** must bridge two critical gaps:
1. **Material & Specular Transport:** Replacing diffuse lambertian re-lighting with a physically based microfacet BRDF that relocates, shapes, and tints highlights according to virtual light positions and source shapes.
2. **3D Parametric Geometric Proxies:** Overcoming the 2.5D depth-cliff barrier by pairing monocular depth with lightweight 3D volumetric proxies to cast photorealistic shadows onto arbitrary 3D receivers (including studio cycloramas and curved backdrop sweeps).

---

### 2. Architectural Specification: Specular PBR Transport

```
                               SPIKE 3 RADIANCE DECOMPOSITION
                               
                             Photographic Source RGB
                                        |
                   +--------------------+--------------------+
                   |                                         |
                   v                                         v
       Estimated Base Albedo (a)                   Estimated Specular Map
                   |                                         |
                   +-- Intrinsic Roughness (\alpha)          +-- Fresnel F0 (Dielectric / Metal)
                   |                                         |
                   v                                         v
       Diffuse Radiance L_diffuse                  Specular Radiance L_specular
       (E.1 Guided Filter + HBAO)                 (Cook-Torrance / GGX Microfacet)
                   |                                         |
                   +--------------------+--------------------+
                                        |
                                        v
                            Total Radiance L_relit
                                        |
                                        v
                       C3 Oklab Constant-Hue Gamut Mapping
```

#### 2.1 The Cook-Torrance / GGX Microfacet Model
For a surface point with normal $\mathbf{n}$, camera view vector $\mathbf{v}$, and incident light vector $\mathbf{l}$, the half-angle vector is $\mathbf{h} = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|}$.
The specular BRDF term $f_s(\mathbf{l}, \mathbf{v})$ is defined as:

$$f_s(\mathbf{l}, \mathbf{v}) = \frac{D(\mathbf{h}) \cdot F(\mathbf{v}, \mathbf{h}) \cdot G(\mathbf{l}, \mathbf{v})}{4 \, (\mathbf{n} \cdot \mathbf{l}) \, (\mathbf{n} \cdot \mathbf{v})}$$

Where:
1. **GGX Normal Distribution Function $D(\mathbf{h})$:**
   $$D(\mathbf{h}) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}$$
   Models surface micro-facet roughness $\alpha \in [0.01, 1.0]$.
2. **Schlick Fresnel Approximation $F(\mathbf{v}, \mathbf{h})$:**
   $$F(\mathbf{v}, \mathbf{h}) = F_0 + (1 - F_0) (1 - (\mathbf{v} \cdot \mathbf{h}))^5$$
   Where $F_0 = 0.04$ for standard dielectrics (plastics, leather, ceramics) and $F_0 = \text{Albedo}$ for metals.
3. **Smith Height-Correlated Shadowing-Masking Term $G(\mathbf{l}, \mathbf{v})$:**
   $$G(\mathbf{l}, \mathbf{v}) = \frac{2 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}{(\mathbf{n} \cdot \mathbf{v}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{l})^2} + (\mathbf{n} \cdot \mathbf{l}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{v})^2}}$$

---

### 3. Resolving the 2.5D Barrier: 3D Parametric Geometric Proxies

To solve the $SDE$ and $SLR$ failures documented in RS-SPIKE-2.2, Spike 3 introduces **Parametric Geometric Proxies**:

```
                             PARAMETRIC PROXY PIPELINE
                             
    Monocular Image + Depth       3D Bounding Prior         Parametric Surface Receiver
              |                          |                              |
              v                          v                              v
    2.5D Foreground Mask ----> Fitted 3D Bounding Proxy ----> Fitted 3D Receiver Model
                               (Ellipsoid / Convex Hull)       (Floor + Cyclorama Cove)
                                         |                              |
                                         +--------------+---------------+
                                                        |
                                                        v
                                         Analytical 3D Ray-Traced Shadow
                                         (Sub-pixel accuracy SDE <= 1.0 px)
```

1. **Proxy Fitting:**
   - From the monocular depth and segmentation mask, the system fits an analytical 3D primitive (e.g. an oriented bounding box or multi-part superquadric ellipsoid) to the foreground subject.
2. **True 3D Ray Tracing on Receiver:**
   - Instead of shearing a 2D heightfield, shadows are cast by tracing analytical cones or rays from the virtual light source through the 3D proxy onto the fitted receiver model (e.g. horizontal plane + curved cyclorama fillet: $Y = f(Z)$).
3. **Detail Blending:**
   - High-frequency contact details and sole silhouettes from the 2.5D image are blended as a displacement trim along the proxy's shadow footprint, achieving physical accuracy at distance and photographic fidelity at the contact boundary.

---

### 4. Spike 3 Experimental Gates & Verification Criteria

| Metric | Target Acceptance Gate | Measurement Protocol |
| :--- | :---: | :--- |
| **Shadow Distance Error ($SDE$)** | **$\le 2.0\text{ px}$** | Measured against ground-truth 3D Monte Carlo ray tracer across flat and curved receivers. |
| **Intersection over Union ($\text{IoU}$)** | **$\ge 0.90$** | Measured on shadow silhouette against 3D ground truth. |
| **Specular Repositioning Accuracy** | **$\le 5.0\text{ px}$** | Centroid error of repositioned highlight vs physical ground truth. |
| **Gamut & Chromatic Preservation** | **$DCI \ge 0.990$** | Measured in non-specular regions to ensure highlight synthesis does not alter subject base albedo. |
| **GPU Metal Latency (1080p)** | **$\le 35.0\text{ ms}$** | Measured on Apple Silicon MPS with full microfacet BRDF and proxy ray tracing. |

---

### 5. Summary & Next Steps

RS-SPIKE-2.2 has provided the rigorous mathematical foundation and honest forensic data needed to proceed.
The architecture team can now execute Spike 3 with absolute confidence in its baseline metrics, physical limits, and hardware deployment targets.
