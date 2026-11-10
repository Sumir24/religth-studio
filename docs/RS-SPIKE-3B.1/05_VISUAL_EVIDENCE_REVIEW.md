# RELIGHT STUDIO — RS-SPIKE-3B.1 AUDIT DELIVERABLE
# 05: VISUAL EVIDENCE REVIEW & DEFECT CATALOG

**Author:** Principal Computational Photography Engineer & Visual Quality Auditor  
**Date:** November 10, 2026  
**Audited Checkpoint:** `efed4ed` (RS-SPIKE-3B)  
**Artifact Directory:** `docs/RS-SPIKE-3B.1/visual_boards/`  
**Inspected Boards:**
- `P1_nike_sneaker_audit_board.png` ($1728 \times 2048\text{ px}$)
- `P2_classical_statue_audit_board.png` ($1728 \times 2048\text{ px}$)
- `P3_architectural_relief_audit_board.png` ($2304 \times 1024\text{ px}$)
- `M2_03_cosmetic_bottle_cyclorama_audit_board.png` ($2304 \times 1152\text{ px}$)
- `M2_04_sneaker_mesh_plane_audit_board.png` ($2304 \times 1152\text{ px}$)

---

## 1. EXECUTIVE SUMMARY

Independent visual inspection was conducted across all generated contact sheets, comparing:
1. Original Photographic/Synthetic Plate
2. Metal GPU Relit Output (FINAL 64 samples)
3. $5\times$ Amplified Absolute Difference Map
4. Direct Shadow Visibility Field
5. 3D Geometric Proxy Alignment Wireframe

### Key Visual Takeaways:
- **Photographic Believability:** Case P2 (Classical Statue) and Case P3 (Architectural Relief) demonstrate photographic-grade lighting transitions, smooth penumbra falloff, and natural contact darkening.
- **The Sneaker Texture Defect (P1):** Visual inspection corroborates the quantitative failure identified in Phase 4 (Foreground $\text{DCI} = 0.8282$). The shoe upper exhibits high-frequency modulation noise ("texture crunch") and edge haloing around the outsole perimeter.
- **Cove Continuity:** The cyclorama fillet cove transition is geometrically seamless, with zero visible seams or normal popping across the floor-to-cove interface.

---

## 2. CATALOG OF OBSERVED VISUAL DEFECTS

| Defect ID | Defect Category | Manifesting Scene(s) | Visual Description | Root Cause | Severity |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **DEF-01** | Shading Noise / Texture Crunch | `P1_nike_sneaker` | Fabric knit texture on the shoe upper exhibits localized contrast clumping and noisy micro-shadows. | Omission of E.1 Guided-Filter Regularizer in Metal shader; noisy monocular depth normals directly multiply original RGB. | **High** |
| **DEF-02** | Contact Haloing | `P1_nike_sneaker` | A faint dark fringe ($2-4\text{ px}$ wide) bleeds into the ground plane around the heel and collar. | Geometric mismatch between the coarse 280-triangle footwear hull proxy and the actual photographic silhouette. | **Medium** |
| **DEF-03** | Penumbra Discretization at Grazing Angles | `S5_grazing_oblique_light` | At extreme grazing angles ($15^\circ$ elevation), faint concentric banding is visible in the distant penumbra. | 64-sample stratified grid layout without randomized per-pixel jitter in production FINAL mode. | **Low** |
| **DEF-04** | Specular Red Saturation Clipping | `P1_nike_sneaker` | Bright directional relighting causes saturated orange/red clipping on the shoe vamp highlights. | Naive linear power-law tonemapping without C3 Oklab constant-hue gamut compression in the main render kernel. | **Medium** |
| **DEF-05** | Silhouette Normal Discontinuity | `P1`, `M2_04` | At grazing silhouette boundaries, surface normals abruptly flip, creating sharp single-pixel dark boundary lines. | Finite difference gradient estimation on monocular depth maps at depth discontinuities. | **Medium** |

---

## 3. SYSTEMATIC SCENE-BY-SCENE AUDIT

### 3.1. Plate P1: Footwear Subject (`P1_nike_sneaker`)
- **Visual Rating:** **$3.0 / 5.0$** (Acceptable for prototype, below production photographic standard)
- **Strengths:** Cast shadow grounding on the floor plane is geometrically plausible; light directionality convincingly alters shoe warmth.
- **Flaws:**
  - Noticeable micro-contrast degradation on the woven fabric upper.
  - Dark contact halo around the heel sole caused by proxy misalignment.
  - Saturated highlight blowout on red leather trim.

### 3.2. Plate P2: Classical Marble Statue (`P2_classical_statue`)
- **Visual Rating:** **$4.8 / 5.0$** (Near production grade)
- **Strengths:**
  - Warm $3200\text{ K}$ key light from upper-left produces gorgeous volumetric modeling across the statue's muscular anatomy and drapery.
  - Cast shadow onto the curved cyclorama cove is smooth, soft, and completely free of stepping or banding.
  - Contact occlusion at the pedestal base grounds the subject naturally with no bright or dark halos.
- **Flaws:** Slight normal noise on the furthest receded drapery fold.

### 3.3. Plate P3: Architectural Stone Relief (`P3_architectural_relief`)
- **Visual Rating:** **$4.7 / 5.0$** (Professional quality)
- **Strengths:**
  - $6500\text{ K}$ side light accentuates the carved masonry reliefs with crisp, natural micro-shadows.
  - Zero texture smoothing; stone grain and chisel marks remain sharp.
- **Flaws:** Minor edge darkening on the extreme right border where depth extrapolation ends.

### 3.4. Canonical M2_03: Cosmetic Bottle on Cyclorama Cove
- **Visual Rating:** **$4.9 / 5.0$** (Flawless synthetic execution)
- **Strengths:**
  - The superquadric proxy ($e_1 = 0.3, e_2 = 1.0$) casts an impeccably shaped bottle shadow with a soft cylindrical cap penumbra.
  - Cove curve ($Z = -0.80$ to $-1.20\text{ m}$) seamlessly bends the shadow up the vertical studio wall.
  - Superellipse contact grounding matches the base cross-section perfectly.
- **Flaws:** None observed.

### 3.5. Canonical M2_04: Sneaker Hull Mesh on Planar Receiver
- **Visual Rating:** **$4.2 / 5.0$** (Robust geometric transport)
- **Strengths:**
  - 280-triangle hull casts a true asymmetrical footwear shadow with arch cutout and ankle taper.
  - Hard core umbra transitions smoothly into a broad outer penumbra.
- **Flaws:** Slight contact boundary sharpness along the lateral outsole.

---

## 4. PHOTOGRAPHER EXPECTATIONS VS SYSTEM REALITY

| Studio Photography Requirement | Relight Studio Measured Capability | Verdict |
| :--- | :--- | :---: |
| **Natural Shadow Softness:** Shadows must soften with distance from the subject according to light size. | Fully supported by physical area light sampling ($N=64$). Penumbra width scales accurately with emitter dimensions. | **MEETS EXPECTATIONS** |
| **Material & Micro-texture Preservation:** Fabric, leather, and skin pores must not be erased or artificially sharpened. | Supported on smooth organic surfaces (P2, P3), but **degraded on high-frequency woven textures (P1)** due to lack of E.1 regularizer. | **NEEDS IMPROVEMENT** |
| **Contact Crevice Grounding:** Objects must not appear to float or sink into the floor plane. | Superquadric and superellipse contact heuristics provide convincing grounding without light leaks. | **MEETS EXPECTATIONS** |
| **Color Temperature Accuracy:** Warm/cool lights must obey blackbody physics without clipping or hue shifting. | Linear blackbody conversion is mathematically exact; however, highlight gamut mapping requires integration. | **PARTIALLY MEETS** |
