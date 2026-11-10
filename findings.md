# RS-PRODUCT-1.1 Findings & Architectural Notes

## Initial Discovery & Audit Observations (Checkpoint 27a38f8)
1. **Application Architecture Classification:**
   - The application is a local client-server architecture: FastAPI backend (`relight_studio/server.py`) serving a modern HTML5/Canvas/CSS3 frontend (`relight_studio/web/`) launched via Python (`python -m relight_studio`).
   - It is **not** a native AppKit/Cocoa/SwiftUI compiled binary, but rather a high-performance local web application operating on localhost (`127.0.0.1:8000`).
   - It connects natively to Apple Silicon Metal via C bindings (`libmetal2.dylib`) through `ctypes` in `metal2/bridge.py` and `metal2/renderer.py`.
   - This architectural classification must be documented transparently without inaccurate claims of being a native macOS application bundle.
2. **Sample-Count Discrepancy Resolution:**
   - In `studio3a/renderer.py` and `metal2/renderer.py`, `RenderQuality.PREVIEW` uses `n_samples = 4` samples per area light.
   - In `studio3a/renderer.py`, `RenderQuality.FINAL` uses `n_samples = 32` samples per light.
   - In `metal2/shaders/renderer.metal`, `metal2_render_frame` has a macro `NUM_SHADOW_SAMPLES` or passes stratified grid dimensions ($5 \times 5 = 25$ SPP in earlier metal benchmarks vs stratified 32 in CPU reference).
   - In the UI, the button is labeled "Render Final (32 MC)", matching the CPU reference and high-sample Monte Carlo settings.
3. **Interactive 3D Viewport Interaction Gaps:**
   - Currently, `stage-canvas` receives a rendered 2D bitmap from `render_3d_stage_canvas()`.
   - Mouse events currently support camera orbit and pan by sending HTTP requests (`/api/stage/orbit`), but hit-testing for 3D selection and mouse-dragging of the 3D translation gizmo axes is limited to slider manipulations or client-side approximation.
   - We must implement client-side interactive hit-testing and drag-plane projection for the 3D translation and rotation gizmos on `stage-canvas`, sending high-speed updates to `/api/light/transform` with debounced preview rendering!
