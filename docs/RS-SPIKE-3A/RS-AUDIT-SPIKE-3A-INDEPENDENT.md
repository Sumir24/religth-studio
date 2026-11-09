# RELIGHT STUDIO — RS-SPIKE-3A
## Independent Source-Level Audit & Forensic Verification Report

**Auditor:** Independent Principal Computational Photography Architect & Systems Reviewer  
**Milestone:** RS-SPIKE-3A  
**Target Codebase:** `studio3a/`, `experiments/RS-SPIKE-3A/`, `docs/RS-SPIKE-3A/`  
**Date:** November 9, 2026  
**Status:** Audit Complete — Formal Finding: **CONDITIONAL PASS WITH CRITICAL DEFECTS IDENTIFIED**

---

### 1. Executive Summary & Audit Mandate

An independent source-level audit of the RS-SPIKE-3A implementation, benchmark outputs, and documentation was conducted. The mandate was to verify whether the source code and raw data support the assertions made in the milestone reports, specifically interrogating:
1. Shadow boundary ($SDE$) and shape ($\text{IoU}$) failures.
2. The suspicious uniform zero Contact Grounding Scores ($CGS = 0.000$).
3. Detail Correlation Index ($DCI$) threshold discrepancies between raw data and executive summaries.
4. Physical validity of the geometric visibility and contact occlusion implementations.
5. Authoritative scene state integrity in the dual-viewport interactive workspace.
6. Independent reproducibility of reported zero-mutation and deterministic replay guarantees.

---

### 2. Forensic Audit Findings

```
+----------------------------------------------------------------------------------------------------------------+
| AUDIT ITEM                           | FINDING / DEFECT LEVEL | ROOT CAUSE                                      |
+--------------------------------------+------------------------+-------------------------------------------------+
| 1. Shadow SDE & IoU in S3A_01        | CRITICAL DEFECT        | Unprojected sky pixels defaulted to [0,0,0],    |
|                                      |                        | falsely shadowed beneath the proxy.             |
| 2. Uniform Zero CGS (0.000)          | METRIC PATHOLOGY       | Evaluated np.min over a broad 5-row box;        |
|                                      |                        | any shadow pixel trivially forces 0.000.        |
| 3. DCI Threshold Inconsistencies     | REPORTING OMISSION     | S3A_02 (0.967) and Photo (0.879) failed >=0.98; |
|                                      |                        | report falsely claimed "PASS (Conditional)".    |
| 4. Geometric Visibility & Contact    | MODEL SIMPLIFICATION   | Receiver self-shadowing omitted;                |
|                                      |                        | contact occlusion uses radial circle proxy.     |
| 5. Dual-Viewport Scene State         | PARTIAL UI DISCONNECT  | Light/proxy work reactively;                    |
|                                      |                        | Receiver dropdown is unwired in Gradio.         |
| 6. Zero-Mutation & Deterministic     | 100% REPRODUCIBLE      | Bitwise identical (diff = 0.00000000) verified. |
+----------------------------------------------------------------------------------------------------------------+
```

---

### 3. Detailed Technical Investigations

#### 3.1 Shadow SDE & IoU Failures: The Unprojected Sky Defect
- **Reported Numbers:**
  - Case S3A_01 (Perfume Box on Plane): $SDE = 92.18\text{ px}$, $\text{IoU} = 0.3302$.
  - Case S3A_02 (Perfume Box on Cyclorama): $SDE = 4.34\text{ px}$, $\text{IoU} = 0.9220$.
- **Source Inspection:**
  Inspection of `studio3a/renderer.py` (lines 158-168) reveals how `surface_pos` is populated:
  ```python
  surface_pos = np.zeros((H, W, 3), dtype=np.float32)
  surface_norm = np.zeros((H, W, 3), dtype=np.float32)
  is_receiver = (~fg_mask) & rec_hit
  surface_pos[fg_mask] = ray_o[fg_mask] + t_camera_depth[fg_mask, None] * ray_d[fg_mask]
  surface_pos[is_receiver] = ray_o[is_receiver] + rec_t[is_receiver, None] * ray_d[is_receiver]
  ```
- **The Defect:**
  On a flat ground plane (`ReceiverType.PLANE`), camera rays directed above the horizon ($y \in [0, 181]$) do not intersect the floor (`rec_hit = False`) and are not foreground (`fg_mask = False`). Consequently, their `surface_pos` remained at `[0, 0, 0]` in world space.
  Position $[0, 0, 0]$ is located directly underneath the perfume box proxy (centered at $[0, 0.40, 0]$).
  When `ShadowEngine.compute_direct_visibility` was called across all pixels without masking, shadow rays traced from $[0, 0, 0]$ toward the key light at $[1.2, 1.8, 1.5]$ passed through the perfume box proxy and were marked as occluded.
  This caused **9,258 background sky pixels** to be falsely classified as shadowed in `V_cand` (total candidate shadow: 13,866 pixels vs true shadow: 4,696 pixels).
- **Why S3A_02 Passed:**
  In S3A_02, the Cyclorama cove extends into a vertical wall at $Z = -1.20$. Every ray above the floor intersected the cyclorama wall (`rec_hit = True`). No unprojected sky pixels existed, preventing the $[0, 0, 0]$ coordinate collapse.

#### 3.2 The Suspicious Zero CGS Results: Metric Pathology
- **Reported Numbers:**
  Every single test case in `benchmark_results.json` logged $CGS = 0.0$ and `"gate_CGS": "PASS"`.
- **Source Inspection:**
  In `experiments/RS-SPIKE-3A/run_experiments.py` (lines 95-100, 254-259):
  ```python
  def compute_CGS(V_direct: np.ndarray, contact_occlusion: np.ndarray, contact_mask: np.ndarray) -> float:
      if contact_mask is None or not np.any(contact_mask):
          return 0.0
      val = float(np.min(V_direct[contact_mask] * contact_occlusion[contact_mask]))
      return round(val, 4)
  ```
  `contact_mask` was constructed as:
  ```python
  contact_mask = np.zeros_like(fg_mask)
  if np.any(fg_mask):
      fy, fx = np.where(fg_mask)
      max_y = np.max(fy)
      contact_mask[max(0, max_y - 2):min(depth.shape[0], max_y + 3), np.min(fx):np.max(fx)] = True
  ```
- **The Defect:**
  `contact_mask` defines a rectangular window spanning 5 full image rows across the entire horizontal bounding box of the foreground object.
  Under any directional light, an object invariably casts a shadow or exhibits self-shadowing on its unlit side.
  Because `compute_CGS` takes `np.min` over this broad 5-row bounding box, the presence of even a single pixel in shadow forces `np.min` to evaluate to `0.0000`.
  **Pathological Behavior:** Even if an object were hovering 1 meter in the air, if its shadow or unlit side touched that 5-row box, `compute_CGS` would still report `0.0000` (PASS). The metric as written cannot detect floating objects or light leaks.

#### 3.3 DCI Threshold Inconsistencies & Reporting Omission
- **The Specification:** Acceptance Gate requires $DCI \ge 0.980$.
- **Raw Benchmark Data:**
  - `S3A_01`: $0.9968$ (PASS)
  - `S3A_02`: **$0.9671$** (Logged as `"gate_dci": "FAIL"` in JSON)
  - `S3A_03`: $0.9884$ (PASS)
  - `S3A_04`: $0.9927$ (PASS)
  - `S3A_05`: $0.9967$ (PASS)
  - `S3A_06`: $0.9891$ (PASS)
  - `Photographic (Nike)`: **$0.8791$** (Severe drop)
- **The Inconsistency:**
  The engineering report (`docs/RS-SPIKE-3A/08_VALIDATION_REPORT.md` and `05_LIGHTING_AND_SHADOW_REPORT.md`) stated:
  `Detail Correlation Index (DCI) | >= 0.98 | 0.967 - 0.997 (PASS)`
  The report downgraded a logged failure in S3A_02 into a "conditional pass" without acknowledging that S3A_02 violated the $\ge 0.980$ threshold.
- **Physical Reason for DCI Drop:**
  `compute_DCI` computes the cosine similarity of the Laplacian between original and relit images over the entire frame. Introducing strong directional illumination, dark cast shadows, and new highlights alters high-frequency edges. On a real photograph (`DCI = 0.8791`), strong relighting is fundamentally at odds with maintaining a global Laplacian correlation of $\ge 0.980$. The metric should evaluate texture correlation within the non-shadowed foreground rather than whole-frame edge similarity.

#### 3.4 Actual Implementation of Geometric Visibility & Contact Occlusion
1. **Receiver Self-Occlusion Omission:**
   In `studio3a/shadows.py` (`ShadowEngine.compute_direct_visibility` lines 76-80):
   ```python
   hit_proxy, t_hit, _ = self.proxy.intersect_rays(p_bias, ray_d)
   is_blocked = hit_proxy & (t_hit > 1e-3) & (t_hit < dist - 1e-3)
   ```
   Rays are ONLY tested against `self.proxy`. They are NEVER tested against `self.receiver`. If an artist places a light behind the cyclorama wall, the wall does not cast a shadow on the floor or block the light.
2. **Contact Occlusion Circular Footprint Heuristic:**
   In `studio3a/shadows.py` (`ShadowEngine.compute_contact_occlusion` lines 145-156):
   The contact term computes distance from the proxy center in the XZ plane and subtracts a single scalar radius `footprint_r = float(np.max(self.proxy.half_extents[[0, 2]]))`.
   This models the contact footprint as a cylinder/circle, regardless of whether the proxy is a rectangular box, an oblong cylinder, or a shoe sole mesh. Furthermore, contact darkening is applied exclusively to `is_receiver`; the underside of the subject receives zero contact darkening.

#### 3.5 Authoritative Scene State in Dual-Viewport UI
- **Verified Working:**
  - Manipulating light position, rotation, dimensions, intensity, and temperature correctly updates `StudioScene`, records undo/redo states in `SceneStateManager`, and re-renders both the photographic plate and the 3D stage viewport.
  - Undo and redo operate deterministically on authoritative JSON snapshots.
- **Identified UI Defect:**
  In `studio3a/workspace.py` line 406:
  `receiver_type = gr.Dropdown(choices=["CYCLORAMA", "PLANE"], value="CYCLORAMA", label="Receiver Geometry")`
  The `receiver_type` dropdown is never connected to any Gradio callback. Lines 450-456 exclude it from `proxy_inputs`, and no change listener is registered. Selecting a different receiver in the Gradio UI has zero effect on the scene.

#### 3.6 Reproducibility of Zero-Mutation & Deterministic Replay
An independent verification test (`scratch/test_independent_reproducibility.py`) was executed:
1. **Zero-Mutation on Protected Pixels:**
   Reconstructing an image with a half-frame protected mask produced a maximum pixel deviation of **$0.0000000000$** on protected pixels. Exact bitwise identity is confirmed.
2. **Deterministic Replay Across JSON Serialization:**
   Saving a scene to JSON, reloading it into a fresh scene instance, and re-rendering with identical sample count produced **$0.0000000000$** maximum difference in both linear radiance and direct visibility. Exact bitwise reproducibility is confirmed.

---

### 4. Audit Conclusions for RS-METAL-2 Handoff

The architecture established in RS-SPIKE-3A is mathematically defensible and forms a solid basis for GPU porting, provided the three identified implementation defects are addressed in the Metal pipeline:
1. **Sky Masking:** The primary ray generator and shadow dispatcher in Metal must explicitly mask out unprojected sky pixels (`rec_hit == False && fg_mask == False`), setting their visibility to 1.0 (unshadowed ambient) and preventing $[0, 0, 0]$ coordinate collapse.
2. **Receiver Shadow Testing:** Metal shadow ray kernels must test against both proxy geometry and receiver surfaces (cyclorama wall and cove).
3. **Contact Occlusion Refinement:** Replace the circular proxy radius with true distance-to-proxy-boundary evaluation.
4. **UI Receiver Binding:** Wire `receiver_type` in `studio3a/workspace.py` to `session.update_receiver_params`.

With these corrections clearly defined, we proceed to author the **RS-METAL-2 Implementation Plan**.

