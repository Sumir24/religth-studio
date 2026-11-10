# RS-PRODUCT-1.0 Findings & Architectural Notes

## Discovery & Existing Assets
- **Rendering Foundation:** Complete Cook-Torrance GGX microfacet specular BRDF, multi-light additive transport, Karis split-sum Image-Based Lighting (diffuse irradiance + prefiltered specular + 2D BRDF LUT), E.1 guided-filter photographic reconstruction, and C3 Oklab gamut mapping.
- **Metal Acceleration:** `metal2/libmetal2.dylib` compiled and functioning via `metal2/bridge.py` and `metal2/renderer.py`. Pure GPU kernel time at $1024 \times 576$ is $1.82 - 2.41\,\text{ms}$ ($400+\,\text{FPS}$).
- **Historical Workspace:** `studio3a/workspace.py` provided a basic prototype using Gradio 6. However, Gradio has rigid web-form layouts and lacks professional creative application interaction (e.g. smooth mouse-drag 3D orbit/pan/zoom, interactive 3D transform gizmos, responsive dockable panels, bespoke dark studio aesthetic).
- **Installed Runtime:** Python 3.14.6 with FastAPI, Starlette, Uvicorn, Pillow, OpenCV, NumPy, Torch, Pytest. Google Chrome 157 is installed locally on macOS.
- **Application Architecture Decision:**
  - Create a production-grade macOS studio application package `relight_studio/`.
  - Architecture: Application UI (HTML5/Canvas/WebGL dark studio workspace with interactive 3D gizmos, viewport zoom/pan/wipe) <-> StudioAppController <-> Authoritative Scene State (SceneStateManager) <-> RenderingOrchestrator (async executor with background worker, request cancellation, and stale-frame suppression) <-> MetalRenderBackend / RenderBackend.
  - Native launch via `python -m relight_studio` or CLI entry point, served over high-performance local async HTTP/WebSocket, capable of running in browser or standalone app window.
  - Full screenshot capture pipeline using headless Chrome to produce verified, high-resolution visual evidence of all 10 application states.
