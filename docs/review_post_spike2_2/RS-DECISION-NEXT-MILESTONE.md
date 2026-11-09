# RELIGHT STUDIO — ARCHITECTURAL MILESTONE DECISION
## Next Milestone Roadmap, Sequencing & Execution Authorization

- **Document ID:** RS-DECISION-NEXT-MILESTONE-v1.0
- **Status:** RATIFIED ARCHITECTURAL DECISION & EXECUTION ROADMAP
- **Author:** Principal Computational Photography Architect & Rendering Systems Auditor
- **Date:** 2026-11-09
- **Governing Audits:** RS-REP-POST-SPIKE-2.2-INDEPENDENT-REVIEW.md, RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md

---

### 1. Executive Summary & Context

The post-Spike 2.2 independent architecture audit clearly separated verified capabilities from physical dead ends:
1. **The 2.5D Image-Space Cast Shadow Engine is Dead for General Lighting:** With an average $SDE$ of $13.4\text{ px}$ and systematic failure on curved cyclorama coves ($SLR = 12.66\%$), attempts to optimize 2D heightfield shear projections have reached their mathematical limit. Shadow transport requires analytical 3D volumetric proxies.
2. **PyTorch MPS is Unviable for Production Interactive Relighting:** With genuine gamut bisection taking $239.24\text{ ms}$ (due to $112+$ kernel dispatches), the Python/MPS research harness cannot support real-time slider manipulation. A native Metal engine is required.
3. **Specular BRDF Transport is Essential for Photographic Realism:** Diffuse-only relighting leaves original specular highlights static, undermining physical plausibility.

---

### 2. Milestone Evaluation & Strategic Alignment

Three independent proposals were generated to address these core requirements:
- **RS-SPIKE-3A:** Parametric 3D Proxy & Geometry-Aware Shadow Transport.
- **RS-SPIKE-3B:** Specular PBR, Microfacet Reflection & Material Decomposition.
- **RS-METAL-2:** Native Metal Shading Language & Real-Time GPU Engine.

#### Dependency & Risk Matrix:

```
+---------------------------------------------------------------------------------------------------+
| MILESTONE     | TECHNICAL GOAL                  | BLOCKING DEPENDENCY  | PARALLEL CAPABILITY      |
+---------------------------------------------------------------------------------------------------+
| RS-SPIKE-3A   | Solve SDE <= 2.0px & Cycloramas | Spike 2.2 Ref Tracer | Can run immediately      |
+---------------------------------------------------------------------------------------------------+
| RS-METAL-2    | Native MSL Engine (< 16ms 1080p)| CAHRA Architecture   | Can run in parallel      |
+---------------------------------------------------------------------------------------------------+
| RS-SPIKE-3B   | GGX Specular Highlights & Inpaint| CAHRA Specular Layer | Sequential after 3A & M2 |
+---------------------------------------------------------------------------------------------------+
```

---

### 3. Sequencing Recommendation & Execution Roadmap

```
+===================================================================================================+
|                                    NEXT MILESTONE ROADMAP                                         |
+===================================================================================================+

    TRACK 1: GEOMETRIC ACCURACY TRACK                TRACK 2: HIGH-PERFORMANCE BACKEND TRACK
    ---------------------------------                ---------------------------------------
    RS-SPIKE-3A (Parametric 3D Proxies)              RS-METAL-2 (Native MSL Engine)
    - OBB, Superquadric, Capsule fitting             - Native .metal compute shaders
    - Curved cyclorama cove ray tracing              - Hybrid 33^3 LUT Oklab kernel (< 1.0 ms)
    - Target: SDE <= 2.0 px, IoU >= 0.90             - Target: 1080p < 16.6 ms (60 FPS)
                   |                                                    |
                   +------------------------+---------------------------+
                                            |
                                            v
                            CONVERGENCE & INTEGRATION POINT
                                            |
                                            v
                           RS-SPIKE-3B (Specular PBR & Material Decomposition)
                           - Cook-Torrance GGX microfacet highlights
                           - Baked highlight suppression & inpainting
                           - Area-light softbox reflection shaping
                           - Native Metal PBR shader integration
                                            |
                                            v
                           PRODUCTION ENGINE INTEGRATION (v4.5 / v5.0)
```

---

### 4. Immediate Decision: What Starts First?

#### Primary Immediate Milestone:
$$\Large \mathbf{RS-SPIKE-3A:\; Parametric\; 3D\; Proxy\; \&\; Geometry-Aware\; Shadow\; Transport}$$

**Rationale for Prioritizing Spike 3A:**
1. **Core Product Vulnerability:** Commercial studio photography lives or dies by its contact grounding and cast shadows. In Spike 2.2, cast shadows failed 25 of 26 synthetic scenes and leaked severely onto cyclorama backdrops. Until shadow transport is physically believable, higher rendering framerates merely accelerate the display of incorrect images.
2. **Deterministic Mathematical Scope:** The analytical proxy ray tracer (OBB, Superquadric, Cyclorama fillet) can be validated rapidly against the existing Spike 2.2 reference ground-truth ray tracer.
3. **Direct Input to Engine Design:** The geometric proxy parameters produced by Spike 3A define the exact shader uniforms needed by RS-METAL-2.

#### Concurrent Secondary Milestone (Parallel Track):
$$\Large \mathbf{RS-METAL-2:\; Native\; Metal\; Performance\; \&\; GPU\; Pipeline}$$
The performance team can concurrently develop the native Metal Shading Language kernels (specifically the Hybrid 3D LUT Oklab gamut mapper, which has zero geometric dependencies) so that the engine backend is ready the moment Spike 3A finishes.

---

### 5. Architectural Mandate & Guardrails

To prevent repeating the errors documented in Spike 2.1 and 2.2, the following rules are permanently ratified:

1. **Rule of Experimental Ground Truth:**
   Never evaluate an algorithm against a mock condition or self-referential metric. Cast shadow accuracy must always be evaluated against true 3D Monte Carlo ray tracing.
2. **Rule of Native Hardware Verification:**
   Never claim "Metal performance" based on high-level Python wrappers (PyTorch MPS) running synthetic toy kernels. Performance claims require native Metal timestamps from Xcode Instruments.
3. **Rule of Architectural Decoupling:**
   Do not merge experimental prototype code into the production engine (`engine/relighter_v4.py`) until both RS-SPIKE-3A and RS-METAL-2 have passed their quantitative acceptance gates.

---

*Decision ratified and signed off by Principal Computational Photography Architect & Independent Systems Auditor.*
