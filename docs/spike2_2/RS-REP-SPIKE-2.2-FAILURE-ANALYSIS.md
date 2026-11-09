# RELIGHT STUDIO — RS-SPIKE-2.2
## Structural Failure Analysis & Physical Limitations of 2.5D Image-Space Transport

- **Document ID:** RS-REP-SPIKE-2.2-FAILURE-ANALYSIS-v1.0
- **Status:** APPROVED / ROOT CAUSE INVESTIGATION
- **Author:** Principal Physically Based Rendering Engineer & Numerical Methods Researcher
- **Harness Reference:** `spike2_2/spike2_2_candidate.py`, `spike2_2/spike2_2_evaluation.py`
- **Output Artifacts:** `spike2_2_output/contact_sheets/`

---

### 1. Executive Summary & Purpose

The purpose of this failure analysis is to determine the exact mathematical and physical boundaries beyond which a 2.5D image-space lighting model breaks down.
Rather than attempting to force 2.5D heuristics to pass arbitrary 3D benchmarks, this report documents why 2.5D image-space methods are fundamentally incapable of general-purpose 3D shadow transport and establishes clear operating envelopes for production engineering.

---

### 2. Deep Root-Cause Dissection of Edge Case Failures

```
                              THE 2.5D DEPTH-CLIFF PARADOX
                              
           Light Vector L (Key)
               \
                \     [ Occluder Silhouette ]
                 \   +----------------------+
                  \  |                      |
                   \ |      2.5D Front      |
                    \|      Visible Face    |
                     +----------------------+ <--- Depth Cliff Seam (dZ >> threshold)
                      \         |
                       \        | Occluded Back Face (UNKNOWN to 2.5D)
                        \       |
                         \      v
    ----------------------\----------------------- Floor Plane
                           \
                            +====== Cast Shadow Zone
```

#### Edge Case 1: Hovering Objects & Elevation Sweep (S2: $h = 0.05 \to 0.50$)
- **Empirical Symptoms:**
  - Elevation $h = 0.00$: $SLR = 0.00\%$, $SDE = 5.57\text{ px}$, $\text{IoU} = 0.6616$.
  - Elevation $h = 0.05$: $SLR = 2.77\%$, $SDE = 10.26\text{ px}$, $\text{IoU} = 0.4960$.
  - Elevation $h = 0.20$: $SLR = 8.42\%$, $SDE = 21.70\text{ px}$, $\text{IoU} = 0.1830$.
  - Elevation $h = 0.50$: $SLR = 16.60\%$, $SDE = 48.33\text{ px}$, $\text{IoU} = 0.0000$ (Complete shadow detachment failure).
- **Mathematical Root Cause:**
  - A 2.5D heightfield contains depth only for the camera-facing hemisphere.
  - When the sphere is grounded ($h=0$), the contact seam anchors the planar projection.
  - As elevation increases ($h > 0$), true 3D ray tracing projects rays from the sphere's actual 3D center of mass. In 2.5D image space, however, the floor contact line is missing; the projection algorithm must guess the receiver intersection solely from the lowest foreground boundary pixel and estimated depth.
  - Perspective parallax causes the projected shadow to shear away from the true 3D umbra, resulting in a $48.33\text{ px}$ centroid offset and $0.00$ IoU overlap at $h=0.50$.

#### Edge Case 2: Multi-Contact Bench & Inter-Object Shadowing (S7)
- **Empirical Symptoms:** $SLR = 19.23\%$ (FAIL), $SDE = 8.41\text{ px}$, $\text{IoU} = 0.5632$.
- **Mathematical Root Cause:**
  - The scene features 4 vertical legs and a horizontal crossbar.
  - When light arrives at an angle, the front left leg casts a shadow that must travel across the floor and partially strike the rear leg.
  - In a 2.5D image-space shear projection, the entire foreground mask is treated as a single rigid 2D slab. The shadow cast by the front leg shears backwards and lands across the lit background cliff pixels behind the rear leg, violating the lit-side guard because the rear leg has a different depth plane.
  - 2.5D image space cannot handle *caster-on-caster* or *multi-depth occluder chains*.

#### Edge Case 3: Curved Cyclorama Cove & Non-Planar Receivers (S11)
- **Empirical Symptoms:**
  - Medium Ground: $SLR = 4.03\%$ (FAIL), $SDE = 5.22\text{ px}$, $\text{IoU} = 0.6671$.
  - Long Shadow: $SLR = 12.66\%$ (FAIL), $SDE = 7.27\text{ px}$, $\text{IoU} = 0.6406$.
- **Mathematical Root Cause:**
  - Studio photographers use curved cyclorama coves (infinity walls) to avoid harsh horizon lines.
  - A 2.5D planar proxy assumes a horizontal receiver plane $Y = \text{ground\_y}$.
  - In reality, the cyclorama curves smoothly upward from horizontal floor ($N = [0, 1, 0]$) to vertical wall ($N = [0, 0, -1]$).
  - When the key light casts a long shadow, the true 3D shadow runs across the floor and curves *up* the vertical back wall. The 2.5D planar projection continues flat across the image, stretching horizontally and bleeding into the curved wall background ($SLR = 12.66\%$).

#### Edge Case 4: Extreme Camera Angles & Foreshortening (S12)
- **Empirical Symptoms:**
  - Eye Level ($15^\circ$ pitch): $SLR = 15.29\%$, $SDE = 17.17\text{ px}$, $\text{IoU} = 0.2766$.
  - Studio Standard ($45^\circ$ pitch): $SLR = 0.00\%$, $SDE = 5.57\text{ px}$, $\text{IoU} = 0.6616$.
  - Top Down ($85^\circ$ pitch): $SLR = 20.35\%$, $SDE = 38.46\text{ px}$, $\text{IoU} = 0.1642$.
- **Mathematical Root Cause:**
  - At Eye Level, the ground plane is viewed at extreme grazing angles. A small 3D shadow displacement corresponds to a massive vertical compression in 2D image coordinates, amplifying ray marching quantization errors.
  - In Top-Down views, the floor plane is perpendicular to the line of sight, but the subject's height extends directly toward the camera along the Z axis. The 2.5D planar shear projection projects along $L_{xy}$, producing an artificial shadow elongation that does not account for the steep orthographic foreshortening of the top-down perspective matrix.

#### Edge Case 5: Real Photographic Footwear & Relief Terrain (R1 & R3)
- **Empirical Symptoms:**
  - R1 Sneaker: $CGS = 0.1900$ (FAIL), $SLR = 15.68\%$ (FAIL).
  - R3 Architectural Relief: $CGS = 0.1900$ (FAIL), $SDG = 25.00\text{ px}$ (FAIL), $SLR = 12.43\%$ (FAIL).
- **Mathematical Root Cause:**
  - *R1 Sneaker Sole Lugs:* Sneaker soles are not flat plates; they possess deep tread channels (waffle/herringbone lugs). The contact grounding heuristic assumes a continuous contact edge. In reality, the lugs touch the ground, while the 2–5mm recessed channels do not. Monocular depth estimation smooths across these micro-crevices, causing the contact grounding term to bleed into the tread voids and failing the $CGS \le 0.15$ threshold.
  - *R3 Architectural Relief:* Vertical stone carving mounted on a wall has no horizontal floor receiver whatsoever. The planar ground model attempts to project shadows onto an imaginary floor at $Y = 352\text{ px}$, resulting in a severe $25.0\text{ px}$ detachment gap from the carving reliefs.

---

### 3. The Fundamental 2.5D Barrier

The empirical evidence from RS-SPIKE-2.2 conclusively establishes what can and cannot be achieved within a 2.5D image-space representation:

```
+---------------------------------------------+---------------------------------------------+
|    WHAT 2.5D IMAGE SPACE CAN DO WELL        |    WHAT 2.5D IMAGE SPACE CANNOT DO          |
|    (READY FOR PRODUCT USE)                  |    (REQUIRES 3D PARAMETRIC PROXIES)         |
+---------------------------------------------+---------------------------------------------+
| 1. Local Ambient Occlusion (Cavities)       | 1. Non-planar receiver projection (Cycloramas)|
| 2. Contact Grounding on flat studio floors  | 2. Floating / hovering object shadows       |
| 3. High-noon / steep overhead shading       | 3. Inter-object occluder chains (Legs/Bars) |
| 4. Diffuse surface orientation re-lighting  | 4. Extreme camera angles (<20 deg or >80 deg)|
| 5. Specular highlight suppression/re-map    | 5. Deeply lugged / non-continuous contact   |
+---------------------------------------------+---------------------------------------------+
```

---

### 4. Architectural Boundaries & Safe Operating Envelope for Production

To prevent visual artifacts and customer dissatisfaction in Relight Studio, the rendering pipeline must enforce the following runtime constraints:

1. **Planar Studio Assumption:**
   - The 2.5D cast shadow engine is restricted to **studio tabletop product photography** where the subject rests on a verified planar surface.
2. **Confidence-Gated Shadow Attenuation:**
   - When the geometric confidence map $U_{\text{geom}}$ drops below $0.40$ (detected at depth boundaries, grazing angles, or background cliffs), the cast shadow term $V_{\text{cast}}$ must be smoothly clamped to the original ambient luminance rather than forced to zero.
3. **Contact Seam Fallback:**
   - On scenes without a detected ground contact interface (such as wall-mounted reliefs, airborne subjects, or pure headshots), cast shadow projection must be disabled automatically, retaining only Ambient Occlusion ($A_{\text{amb}}$) and Diffuse Relighting ($D$).
4. **Handoff to Spike 3 (3D Parametric Proxies):**
   - For premium studio lighting features (e.g. cyclorama sweeps, hovering shoes, multi-light studio rigs), Relight Studio must incorporate lightweight 3D parametric geometric proxies (ellipsoids, bounding boxes, or coarse NeRF/mesh priors) to compute true 3D ray traced shadows.
