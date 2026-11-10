# RS-SPIKE-3B: Next Milestone Architecture Recommendation

**Milestone:** RS-SPIKE-3B — Geometric Lighting Fidelity & Scene Interaction  
**Role:** Principal Computational Photography Architect & Rendering Systems Specialist  
**Target Milestone:** **RS-SPIKE-3C — Multi-Light Rig Architecture & Physically Based Specular Response**  
**Date:** November 2026  

---

## 1. Executive Context & Recommendation

RS-SPIKE-3B has resolved the geometric, shadow transport, radiometry, and interaction latency challenges that previously limited the hybrid virtual studio foundation. The platform now possesses:
- A rock-solid, watertight geometry intersection pipeline (normalized superquadrics, oriented bounding boxes, low-poly footwear proxy meshes, and cyclorama cove receivers).
- A sub-millisecond, native Apple Silicon Metal compute engine ($0.87\,\text{ms}$ preview, $7.24\,\text{ms}$ 1080p final render).
- Strict bitwise zero-mutation guarantees on protected regions ($0.0000000000$).
- Radiometrically verified area-light illumination with smooth penumbra scaling and calibrated blackbody color temperatures.

**Recommendation:** The single-light virtual studio foundation is technically proven and production-ready. We recommend advancing immediately to:

**RS-SPIKE-3C: Multi-Light Rig Architecture & Physically Based Specular Response**

---

## 2. Component Readiness & Architectural Freezing Status

| Component | Status | Recommendation |
| :--- | :---: | :--- |
| **Normalized Superquadric Root Solver** | Production Ready | **Freeze.** Retain scale-normalized metric $G(p)$ with 32 interval steps + 4 bisections. |
| **Cyclorama Receiver Intersections** | Production Ready | **Freeze.** Retain cove tangent continuity and $\pm 10^{-4}\,\text{m}$ tolerance padding. |
| **Metal GPU Shading & Shadow Ray Engine** | Production Ready | **Freeze core kernel.** Extend buffer parameters for multi-light array. |
| **Stratified Emitter Center Sampling** | Production Ready | **Freeze.** Retain low-discrepancy cell-center grid for interactive determinism. |
| **Bitwise Protected-Region Masking** | Production Ready | **Freeze.** Retain hardware-level pass-through guarantee. |
| **Scene State Transaction Manager** | Production Ready | **Freeze.** Retain JSON serialization and discrete undo/redo stack. |
| **Single-Light Lambertian Illumination** | Milestone Complete | **Extend.** Expand to multi-light rig and physically based specular response. |

---

## 3. Scope & Objectives for RS-SPIKE-3C

Commercial photography rarely relies on a single light source. Professional studio photography utilizes coordinated **3-point or 4-point lighting rigs** (Key Light, Fill Light, Rim/Kicker, and Background Accent) and demands realistic specular highlights on glossy or metallic products (watches, cosmetics, polished leather, glassware).

### In-Scope Objectives for RS-SPIKE-3C:
1. **Multi-Light Rig Orchestration:**
   - Support up to 4 concurrent virtual area lights (Key, Fill, Rim, Background).
   - Independent transformation gizmos, Kelvin color temperatures, dimensions, and intensities.
   - Unified single-pass Metal GPU compute shader accumulating multi-light irradiance and visibility without separate dispatch passes.
2. **Physically Based Specular Decomposition & Microfacet Response:**
   - Extend surface shading beyond pure diffuse Lambertian transport by integrating an energy-conserving microfacet specular model (GGX / Cook-Torrance distribution).
   - Estimate surface roughness and specular albedo from estimated monocular normal variation and photographic luminance.
   - Non-destructive specular highlight synthesis: additive high-frequency specular lobes regularized by surface roughness to avoid blown-out specular clipping.
3. **Interactive 3D Stage Viewport Multi-Light Gizmos:**
   - Multi-light selection and manipulation in the 3D studio stage.
   - Visual light frustums showing directional coverage and soft falloff cones for each active emitter.
4. **Photographic Product Validation:**
   - Dedicated validation on highly reflective and metallic product plates (chronograph watches, glossy cosmetic containers, lacquered surfaces).

### Explicit Out-of-Scope Boundaries:
- **No Unrestricted Generative Inpainting:** Do not use diffusion models or hallucinated image generation. Shading consequences must remain strictly physically computed from artist-placed lights.
- **No Offline Path Tracing:** Maintain real-time interactive preview budget ($\le 16.6\,\text{ms}$ on Apple Silicon GPU).
- **No Automated Photogrammetry Reconstruction:** Proxy geometry remains parametric and artist-controlled.

---

## 4. Proposed RS-SPIKE-3C Acceptance Gates

1. **Multi-Light Parity & Energy Accumulation:** CPU and Metal irradiance MAE across a 3-light rig $\le 0.001$.
2. **Multi-Light Interactive Preview Latency:** GPU P95 latency for 3 active area lights $\le 8.0\,\text{ms}$ at $1024 \times 576$; end-to-end host wall latency $\le 16.6\,\text{ms}$ (60 FPS).
3. **Specular Energy Conservation:** Total reflected radiance (diffuse + specular) $\le$ incident irradiance across all surface normals ($\max(R_{\text{diffuse}} + R_{\text{specular}}) \le 1.0$).
4. **Specular Highlight Plausibility:** Specular highlights track light movement across curved surfaces with sub-pixel continuity; no highlight banding or aliasing.
5. **Protected-Region Immutability:** Bitwise identical zero-mutation guarantee preserved ($0.0000000000$).
6. **Photographic Metallic/Glossy Plate Validation:** Tested on at least 2 real product photographs featuring metallic or glossy materials with $\text{DCI} \ge 0.90$.
