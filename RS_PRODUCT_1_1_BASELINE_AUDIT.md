# Relight Studio — RS-PRODUCT-1.1 Baseline Audit
## Inspection, Architectural Classification & Discrepancy Reconciliation

**Document:** `RS_PRODUCT_1_1_BASELINE_AUDIT.md`  
**Milestone:** RS-PRODUCT-1.1 (Phase 0 Audit)  
**Baseline Commit:** `27a38f8`  
**Parent Checkpoint:** `9ad1118`  
**Active Branch:** `feature/RS-PRODUCT-1.1-interactive-scene`  
**Date:** November 2026  
**Auditor:** Principal macOS Application Architect & Independent Rendering Auditor

---

### 1. Executive Summary

In accordance with Phase 0 of the RS-PRODUCT-1.1 Master Engineering Prompt, an independent audit of repository checkpoint `27a38f8` was conducted. This audit establishes the concrete status of the codebase, inspects the 14 baseline areas, resolves two critical discrepancies reported in previous milestone documentation, and determines the architectural foundation for subsequent interaction engineering.

---

### 2. Discrepancy Reconciliation

#### 2.1 Discrepancy A: Application Architecture Classification
- **Reported in Previous Documentation:** Described as a "macOS application" or "studio workspace".
- **Audited Reality in Source Code:**
  - The application is engineered as a **high-performance local client-server application**:
    - Backend: Python 3.14 + FastAPI + Starlette + Uvicorn (`relight_studio/server.py`).
    - Frontend: Pure HTML5 Canvas + CSS3 + Vanilla JavaScript (`relight_studio/web/`).
    - Entry Point: Python module execution: `python -m relight_studio --port 8000` serving `http://127.0.0.1:8000`.
  - **Verdict:** Relight Studio is currently a **local web application running in the user's browser or desktop webview**, not a compiled native macOS `.app` (AppKit/Cocoa/SwiftUI) binary.
  - **Assessment:** However, the backend directly binds to native Apple Silicon Metal via C bindings (`libmetal2.dylib`) and ctypes (`metal2/bridge.py`). This architecture allows cross-browser inspection, zero external build toolchains, and high developer velocity. We will **retain this architecture** while making its interaction completely fluid, without falsely claiming native AppKit bundle compilation.

#### 2.2 Discrepancy B: Sample-Count Configuration (32 MC vs 25 SPP)
- **Reported in Previous Documentation:** The UI button displays `Render Final (32 MC)`, whereas benchmark tables document `spp: 25` for Full HD Final Quality.
- **Audited Reality in Source Code:**
  - In the CPU reference renderer (`studio3a/renderer.py:274`):
    - `PREVIEW` quality specifies $N = 4$ stratified samples per area light.
    - `FINAL` quality specifies $N = 32$ stratified samples per area light.
  - In the Metal GPU benchmark runner (`metal2/run_benchmarks.py` and JSON telemetry):
    - `PREVIEW` quality used $N = 4$ ($2 \times 2$ stratified grid).
    - `FINAL` quality used $N = 25$ ($5 \times 5$ stratified grid) to balance GPU ray tracing throughput on 1080p frames.
  - **Verdict:** 32 MC refers to the CPU reference implementation sample count, while 25 SPP refers to the Metal $5 \times 5$ stratified sampling grid. Both represent high-sample Monte Carlo final passes. In RS-PRODUCT-1.1, we will unify configuration reporting so that the UI accurately displays the active backend's sample count.

---

### 3. Fourteen-Point Baseline Inspection Table

| # | Inspection Item | Source Location | Audited Status | Finding / Action Required for 1.1 |
|---|---|---|---|---|
| **1** | Git Branch & HEAD | `27a38f8` on `feature/RS-PRODUCT-1.1-interactive-scene` | **VERIFIED** | Clean branching off verified product baseline. |
| **2** | Working-Tree Cleanliness | Workspace root | **VERIFIED** | Clean working tree; zero untracked artifacts. |
| **3** | Application Launch Architecture | `relight_studio/__main__.py` | **VERIFIED** | CLI launcher with `--port`, `--image`, `--cpu` flags. |
| **4** | UI Framework Classification | `relight_studio/web/` | **LOCAL WEB APP** | HTML5 Canvas + CSS3 served over FastAPI/Uvicorn. |
| **5** | Authoritative Scene State | `studio3a/scene.py` | **VERIFIED** | Dataclass-based `StudioScene` with strict validation. |
| **6** | Rendering Orchestrator | `relight_studio/orchestrator.py` | **VERIFIED** | Multi-threaded worker queue; off-main-thread execution. |
| **7** | Metal GPU Integration | `metal2/libmetal2.dylib`, `metal2/renderer.py` | **VERIFIED** | Metal 3 pipeline with UMA buffer reuse and pole guard. |
| **8** | Photograph Viewport | `relight_studio/web/app.js` | **FUNCTIONAL** | Canvas zoom/pan and draggable split wipe working. |
| **9** | 3D Stage Viewport | `relight_studio/controller.py:465` | **PARTIALLY INTERACTIVE** | Renders 2D stage canvas; needs direct mouse picking & gizmo drag. |
| **10**| Light Transformation | `relight_studio/controller.py:188` | **FUNCTIONAL (SLIDERS)** | Sliders work; 3D viewport on-canvas drag needs client projection. |
| **11**| Project Save / Load | `relight_studio/project.py` | **FUNCTIONAL** | `.relight` bundle works; needs atomic write hardening. |
| **12**| Undo / Redo Replay | `studio3a/scene.py`, `controller.py` | **VERIFIED** | Transactional undo/redo stack functioning cleanly. |
| **13**| Stale-Frame Cancellation | `relight_studio/orchestrator.py:155` | **VERIFIED** | Older in-flight preview requests dropped during fast drags. |
| **14**| Automated Test Coverage | `tests/` | **137/137 PASSING** | 100% pass rate across historical and product suites. |

---

### 4. Critical Interaction Deficiencies to Address in RS-PRODUCT-1.1

1. **Direct 3D Viewport Manipulation (Primary Blocker):**
   - In RS-PRODUCT-1.0, the 3D Stage Viewport displayed an interactive gizmo rendered as a 2D bitmap by OpenCV (`render_3d_stage_canvas`). While mouse drag rotated the camera, dragging the actual $X, Y, Z$ gizmo handles was not interactive on canvas — users had to use the inspector sliders.
   - **RS-PRODUCT-1.1 Solution:** Implement client-side hit-testing and plane projection directly in `stage-canvas` JavaScript (`relight_studio/web/app.js`), allowing the user to click and drag the $X, Y, Z$ axes directly in the 3D viewport to reposition the light in world space.
2. **Light Orientation / Rotation Gizmo:**
   - Add pitch and yaw rotation controls with visual normal vector updates so rotation is as intuitive as translation.
3. **Lighting Presets:**
   - Provide photographer-tailored presets (`Key Softbox`, `Fill Softbox`, `Rim Strip`, `Top Light`) backed by real scene transforms and intensities.
4. **Dynamic Progressive Preview:**
   - While dragging gizmos, render at ultra-fast preview resolution ($1024 \times 576, >190\,\text{FPS}$); once dragging settles ($250\,\text{ms}$ debounce), trigger progressive quality refinement.
5. **Atomic Project Saving:**
   - Harden `.relight` saving using temporary directory staging (`tempfile`) and atomic directory replacement to eliminate corruption risk if interrupted.

---

### 5. Conclusion & Clearance

The baseline at commit `27a38f8` is solid, fully tested, and ready. Architectural classifications are now reconciled. 

**Readiness Clearance: APPROVED. Proceed to Phase 1 (Real 3D Interaction Engine).**
