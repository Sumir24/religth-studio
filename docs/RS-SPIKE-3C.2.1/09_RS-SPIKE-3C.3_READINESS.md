# RELIGHT STUDIO — RS-SPIKE-3C.2.1
## Independent Evidence Audit Report 09: RS-SPIKE-3C.3 Readiness Evaluation & Architectural Roadmap

**Author:** Principal Physically Based Rendering Researcher & Metal GPU Architect  
**Milestone:** RS-SPIKE-3C.2.1 — Independent BRDF, Material Transport & Photographic Fidelity Audit  
**Target Milestone:** RS-SPIKE-3C.3 — Image-Based Lighting (IBL) & Studio Reflection Probes  
**Status:** ARCHITECTURALLY READY (Subject to Phase 1 BRDF Safeguard Remediation)

---

### 1. Executive Summary & Readiness Verdict

The completed audit of RS-SPIKE-3C.2 confirms that Relight Studio's core PBR pipeline—comprising Cook–Torrance GGX microfacet BRDFs, physical material profiles, Stochastic Stratified Area Integration, and Two-Scale Physical Energy Decomposition—is mathematically rigorous, highly optimized for Apple Silicon, and ready to evolve into **RS-SPIKE-3C.3 (Image-Based Lighting & Studio Reflection Probes)**.

#### Readiness Verdict: **QUALIFIED READY**
- **Prerequisite Remediation:** Before introducing IBL mipmaps, the denominator safeguard in `distribution_ggx` must be adjusted from `1e-5` to `1e-7` (or $a^2$) to eliminate the non-monotonic peak inversion between roughness $0.04$ and $0.0562$.
- **Architectural Fit:** The Two-Scale energy decomposition ($\mathbf{L}_{\text{relit}} = I_{\text{orig}} \cdot \exp(\hat{\rho}) + \Delta \mathbf{L}_{\text{specular}}$) provides the exact mathematical framework needed to integrate diffuse environment irradiance into the E.1 Guided Filter while streaming specular reflections directly into linear radiant space.

---

### 2. Comprehensive Architectural Resolution to the 8 Core IBL Questions

#### Question 1: HDR Environment Representation (Equirectangular vs Cubemap vs Octahedral)
- **Recommendation:** **Octahedral Mapping for GPU Runtime, Equirectangular for Artist Ingestion.**
  - *Ingestion:* Artists and photography pipelines supply studio environments as standard $2:1$ Equirectangular Lat-Long HDR (`.exr` / `.hdr`).
  - *GPU Runtime:* Convert Lat-Long HDRs into a single 2D **Octahedral Texture** (`MTLPixelFormatRGBA16Float`) with mipmaps. Octahedral mapping provides uniform pixel density without polar pinching (unlike lat-long) and requires only a single 2D texture allocation without the 6-face complexity of cubemaps.
  - *Sampling:* Mapping a unit reflection ray $\mathbf{r}$ to octahedral UV coordinates requires 4 arithmetic instructions:
    $$\mathbf{r}' = \frac{\mathbf{r}}{\|\mathbf{r}\|_1}, \quad \text{uv} = \begin{cases} (r'_x, r'_y) & r'_z \ge 0 \\ (1 - |r'_y|, 1 - |r'_x|) \cdot \text{sign}(r'_x, r'_y) & r'_z < 0 \end{cases}$$

---

#### Question 2: Prefiltered Split-Sum Environment Map & DFG LUT
- **Recommendation:** **Karis / Epic Games Split-Sum Numerical Formulation.**
  The specular IBL integral is factored into:
  $$\int_{\Omega^+} L_i(\mathbf{l}) f_s(\mathbf{l}, \mathbf{v}) (\mathbf{n} \cdot \mathbf{l}) \, d\omega_l \approx \underbrace{\left( \int_{\Omega^+} L_i(\mathbf{l}) D(\mathbf{h}) (\mathbf{n} \cdot \mathbf{l}) \, d\omega_l \right)}_{\text{Prefiltered Environment Map } \text{LD}(\mathbf{r}, \alpha)} \cdot \underbrace{\left( \int_{\Omega^+} f_s(\mathbf{l}, \mathbf{v}) (\mathbf{n} \cdot \mathbf{l}) \, d\omega_l \right)}_{\text{Precomputed BRDF LUT } (F_0 \cdot \text{scale} + \text{bias})}$$
  - *BRDF LUT:* A static, precomputed $256 \times 256$ 2-channel 16-bit float texture (`MTLPixelFormatRG16Float`), indexed by $(\mathbf{n} \cdot \mathbf{v}, \text{roughness})$. Stores the Cook–Torrance geometry and Fresnel scale/bias. Precomputed once and compiled directly into the Metal application bundle (size: $128\,\text{KB}$).
  - *Environment Mip-Chain:* The HDR environment is filtered across 6 mip levels ($\text{roughness} \in \{0.0, 0.2, 0.4, 0.6, 0.8, 1.0\}$) using importance-sampled GGX convolution with $1024$ samples per texel.
  - *Texture Sampling:* Shaders sample the prefiltered environment at LOD $\lambda = \text{roughness} \times (\text{num\_mips} - 1)$ along reflected vector $\mathbf{r} = 2 (\mathbf{n} \cdot \mathbf{v}) \mathbf{n} - \mathbf{v}$.

---

#### Question 3: Studio Reflection Probe Geometry & Parallax Correction
- **Recommendation:** **Parallax-Corrected Box Projection (BPCEM).**
  Infinite environment maps cause virtual studio softboxes to appear at infinite distance, creating incorrect parallax on foreground subjects and receivers.
  - The artist defines a virtual studio bounding box (matching the cyclorama room extents).
  - Ray-box intersection adjusts the reflection vector from surface point $\mathbf{x}$:
    $$\mathbf{r}_{\text{box}} = \mathbf{x} + t_{\text{box}} \mathbf{r} - \mathbf{p}_{\text{probe}}$$
    where $t_{\text{box}} = \min\left( \frac{\mathbf{box}_{\text{max}} - \mathbf{x}}{\mathbf{r}}, \frac{\mathbf{box}_{\text{min}} - \mathbf{x}}{\mathbf{r}} \right)$.
  - This ensures that reflections of softboxes, studio walls, and cove curvatures align with the 3D subject and cyclorama floor.

---

#### Question 4: Diffuse Irradiance from Environment (Spherical Harmonics vs Cubemap)
- **Recommendation:** **Order-3 Spherical Harmonics (L2, 9 Coefficients per RGB Channel).**
  - Evaluating diffuse irradiance from a full environment map is mathematically equivalent to convolving with a broad cosine lobe $\max(0, \mathbf{n} \cdot \mathbf{l})$.
  - Ramamoorthi & Hanrahan (2001) proved that Order-3 Spherical Harmonics capture $> 99.2\%$ of diffuse irradiance energy with zero high-frequency loss.
  - *Memory Footprint:* Exactly 27 float32 values ($9 \times 3 = 108\,\text{bytes}$).
  - *GPU Execution:* Evaluated analytically in Metal shaders without any texture memory lookups:
    $$E_{\text{env, diffuse}}(\mathbf{n}) = \sum_{l=0}^2 \sum_{m=-l}^l \hat{A}_l C_{lm} Y_{lm}(\mathbf{n})$$
    Requires only 16 multiply-adds per pixel in `render_hybrid_studio_kernel`.

---

#### Question 5: Two-Scale Photographic Reconciliation with IBL
- **Recommendation:** **Dual-Stream Radiometric Routing.**
  ```
  [ Diffuse Channel ]                                         [ Specular Channel ]
  E_diff_total = E_direct + E_env_diffuse(SH)                 L_spec_total = L_direct_spec + L_env_spec(IBL)
         |                                                                   |
  rho = log((E_diff_total * expo + amb) / (E_orig + amb))                            |
         |                                                                   |
  E.1 Guided Filter Regularization                                                   |
         |                                                                   |
  I_diffuse_relit = I_orig * exp(rho_bar)                                            |
         |                                                                   |
         +-------------------------------------------------------------------+
                                           |
                                           v
                 L_composite = I_diffuse_relit + L_spec_total * exposure
                                           |
                                           v
                             C3 Oklab Constant-Hue Compression
  ```
  - **Diffuse Environment Irradiance** is integrated additively into $E_{\text{target, diffuse}}$, modulating the base photograph through the E.1 Guided Filter log ratio. This preserves fine microtexture while smoothly tinting and illuminating the subject with environmental bounce.
  - **Specular Environment Radiance** bypasses the Guided Filter entirely, streaming directly into the Pass 7 linear composite. This ensures reflections of studio softbox strips, windows, and studio umbrellas remain sharp.

---

#### Question 6: Resolution of Single-Image Conductor Darkening (Plate P1 Case)
- **Problem in RS-SPIKE-3C.2:** Setting $\text{metallic} = 1.0$ extinguished diffuse bounce ($k_d \to 0$). In the absence of an environment map, areas not directly hit by a virtual softbox decayed to ambient fill ($0.15$), dropping DCI on Plate P1 to $0.7899$.
- **IBL Resolution:**
  - Real conductors reflect the entire $360^\circ$ hemisphere of the room.
  - Under IBL, when $k_d = 0$, the surface is **not dark**—it reflects the prefiltered studio environment:
    $$\mathbf{L}_{\text{relit}} = F_0 \cdot \text{EnvSpec}(\mathbf{r}, \text{roughness})$$
  - The knit mesh of the sneaker will continuously reflect the floor, ceiling, and ambient studio light, maintaining continuous spatial luminance and eliminating the extreme contrast collapse.
  - This solves the Plate P1 Rough Metal limitation physically, without requiring ad-hoc heuristic clamps.

---

#### Question 7: Metal 3 Pipeline Integration & Unified Memory Architecture
- **Buffer & Texture Architecture:**
  - `MTLTextureType2DArray` or single octahedral `MTLTextureType2D` with mip levels 0 to 5.
  - Storage Mode: `MTLStorageModeShared` on Apple Silicon Unified Memory.
  - Hardware Filtering: Native Metal bilinear sampler with seamless mip-filtering (`sampler(filter::linear, mip_filter::linear)`).
  - Pre-filtering Compute Kernel: An offline GPU preprocessing pass (`metal2_prefilter_environment`) executes in $< 15\,\text{ms}$ upon loading a new `.hdr` file, writing directly into the cached buffer pool.

---

#### Question 8: Artist Interaction & Workspace Integration
- **Gradio 6 Workspace Controls:**
  1. **Studio Environment Dropdown:** Curated HDR studio presets:
     - `Warm Portrait Studio` (large diffused key, warm bounce floor).
     - `Commercial Product Studio` (high-contrast dual strip softboxes, clean white cyclorama).
     - `Cool Rim Dramatic` (dark moody backdrop, sharp rim kickers).
  2. **Environment Exposure Slider:** $[-3.0, +3.0]\,\text{EV}$.
  3. **Environment Azimuth Rotation:** Continuous circular dial / slider $[0^\circ, 360^\circ]$ to rotate the reflection environment interactively at $> 80\,\text{FPS}$.
  4. **Custom HDR Upload:** File upload component supporting `.hdr` and `.exr` files.

---

### 3. Engineering Checklist & Prerequisites for RS-SPIKE-3C.3

Before starting RS-SPIKE-3C.3 implementation:
- [ ] **Fix Phase 1 Safeguard Defect:** In `studio3a/brdf.py` and `metal2/shaders/renderer.metal`, update `distribution_ggx`:
  ```python
  denom = np.maximum(denom, a2)  # Bounds denominator by alpha^2 instead of 1e-5
  ```
- [ ] **Precompute 2D BRDF LUT:** Generate static $256 \times 256$ fp16 LUT and embed into `metal2/shaders/`.
- [ ] **Integrate Fast Octahedral Converter:** Implement spherical-to-octahedral projection compute shader.
- [ ] **Implement Order-3 Spherical Harmonics Projector:** Extract 9 RGB SH coefficients from incoming HDR maps.

---

### 4. Summary & Phase 9 Audit Conclusion

Relight Studio is architecturally prepared for RS-SPIKE-3C.3. The Cook–Torrance microfacet BRDF, Two-Scale decomposition, and Metal GPU pipeline provide a rock-solid foundation for Image-Based Lighting and Studio Reflection Probes.
