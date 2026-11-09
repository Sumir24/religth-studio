# RELIGHT STUDIO — ARCHITECTURAL DECISION LOG & UNRESOLVED QUESTIONS

**Tracking Status:** Active  
**Runtime:** GRAVITAS Engineering Reliability Runtime  

---

## 1. ARCHITECTURAL DECISIONS (ADRs)

### ADR-001: Dual-Engine Strategy (Light Mixer vs. Single-Image)
- **Status:** APPROVED
- **Context:** Single-image uncalibrated inverse rendering cannot physically separate reflections from complex surfaces without geometry. Studio photographers frequently lock cameras on tripods and shoot multiple lights.
- **Decision:** Architect Relight Studio with two first-class engines: Engine 1 (Multi-pass Light Mixer, 100% physically deterministic) and Engine 2 (Guided Single-Image Shaper).
- **Consequence:** Eliminates market risk of single-image limitations while providing high-end commercial studios with an immediate daily workflow tool.

### ADR-002: Analytical Parametric Form Guides vs. Neural Surface Normals
- **Status:** APPROVED
- **Context:** State-of-the-art neural surface normal estimators (DSINE, Omnidata) interpret specular highlights and studio softbox reflections as geometric bumps. On polished metal watches, neural normal fields are severely distorted.
- **Decision:** Use analytical geometric primitives (cylinders, spheres, planes, cones, surfaces of revolution) as the primary surface orientation engine for specular synthesis. Neural normal estimation is strictly an optional preview aid on matte objects.
- **Consequence:** Predictable, smooth, studio-grade specular reflection bands.

### ADR-003: Orthogonal Shading Gain vs. Specular Synthesis
- **Status:** APPROVED
- **Context:** Multiplicative gain alone cannot simulate a softbox reflection on mirror chrome. Additive specular alone cannot deepen shadows on diffuse cardboard.
- **Decision:** Decompose lighting operations into:
  1. Base Shading: Multiplicative gain field $\mathbf{G}(u, v) \in [0, \infty)$ applied to linear diffuse base.
  2. Specular Synthesis: Additive radiance field $\mathbf{S}(u, v) \in [0, \infty)$ derived from reflected ray-tracing onto virtual studio emitters.
- **Consequence:** Clear physical separation matching studio lighting reality.

### ADR-004: Color Management — Linear 32-Bit Float ACEScg Working Space
- **Status:** APPROVED
- **Context:** Blending light in gamma spaces (sRGB, Adobe RGB) produces dark borders and incorrect chromatic saturation.
- **Decision:** All computations execute in scene-referred 32-bit linear floating-point using ACEScg (AP1 primaries, linear transfer function). Tone-mapping occurs only at display presentation.
- **Consequence:** True additive radiometric math; high dynamic range headroom.

### ADR-005: High-Frequency Identity Protection via Guided Filter Decomposition
- **Status:** APPROVED
- **Context:** Lighting adjustments must not wash out logos, dials, engravings, or watch hands.
- **Decision:** Use edge-preserving guided filtering to separate the image into Base Illumination and High-Frequency Detail Residual. Gains are applied only to the Base layer before recombining.
- **Consequence:** Zero distortion of brand marks or fine textures; verified via real-time $\Delta E_{00}$ gating.

### ADR-006: Native Metal 3 Compute Engine (Bypassing Core Image)
- **Status:** APPROVED
- **Context:** Core Image does not offer fine-grained tiled memory control or custom ray-tracing shader dispatch for 100MP files.
- **Decision:** Direct implementation of Metal Shading Language compute kernels, Metal 3 argument buffers, and custom tile allocators.
- **Consequence:** 60 FPS viewport updates at 4K display resolution; memory stays strictly below 2.8 GB on 150MP files.

---

## 2. UNRESOLVED QUESTIONS REGISTER

| ID | Topic | Question | Impact | Resolution Plan / Experiment |
| :--- | :--- | :--- | :--- | :--- |
| **UQ-01** | **Glass Caustics** | Can internal glass reflections and caustics on transparent perfume bottles be approximated convincingly from single images without full ray-traced refraction? | High on cosmetics/perfume segment | Experiment EXP-09 in Python prototype sandbox. |
| **UQ-02** | **Clipped RAW Highlights** | When existing studio highlights are burned out ($> 1.0$), how should the engine handle them when negative fill is applied? | Retouching edge case | Test threshold-based highlight clamp vs. soft roll-off preservation in EXP-01. |
| **UQ-03** | **Anisotropic Directionality** | How should users specify brushed metal orientation across curved watch lugs without complex UV unwrapping? | Watch retouching usability | Implement a 2D tangent vector flow field generator driven by guide boundaries. |
| **UQ-04** | **Capture One Live Tethering** | Can Relight Studio watch a session folder and automatically assemble multi-pass Light Mixer stacks as the photographer triggers flashes? | Studio workflow speed | Prototype a folder-watchdaemon and test metadata tagging via AppleScript / CLI. |
