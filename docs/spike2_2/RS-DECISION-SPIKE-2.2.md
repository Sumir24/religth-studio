# RELIGHT STUDIO — RS-SPIKE-2.2
## Formal Architectural Decision & Production Readiness Milestone

- **Document ID:** RS-DECISION-SPIKE-2.2-v1.0
- **Status:** FORMAL ARCHITECTURAL MILESTONE DECISION
- **Author:** Principal Computational Photography Architect & Independent Experimental Auditor
- **Date:** 2026-11-09
- **Evidence Base:**
  - Audit: `docs/spike2_2/RS-REP-SPIKE-2.2-FORENSIC-AUDIT.md`
  - Metrics Spec: `docs/spike2_2/RS-SPEC-SPIKE-2.2-METRICS.md`
  - Architecture Spec: `docs/spike2_2/RS-SPEC-SPIKE-2.2-ARCHITECTURE.md`
  - Performance Benchmark: `docs/spike2_2/RS-REP-SPIKE-2.2-PERFORMANCE.md`
  - Results Report: `docs/spike2_2/RS-REP-SPIKE-2.2-RESULTS.md`
  - Failure Analysis: `docs/spike2_2/RS-REP-SPIKE-2.2-FAILURE-ANALYSIS.md`

---

### 1. Formal Architectural Verdict

Following an independent experimental audit of 29 benchmark scenes, 10 isolated component ablation configurations, and native Apple Silicon Metal hardware micro-benchmarking, the formal decision for RS-SPIKE-2.2 is:

$$\Large \mathbf{OPTION\; B:\; CONDITIONALLY\; VALIDATED}$$

This decision acknowledges both the verified mathematical breakthroughs of the repaired pipeline and the definitive physical limits of 2.5D image-space geometry.

---

### 2. Component-by-Component Readiness Breakdown

| Architectural Component | Spike 2.2 Status | Empirical Evidence Summary | Production Disposition |
| :--- | :---: | :--- | :--- |
| **1. Multi-Scale Horizon Ambient Occlusion ($A_{\text{amb}}$)** | **VALIDATED** | Multi-ring depth horizon search eliminates cavity halos; maintains $DCI \ge 0.998$ across all test scenes. | **Deploy to Production Engine.** Integrate directly into studio ambient pipeline. |
| **2. Additive Radiance Compositing Formulation** | **VALIDATED** | Radiance separation ($Y_{\text{indirect}} = Y_b \cdot R_{\text{amb}} \cdot A_{\text{amb}}$) permanently eliminates contact bleeding into ambient bounce. | **Deploy to Production Engine.** Supersedes legacy multiplicative shading ratios. |
| **3. Planar Contact Grounding ($C_{\text{contact}}$)** | **CONDITIONALLY VALIDATED** | Passes on all flat tabletop scenes ($CGS \le 0.0412$, $SDG = 0.0\text{ px}$). Fails on non-planar reliefs ($SDG = 25\text{ px}$) and recessed lug soles ($CGS = 0.19$). | **Deploy with Guardrails.** Enable strictly when a planar floor interface is confirmed. Disable for wall-mounted reliefs and free-floating objects. |
| **4. Lit-Side Silhouette Bleed Guard** | **VALIDATED** | Half-space lit normal mask eliminates backward shadow leaks on grounded spheres, shoes, and cylinders ($SLR = 0.00\%$). | **Deploy to Production Engine.** Mandatory post-projection stencil mask. |
| **5. 2.5D Image-Space Cast Shadow Engine ($V_{\text{cast}}$)** | **REJECTED FOR GENERAL 3D USE**<br>*(Provisional Tabletop Only)* | Fails 3D ground truth across 25 of 26 synthetic scenes ($SDE = 3.67 - 48.33\text{ px}$, $\text{IoU} = 0.00 - 0.77$). Cannot project onto curved cycloramas ($SLR = 12.66\%$). | **Downgrade to Provisional.** Gate behind confidence attenuation for basic planar shadows. Must be superseded by Spike 3 parametric proxies for production 3D lighting. |
| **6. Apple Silicon Metal GPU Performance** | **VALIDATED FOR INTERACTIVE VIEWPORTS** | Preview: **$3.49\text{ ms}$ (286.5 FPS)**.<br>1080p: **$32.08\text{ ms}$ (31.2 FPS)**.<br>VRAM: $56.0\text{ MB}$ at 1080p. | **Deploy to Production Engine.** Target Metal compute shaders for viewport; offline batch queue for 4K ($135.68\text{ ms}$). |

---

### 3. Required Architectural Mitigations for Production Integration

Before any code from Spike 2.2 is merged into the production engine (`engine/relighter_v4.py`), the following engineering gates are mandatory:

1. **Gate M1: Receiver Geometric Classification**
   - The pipeline must analyze estimated normal and depth gradients in the background region. If normal variance indicates a curved cyclorama cove or non-planar terrain, the 2.5D planar projection must be automatically replaced by a cylindrical/parametric receiver warp.
2. **Gate M2: Continuous Confidence Fallback**
   - In areas where depth-cliff magnitude exceeds the threshold ($|\nabla Z| > 0.04$), the cast shadow visibility $V_{\text{cast}}$ must be linearly blended toward the original background luminance using $U_{\text{geom}}$ to prevent visible black seams.
3. **Gate M3: Contact Crevice Adaptive Radius**
   - For footwear soles with lug textures, the contact grounding search radius must scale inversely with local normal variance to prevent shadow bleed into non-contacting sole voids.

---

### 4. Transition Plan to Spike 3

With the completion of RS-SPIKE-2.2, Relight Studio has established a mathematically defensible diffuse and ambient foundation.
The project will immediately proceed to **Spike 3: Physically Based Specular Reflection & 3D Parametric Proxies**, addressing:
1. Microfacet Cook-Torrance / GGX specular BRDF driven by estimated roughness and metallic priors.
2. Lightweight 3D parametric geometric proxies (ellipsoids, bounding boxes, CAD priors) to achieve sub-millimeter cast shadow accuracy ($SDE \le 3.0\text{ px}$, $\text{IoU} \ge 0.85$) on arbitrary curved receivers.
