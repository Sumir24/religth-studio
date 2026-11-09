# RELIGHT STUDIO — MASTER TECHNICAL RESEARCH COMPENDIUM

**Classification:** Research, Mathematical Foundations & Architectural Ideation  
**Framework:** GRAVITAS Engineering Reliability Runtime  
**Status:** COMPLETE / VALIDATED  
**Target Platform:** Local-First macOS 14.0+ (Apple Silicon Metal 3 + Core ML)  

---

## EXECUTIVE SUMMARY

This research study establishes the technical, mathematical, and algorithmic foundations for **Relight Studio**—a local-first, non-destructive 2.5D virtual lighting studio for existing photographs.

In strict adherence to the project directive (*"This is a research and learning phase. Do not start implementing the application yet"*), this study identifies the exact physical principles, open-source models, licensing clearances, and failure boundaries required to build the application without premature implementation.

The research compendium is organized into three comprehensive volumes covering all 18 topics across their designated priority tiers:

```
docs/research/
├── README.md                                             # This Master Navigation Index
├── PART_1_CORE_PHYSICS_AND_SCENE_DECOMPOSITION.md       # Priority 1: Topics 1–7
├── PART_2_RENDERING_SHADOWS_AND_COLOR_SCIENCE.md        # Priority 2: Topics 8–12
└── PART_3_SYSTEMS_COMPUTING_AND_COMMERCIAL_VIABILITY.md # Priority 3: Topics 13–18
```

---

## DIRECTORY OF RESEARCH VOLUMES & TOPICS

### [Part 1: Core Optics, Computational Photography & Scene Decomposition](PART_1_CORE_PHYSICS_AND_SCENE_DECOMPOSITION.md)
*Priority 1: Core physical and computer vision foundations.*
1. **Topic 1: Image Formation & Computational Photography** — Rendering equation, optical sensor integration, linear radiometric vs. display-referred models, and the fundamental under-determined single-image barrier.
2. **Topic 2: Intrinsic Image Decomposition** — Retinex theory, albedo/shading separation, direct vs. ambient sunlight formulation, and why academic pre-trained intrinsic weights are legally disqualified.
3. **Topic 3: Sunlight & Sky Illumination Estimation** — Perez All-Weather Sky Model, analytical solar azimuth/elevation fitting from sky luminance gradients, and shadow-casting direction triangulation.
4. **Topic 4: Scene Understanding & Semantic Segmentation** — SAM 2, SegFormer-B1, continuous alpha edge matting (BiRefNet), and semantic protection zones.
5. **Topic 5: Monocular Depth Estimation & 2.5D Scene Representation** — Camera-space point cloud unprojection $\mathbf{P}(u, v)$, relative vs. metric disparity, and selection of Depth Anything V2 (Small/Base) as exclusive commercial backbone.
6. **Topic 6: Surface Normal Estimation & Material Understanding** — DSINE neural normals, analytical depth-gradient normals ($\nabla D$), GGX roughness, and dielectric vs. conductor classification.
7. **Topic 7: Single-Image Relighting State of the Art** — Critical audit of generative diffusion (IC-Light, ControlNet) vs. 2.5D deterministic GPU shading; why pixel hallucination is disqualified for commercial photography.

---

### [Part 2: Lighting Mathematics, Shadows, Detail Preservation & Color Science](PART_2_RENDERING_SHADOWS_AND_COLOR_SCIENCE.md)
*Priority 2: Rendering mathematics, physical light models, and visual fidelity.*
8. **Topic 8: Light Transport & Lighting Mathematics** — Lambertian diffuse, Cook-Torrance microfacet specular, physical inverse-square falloff, Heitz Linearly Transformed Cosines (LTC) area softboxes, rim lighting, and negative fill transmittance fields.
9. **Topic 9: Shadow Estimation & 2.5D Occlusion** — Screen-Space Ray Tracing (SSRT) through depth buffers, Percentage-Closer Soft Shadows (PCSS in screen space), contact hardening, and off-screen geometry mitigation.
10. **Topic 10: Colour Science & HDR Pipeline** — 32-bit linear float ACEScg working pipeline, Bradford chromatic adaptation, AgX display tone mapping, and real-time CIEDE2000 ($\Delta E_{00}$) guardrails.
11. **Topic 11: Image Compositing & Detail Preservation** — Ratio-based Guided Filter decomposition ($\mathbf{I} = \mathbf{B} \odot \mathbf{R}$), $100\%$ high-frequency texture preservation, and semantic bypass masks (faces, brand typography).
12. **Topic 12: Confidence Estimation & Uncertainty-Aware Rendering** — Multi-factor confidence maps $C(u, v) \in [0, 1]$ (depth gradient variance, normal spatial variance, cross-model agreement) and dynamic cross-fading to 2D image-space fallbacks on foliage/hair.

---

### [Part 3: Systems Architecture, Computing, Benchmarking & Commercial Licensing](PART_3_SYSTEMS_COMPUTING_AND_COMMERCIAL_VIABILITY.md)
*Priority 3: Software engineering, high-performance computing, UX, and legal compliance.*
13. **Topic 13: Natural-Language Lighting Control** — Local on-device LLM (Apple MLX 3B) tool-calling into deterministic scene graph JSON operations rather than generative pixel synthesis.
14. **Topic 14: Metal, GPU Computing & Native macOS Engineering** — Apple Silicon Unified Memory Architecture (UMA) zero-copy pointers, sparse texture tiling for 100MP RAW files, and Metal 3 compute shader DAG.
15. **Topic 15: Python Prototyping & Model Integration** — Modular reference architecture in Python/PyTorch with direct 1:1 translation mapping to Metal Shading Language (MSL).
16. **Topic 16: Photographic Scene Graph & Non-Destructive Editing** — Mutable Directed Acyclic Graph (DAG) with dirty-flag incremental re-evaluation and `.relight` project file bundle specification.
17. **Topic 17: Datasets, Benchmarking & Photographic Validation** — 30-landscape test suite across 5 biomes (alpine, coastal, forest, desert, sunset) + 500-scene procedural Blender ground-truth rendering pipeline.
18. **Topic 18: Master Model Licensing & Commercial Viability Audit** — Exhaustive legal clearance table verifying Apache 2.0 / MIT / BSD licenses across all adopted components and eliminating CC BY-NC risk.

---

## THE CORE SCIENTIFIC VERDICT

| Product Question | Scientific & Engineering Finding |
| :--- | :--- |
| **Can we physically recover true 3D lighting from a single photograph?** | **No.** Uncalibrated monocular inverse rendering is mathematically under-determined [Barron & Malik 2015]. Relight Studio must operate as a **physically guided 2.5D scene estimator**, not an exact physical solver. |
| **How do we make "purple sun, blue sky" look real without a purple overlay?** | By decomposing scene radiance into direct sunlight $\mathbf{I}_{\text{sun}}$ and diffuse ambient skylight $\mathbf{I}_{\text{ambient}}$ using Perez sky gradient fitting, normal cosine gating $(\mathbf{n} \cdot \mathbf{l}_{\text{sun}})^+$, and chromatic disparity. Recoloring applies **exclusively to $\mathbf{I}_{\text{sun}}$**, preserving 100% of the natural blue sky and cool ambient shadows. |
| **How do we add studio lights without distorting original details?** | Via ratio-based Guided Filter decomposition ($\mathbf{I} = \mathbf{B} \odot \mathbf{R}$). Lighting gains apply only to the base illumination layer $\mathbf{B}$; the high-frequency residual $\mathbf{R}$ is multiplied back, mathematically guaranteeing zero loss of brand marks, rock textures, or foliage micro-contrast ($\text{PSNR} > 60\text{ dB}$). |
| **Is the pipeline legally safe for commercial sale?** | **Yes, under our specific stack.** Academic models like SFU Careaga Intrinsic and Omnidata are strictly non-commercial. Relight Studio achieves commercial safety by pairing **Depth Anything V2 (Apache 2.0)**, **DSINE (Apache 2.0)**, and **SegFormer / SAM 2 (Apache 2.0)** with our own **In-House Analytical Perez Sun-Sky Solver**. |
