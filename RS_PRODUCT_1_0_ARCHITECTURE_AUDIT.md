# Relight Studio — RS-PRODUCT-1.0 Architecture Audit
## From Rendering Engine to Artist-Controlled Virtual Lighting Studio

**Document:** `RS_PRODUCT_1_0_ARCHITECTURE_AUDIT.md`  
**Milestone:** RS-PRODUCT-1.0 (Studio Workspace)  
**Baseline Checkpoint:** `9ad1118` (`feature/RS-PRODUCT-1.0-studio-workspace`)  
**Date:** November 2026  
**Author:** Principal macOS Application Architect, Staff Rendering Engineer, Senior Interaction Designer, Metal GPU Engineer

---

### 1. Executive Summary

Over previous engineering milestones (RS-SPIKE-3A through RS-SPIKE-3C.3), Relight Studio established a mathematically rigorous, physically grounded rendering foundation. This foundation combines:
- Native Metal GPU 3D area-light transport with ray-traced penumbra shadows.
- Cook–Torrance GGX microfacet specular reflection with Smith $G_2$ shadowing-masking and Schlick Fresnel.
- Karis split-sum Image-Based Lighting (IBL) with diffuse irradiance convolution and 2D preintegrated BRDF lookup.
- E.1 Guided-Filter regularized photographic reconstruction preserving original image identity.
- Bitwise non-destructive protected-region preservation ($0.0000000000$ error).

The objective of **RS-PRODUCT-1.0** is to transition this technology from isolated rendering experiments into a professional, artist-controlled virtual lighting studio application on macOS / Apple Silicon. This audit evaluates existing repository assets, identifies production-ready components, catalogues missing application infrastructure, defines the target application architecture, and maps out risks and performance boundaries.

---

### 2. Comprehensive Repository Inventory & Readiness Classification

| Subsystem / Component | Repository Location | Current Maturity | Architectural Verdict |
| :--- | :--- | :--- | :--- |
| **Metal GPU Shaders** | `metal2/shaders/renderer.metal`, `reconstruction.metal` | Production-Grade (Metal 3) | **REUSE AS-IS.** Fully validated, pole singularity guarded. |
| **Metal C++ / Obj-C Bridge** | `metal2/src/metal_bridge.mm`, `metal_bridge.h`, `libmetal2.dylib` | Production-Grade | **REUSE AS-IS.** High-throughput C interface. |
| **Metal Python Runtime** | `metal2/bridge.py`, `metal2/renderer.py` | Production-Grade | **REUSE AS-IS.** Integrates ctypes with Apple Silicon UMA buffers. |
| **CPU Reference Renderer** | `studio3a/renderer.py` | Production-Grade Reference | **REUSE AS-IS.** Deterministic CPU verification baseline. |
| **Scene Data Structures** | `studio3a/scene.py` | Highly Mature | **REUSE & EXTEND.** Full dataclass serialization, validation, and history. |
| **Parametric Geometry** | `studio3a/geometry.py` | Production-Grade | **REUSE AS-IS.** OBB, Superquadric, Mesh ray tracing and SDFs. |
| **Area Light Transport** | `studio3a/lighting.py` | Production-Grade | **REUSE AS-IS.** Stratified Monte Carlo, Blackbody Kelvin conversion. |
| **Material Model** | `studio3a/material.py`, `studio3a/brdf.py` | Production-Grade | **REUSE AS-IS.** 5 canonical PBR profiles, GGX microfacet formulation. |
| **IBL & Environment** | `studio3a/environment.py` | Production-Grade | **REUSE AS-IS.** Equirectangular sampling, BRDF LUT, irradiance maps. |
| **Photographic Reconstruction** | `studio3a/reconstruction.py` | Production-Grade | **REUSE AS-IS.** E.1 guided filter, C3 Oklab gamut mapping. |
| **Uncertainty Supervisor** | `studio3a/uncertainty.py` | Production-Grade | **REUSE AS-IS.** Multi-channel geometric, occlusion, material metrics. |
| **Stage Viewport Projection** | `studio3a/workspace.py` (`render_virtual_studio_viewport`) | Prototype | **REUSE & REFINE.** Wireframe 3/4 perspective stage generator. |
| **Session Controller** | `studio3a/workspace.py` (`StudioWorkspaceSession`) | Prototype | **REFACTOR INTO APPLICATION CONTROLLER.** |
| **Existing UI Prototype** | `studio3a/workspace.py` (`build_gradio_workspace`) | Prototype (Gradio 6) | **REPLACE WITH BESPOKE STUDIO WORKSPACE.** |
| **Project Persistence** | None (ad-hoc single-scene JSON only) | Missing | **NEW INFRASTRUCTURE REQUIRED.** `.relight` project bundle. |
| **Async Rendering Orchestrator**| None (synchronous single-thread execution) | Missing | **NEW INFRASTRUCTURE REQUIRED.** Non-blocking worker queue. |
| **Interactive 3D Gizmos** | None (sliders only) | Missing | **NEW INFRASTRUCTURE REQUIRED.** 3D viewport transform manipulation. |

---

### 3. Detailed Architectural Gap Analysis

#### 3.1 Why the Existing Gradio Prototype Cannot Serve as the Product
`studio3a/workspace.py` implemented a prototype using Gradio 6 (`build_gradio_workspace`). While useful for early algorithmic verification, Gradio exhibits fundamental limitations for a professional creative instrument:
1. **Layout Rigidity:** Gradio organizes components in predefined HTML flexbox containers with generic web admin/dashboard styling (oversized cards, fixed padding, standard form inputs). It cannot deliver the dense, precise, distraction-free aesthetic of professional creative tools (Lightroom, DaVinci Resolve, Capture One).
2. **Lack of Interactive 3D Canvas Manipulation:** In Gradio, adjusting a light requires scrolling down to slider controls. Direct mouse interaction in the 3D viewport (orbiting the camera, clicking a light quad, dragging a 3D translation/rotation gizmo) cannot be implemented natively within standard Gradio components without extensive, fragile custom web components.
3. **Synchronous UI Blocking:** Slider adjustments in Gradio trigger synchronous backend execution. Rapid slider dragging causes request backlogs, resulting in UI freezes, dropped frames, and stale execution cascades.
4. **No Project Lifecycle Management:** The prototype only saved raw scene parameters to single JSON files. It lacked project concepts: document management, relative asset resolution, image metadata preservation, color space tracking, and recent project history.

#### 3.2 Missing Application Infrastructure
To fulfill **RS-PRODUCT-1.0**, the following core architectural modules must be engineered:
1. **Authoritative Application Controller (`relight_studio/controller.py`):**
   - Coordinates scene state, project files, rendering requests, and viewport view models.
   - Decoupled from any specific rendering backend or UI display technology.
2. **Project Bundle & Document Manager (`relight_studio/project.py`):**
   - Manages `.relight` project packages (or directory bundles) containing project manifests, relative asset links, camera alignments, proxy settings, light configurations, material properties, and render settings.
   - Handles asset missing/relocation gracefully without corrupting project state.
3. **Asynchronous Rendering Orchestrator (`relight_studio/orchestrator.py`):**
   - Decouples UI interaction from rendering computation.
   - Manages an async worker thread pool with **Render Request Debouncing** and **Stale-Frame Cancellation**: when an artist drags a light slider or 3D gizmo rapidly, in-flight obsolete preview renders are cancelled or superseded, preventing backlogs and guaranteeing $< 16\,\text{ms}$ UI response.
4. **Bespoke Professional Studio UI (`relight_studio/web/` & `server.py`):**
   - Built on a lightweight, high-performance local async backend (FastAPI/WebSocket) serving a precision dark-mode Studio Workspace (`#121214` neutral dark palette, SF Pro / Inter typography, 1px subtle borders, zero unnecessary decoration).
   - Four unified workspace regions:
     - **Region A: Photograph Viewport** (Zoom, pan, fit-to-screen, interactive split wipe, mode switching, rendering status indicator).
     - **Region B: 3D Studio Viewport** (Real-time camera orbit/pan/zoom via mouse/trackpad, ground/cove grid, subject proxy, area lights with normal arrows, click-selection, and interactive 3D transform gizmos).
     - **Region C: Scene Hierarchy Tree** (Scene $\to$ Camera, Subject $\to$ Proxy, Receiver, Lights $\to$ Area Light 01/02, Environment; with add, remove, duplicate, toggle, rename, and selection synchronization).
     - **Region D: Context Inspector** (Dynamic, property-exact controls for selected object with live updates).

---

### 4. Target Application Architecture

The application strictly enforces a unidirectional data flow and clean separation of concerns:

```
+-----------------------------------------------------------------------------------+
|                            APPLICATION UI (WORKSPACE)                             |
|  - Photograph Viewport (Pan/Zoom/Wipe)      - 3D Studio Viewport (Orbit/Pan/Gizmo)|
|  - Scene Hierarchy Tree (Add/Del/Select)    - Context Inspector (Exact Controls)  |
+------------------------------------------+----------------------------------------+
                                           | User Actions / Events
                                           v
+-----------------------------------------------------------------------------------+
|                        STUDIO APPLICATION CONTROLLER                              |
|  - Document / Project Lifecycle             - Selection Manager                   |
|  - Tool & Interaction Dispatcher            - Undo / Redo Transaction Stack       |
+------------------------------------------+----------------------------------------+
                                           | Scene Mutations
                                           v
+-----------------------------------------------------------------------------------+
|                         AUTHORITATIVE SCENE STATE                                 |
|  - StudioScene (Camera, Subject, Receiver, Lights, Material, Environment)         |
|  - Strict Numerical Validation & Schema Versioning                                |
+------------------------------------------+----------------------------------------+
                                           | State Snapshots
                                           v
+-----------------------------------------------------------------------------------+
|                        ASYNC RENDERING ORCHESTRATOR                               |
|  - Priority Queue (Interactive Preview vs Final Export)                           |
|  - Stale-Request Cancellation & Debounce Supervisor                               |
|  - Worker Thread Pool (Off-Main-Thread Execution)                                 |
+------------------------------------------+----------------------------------------+
                                           | Dispatch Render Pass
                                           v
+-----------------------------------------------------------------------------------+
|                      RELIGHT STUDIO RENDERING ENGINE                              |
|  +-------------------------------------+   +------------------------------------+ |
|  | Native Metal GPU Backend (Metal 3)  |   | CPU Reference Backend              | |
|  | - Ray Tracing & Area Light Sampling |   | - Numerical Parity Baseline        | |
|  | - GGX Microfacet Specular BRDF      |   | - Fallback Verification            | |
|  | - Karis Split-Sum IBL Transport     |   |                                    | |
|  +-------------------------------------+   +------------------------------------+ |
|                                           |                                       |
|                                           v                                       |
|  +------------------------------------------------------------------------------+ |
|  | Photographic Reconstruction (E.1 Guided Filter + C3 Oklab Gamut Mapping)     | |
|  | Protected Region Non-Destructive Pass-Through (0.0000000000 Error)           | |
|  +------------------------------------------------------------------------------+ |
+------------------------------------------+----------------------------------------+
                                           | Framebuffers / Diagnostic Telemetry
                                           v
+-----------------------------------------------------------------------------------+
|                      VIEWPORT COMPOSITOR & VIEW MODEL                             |
|  - Relit Photograph Viewport Buffer        - 3D Studio Stage Viewport Buffer      |
|  - Direct Visibility / Wireframe Overlays  - Performance & Latency Telemetry      |
+-----------------------------------------------------------------------------------+
```

---

### 5. State Management & Interaction Strategy

1. **Single Source of Truth:** All viewports, hierarchy panels, and inspectors derive their data exclusively from the current `StudioScene` snapshot in `AuthoritativeSceneManager`.
2. **Stable Object Identification:**
   - Every light, geometry proxy, receiver, and environment object has a persistent UUID string (`light_01`, `uuid4`).
   - Inspector controls bind to the selected object ID. Deselecting or switching objects updates the inspector dynamically without state loss.
3. **Transactional History (Undo / Redo):**
   - Discrete artist operations (e.g. adding a light, changing a material profile, renaming an object) push a complete immutable scene snapshot onto the history stack.
   - Continuous artist operations (e.g. dragging a slider or dragging a 3D gizmo) perform ephemeral preview renders during drag, and push a single transaction snapshot upon mouse release (`drag_end`).
4. **Bidirectional Viewport Synchronization:**
   - Selecting a light quad in the 3D viewport immediately updates the selection highlight in the Scene Hierarchy tree and loads the light's parameters into the Inspector.
   - Adjusting a parameter in the Inspector instantly re-renders the 3D stage quad and initiates an asynchronous preview render for the Photograph Viewport.

---

### 6. Persistence & Project File Specification

Relight Studio projects will use a non-destructive, portable bundle format: `.relight` (directory bundle or packaged zip containing `project.json` and associated assets).

```
my_shoot_relight.relight/
├── project.json              # Project metadata, version, creation timestamp
├── scene.json                # Complete StudioScene serialized snapshot
├── source/
│   ├── original_image.png    # High-resolution source photograph (immutable)
│   ├── depth_map.png         # Optional/estimated depth map
│   └── normals_map.png       # Optional/estimated surface normal map
├── environment/
│   └── env_map.hdr           # Optional imported HDR environment map
└── previews/
    └── last_render_thumb.jpg # Fast project thumbnail
```

- **Non-Destructive Guarantee:** `source/original_image.png` is opened read-only and never modified.
- **Relative Path Portability:** All file references inside `project.json` use relative paths within the bundle. If moved to another machine or folder, the project loads without missing asset warnings.

---

### 7. Performance Constraints & Threading Architecture

1. **Main UI Thread Responsiveness:**
   - The UI event loop must never wait on rendering execution.
   - Rendering requests are submitted to `RenderingOrchestrator` via an async channel (`concurrent.futures.ThreadPoolExecutor` or `asyncio.Queue`).
2. **Interactive Preview Latency Budget:**
   - At Preview resolution ($1024 \times 576$), Metal GPU compute execution is $2.41\,\text{ms}$, and end-to-end host roundtrip is $5.25\,\text{ms}$ ($190.6\,\text{FPS}$).
   - The UI debounce threshold is set to $10\,\text{ms}$ (100 Hz update cap), ensuring buttery-smooth interaction well within the 60 FPS interactive budget ($16.6\,\text{ms}$).
3. **1080p Host Overhead Management:**
   - At Full HD ($1920 \times 1080$), host ctypes buffer marshalling takes $\sim 13\,\text{ms}$ ($75.5\,\text{FPS}$).
   - While dragging gizmos, rendering runs strictly in **Preview Quality** at viewport resolution. **Final Quality** ($1080\text{p}+$, high Monte Carlo samples) is triggered only upon interaction settling (after $250\,\text{ms}$ of idle) or upon explicit user export.
4. **Stale Render Rejection:**
   - Each render request carries an incremental `request_id: int` and timestamp.
   - When a worker finishes a render, it compares `request_id` against the orchestrator's latest sequence ID. If a newer request has arrived, the finished frame is discarded immediately, saving compositing and network transfer overhead.

---

### 8. Technical Risks & Mitigations

| Identified Risk | Severity | Mitigation Strategy |
| :--- | :--- | :--- |
| **GPU/CPU Buffer Marshalling Stalls** | Medium | Use fixed-size, pre-allocated pinned memory buffers for preview rendering; avoid re-allocating textures per frame. |
| **Slider Drag Flood** | High | Implement trailing-edge debouncing and active task cancellation in `RenderingOrchestrator`. |
| **UI Framework Clutter / "Toy" Appearance** | High | Strictly follow Section 10 design guidelines: bespoke dark palette, subtle contrast, zero decorative animations, native macOS styling cues. |
| **Asset Missing when Projects Move** | Medium | Use self-contained `.relight` bundle format with relative internal asset paths and fallback proxy generator. |
| **Dual Viewport Desynchronization** | Critical | Enforce single authoritative scene state in `StudioAppController`; both viewports are pure consumers of scene state. |

---

### 9. Conclusion

The Relight Studio codebase possesses an exceptionally strong rendering and computational core. By introducing a clean application controller, asynchronous rendering orchestrator, non-destructive project manager, and a bespoke professional studio workspace, we can deliver a world-class creative lighting instrument.
