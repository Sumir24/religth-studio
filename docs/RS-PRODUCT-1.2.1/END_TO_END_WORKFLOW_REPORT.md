# RELIGHT STUDIO — RS-PRODUCT-1.2.1
## End-to-End Artist Workflow Audit Report

**Auditor:** Independent QA Architect & Interaction Designer  
**Milestone:** RS-PRODUCT-1.2.1  
**Execution Environment:** Live application server on `127.0.0.1:8525` driving headless Chrome  
**Status:** PASS (20/20 Steps Verified)  

---

## 1. Executive Summary

This audit executed the complete 20-step artist workflow on the live running application using `scripts/audit_end_to_end_workflow.py`.

### Core Question:
> Can an artist successfully align a photograph and produce a meaningful lighting change without manually editing project files or relying on developer tools?

### Audit Answer:
**YES.** All 20 steps execute without crashes, visual glitches, or stale state. When virtual lights are manipulated, photographic relighting changes are observed immediately on the original plate ($> 10\,\text{LSB}$ local luminance shift), and saving/reloading a `.relight` bundle preserves camera, proxy transforms, receiver elevation, and lighting state identically.

---

## 2. 20-Step Execution Audit Log

| Step | Action Performed | Telemetry / Metric Verified | Status | Evidence Screenshot |
|---|---|---|---|---|
| **1** | Open Relight Studio | HTTP 200, Web UI loaded | **PASS** | `workflow_evidence/step_01_open_app.png` |
| **2** | Import photograph | `nike_sample.jpg` loaded, SHA-256 logged | **PASS** | `workflow_evidence/step_02_imported_photo.png` |
| **3** | Initialize virtual scene | Scene hierarchy and inspector initialized | **PASS** | Server State API |
| **4** | Change focal length | 85mm preset applied ($f = 85.0\,\text{mm}, \theta = 16.1^\circ$) | **PASS** | Alignment Meta API |
| **5** | Match camera framing | "Fit to Subject" frames proxy to 65% frame height | **PASS** | `workflow_evidence/step_05_fit_to_subject.png` |
| **6** | Adjust proxy dimensions | Width/Height/Depth adjusted to $[0.38, 0.22, 0.18]$ | **PASS** | Subject API |
| **7** | Move subject | Translation applied to $[0.05, 0.40, -0.05]$ | **PASS** | Subject API |
| **8** | Rotate around X (Pitch) | Pitch set to $15.0^\circ$ | **PASS** | Subject API |
| **9** | Rotate around Y (Yaw) | Yaw set to $-30.0^\circ$ | **PASS** | Subject API |
| **10** | Rotate around Z (Roll) | Roll set to $+10.0^\circ$ | **PASS** | `workflow_evidence/step_10_xyz_rotated_subject.png` |
| **11** | Align receiver | Cyclorama set: $y = -0.25\,\text{m}$, cove $r = 0.40\,\text{m}$, $z = -1.5\,\text{m}$ | **PASS** | Receiver API |
| **12** | Snap subject to ground | Closed-form snap executed: $|\Delta y_{\text{gap}}| = 0.000\,\text{m}$ | **PASS** | `workflow_evidence/step_12_snapped_to_ground.png` |
| **13** | Enable wireframe overlay | Mode `wireframe` rendered over photograph | **PASS** | `workflow_evidence/step_13_wireframe_overlay.png` |
| **14** | Enable silhouette overlay | Mode `silhouette` rendered with $\alpha = 0.5$ | **PASS** | `workflow_evidence/step_14_silhouette_overlay.png` |
| **15** | Inspect mismatch | Mode `mismatch` rendered with IoU heatmap | **PASS** | `workflow_evidence/step_15_mismatch_heatmap.png` |
| **16** | Move virtual light | Key light repositioned to $[1.5, 1.8, 1.0]$, $3200\,\text{K}$ | **PASS** | Light Transform API |
| **17** | Observe lighting changes | Max delta $= 18.0$ LSB, Mean delta $= 2.1$ LSB | **PASS** | `workflow_evidence/step_17_diff_map.png` |
| **18** | Save project | Atomic write to `audit_test.relight` bundle | **PASS** | File on disk verified |
| **19** | Reopen project | New controller instance opened bundle | **PASS** | Load Project API |
| **20** | Verify restored state | Camera 85mm, Cove 0.40m, Ground -0.25m, Roll 10.0° verified | **PASS** | Assertions exact |

---

## 3. Photograph Immutability Guarantee

- Initial SHA-256: `0e9b08a4011562c8b6ef88fde24eecf1359a72a34f59e9793e7494a63e934059`
- Final SHA-256 after all 20 steps: `0e9b08a4011562c8b6ef88fde24eecf1359a72a34f59e9793e7494a63e934059`
- **Result:** ZERO BYTE MUTATION.

