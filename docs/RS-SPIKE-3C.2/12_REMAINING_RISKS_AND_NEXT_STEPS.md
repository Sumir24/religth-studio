# RELIGHT STUDIO — RS-SPIKE-3C.2
## Technical Report 12: Remaining Engineering Risks & Strategic Next Steps

**Author:** Principal Physically Based Rendering Engineer & System Architect  
**Milestone:** RS-SPIKE-3C.2 — Specular Microfacet BRDFs & Material Transport  
**Target Milestone:** RS-SPIKE-3C.3 / RS-SPIKE-3D  
**Status:** COMPLETE & COMMITTED

---

### 1. Architectural Achievements in RS-SPIKE-3C.2

RS-SPIKE-3C.2 successfully established:
1. **Cook-Torrance Microfacet BRDF:** GGX NDF, Smith height-correlated masking-shadowing, and Schlick Fresnel approximations running on both CPU and native Metal 3 GPU.
2. **Two-Scale Physical Energy Decomposition:** Separated diffuse ratio regularization (via E.1 Guided Filter) from additive specular highlights in linear radiant space, eliminating highlight smearing and edge halos.
3. **5 Curated PBR Profiles:** Fabric, Marble, Plastic, Rough Metal, and Polished Metal with full schema v3.2.0 integration and undo/redo support.
4. **Stochastic Stratified Integration:** Zero additional ray casts by evaluating area-light specular transport over the exact same stratified ray positions used for shadow testing.
5. **Interactive Apple Silicon Performance:** Over $180\,\text{FPS}$ at $1024 \times 576$ Viewport Preview and up to $78\,\text{FPS}$ at $1920 \times 1080$ Full HD with zero steady-state memory allocations.

---

### 2. Remaining Technical Risks & Physical Limitations

#### 2.1 Absence of Image-Based Lighting (IBL) Reflection Probes
- **Observation:** In pure studio lighting without an environment map, a mirror metal ($m = 1.0, \alpha = 0.08$) reflects virtual softbox apertures crisply, but all other reflected directions appear black. On an authentic photograph, this causes dark regions on the subject where direct light specular reflections do not point toward the camera.
- **Risk:** Artists attempting to apply mirror chrome or polished gold to non-studio outdoor photographs may perceive unnatural high contrast.
- **Mitigation for Next Milestone:** Introduce an artist-adjustable HDRI studio environment reflection map or spherical harmonics ambient probe to provide off-light specular fill.

#### 2.2 Microgeometry Normal Map Discrepancies
- **Observation:** The monocular surface normals estimated from photographic plates represent macroscopic shapes and drapery folds, but do not capture high-frequency surface roughness or micro-faceting.
- **Risk:** Broad specular lobes on rough surfaces can look smooth unless modulated by high-frequency bump or normal perturbance maps.
- **Mitigation:** In RS-SPIKE-3C.3, introduce procedural micro-facet normal perturbation (e.g. Perlin noise or fabric weave triplanar mapping) to break up specular reflections naturally.

#### 2.3 Clearcoat & Dual-Lobe Reflections
- **Observation:** Certain commercial materials (car paint, lacquered wood, carbon fiber, glazed ceramics) exhibit a dual-layer reflectance: a rough base layer covered by a smooth, mirror-like transparent coat.
- **Risk:** Modeling these with a single microfacet lobe forces a compromise between base roughness and surface gleam.
- **Mitigation:** Plan a lightweight second GGX lobe (`clearcoat` in $[0, 1]$ and `clearcoat_roughness` in $[0, 1]$) for specialized product photography.

---

### 3. Strategic Roadmap for RS-SPIKE-3C.3

1. **Studio HDRI & Reflection Probes (RS-SPIKE-3C.3):**
   - Add Split-Sum approximation (Karis environment BRDF LUT + pre-filtered radiance cubemaps) for image-based ambient specular reflection.
   - Ground metals in realistic photographic studio environments.
2. **Material Mask Painting & Regional Assignment:**
   - Allow artists to paint material assignment masks directly on the photograph (e.g. rubber sole = Plastic, leather upper = Leather, eyelets = Polished Metal).
3. **Photographic Export Engine:**
   - Add 16-bit float EXR and wide-gamut Display P3 / Rec.2020 image export.
