# RELIGHT STUDIO — RS-METAL-2
## Engineering Implementation Plan: Native Metal 3D Rendering Engine

**Document ID:** RS-PLAN-METAL-2-v1.0  
**Status:** Approved Implementation Directive  
**Date:** November 9, 2026  
**Hardware Target:** Apple Silicon GPU (Apple M5, macOS arm64)  
**Parent Milestone:** RS-SPIKE-3A  
**Audit Reference:** `docs/RS-SPIKE-3A/RS-AUDIT-SPIKE-3A-INDEPENDENT.md`  

---

### 1. Executive Summary & Objective

The objective of **RS-METAL-2** is to port the complete scene-driven 3D rendering workload from the CPU reference implementation (`studio3a`) to a **native Apple Metal compute engine (`metal2/`)** executing directly on Apple Silicon GPU hardware (Apple M5).

#### Non-Negotiable Engineering Constraints:
1. **Mathematical Equivalence:** The Metal engine must match the mathematical formulations of the `studio3a` reference renderer (analytical OBB slab tests, Superquadric numerical bracket root finding, vectorized Möller-Trumbore ray-triangle tests, multi-region Cyclorama cove evaluation, stratified Monte Carlo area-light sampling, E.1 guided filter, and C3 Oklab constant-hue chroma bisection).
2. **Defect Rectification:** The Metal implementation must resolve the three defects identified in the RS-SPIKE-3A independent audit:
   - Explicit sky pixel masking to eliminate the $[0, 0, 0]$ coordinate collapse and false sky shadows.
   - Receiver self-shadowing evaluation for back-lit cyclorama coves.
   - Full binding of receiver parameters in the workspace controller.
3. **No Fabricated Benchmarks:** All performance metrics must be measured on the actual Apple M5 hardware using native Metal command buffer timestamps and high-resolution system timers. No claims of acceleration may be asserted until verified by empirical benchmark runs.
4. **Preservation of Spike Artifacts:** All historical Spike 1, 2, 2.1, 2.2, and 3A files remain untouched.

---

### 2. Architecture & File Structure

```
metal2/
├── __init__.py                     # Package export
├── shaders/
│   ├── common.metal                # Shared structs (Ray, Hit, Light, Material, CameraUniforms)
│   ├── camera.metal                # Primary camera ray generation kernel
│   ├── geometry.metal              # Analytical intersection kernels (OBB, Superquadric, Mesh, Plane, Cyclorama)
│   ├── lighting.metal              # Stratified MC area-light irradiance & shadow ray kernels
│   ├── contact.metal               # Geometric contact grounding kernel
│   └── reconstruction.metal        # E.1 guided filter & C3 Oklab gamut bisection kernels
├── src/
│   ├── metal_bridge.h              # C API interface for host Python binding
│   └── metal_bridge.mm             # Objective-C++ / Metal runtime pipeline dispatcher
├── Makefile                        # Compilation rules producing libmetal2.dylib via Apple clang
├── bridge.py                       # ctypes / ctypes wrapper exposing C API to Python
├── renderer.py                     # MetalRenderBackend matching studio3a.renderer.RenderBackend interface
└── tests/
    ├── test_metal_device.py        # Validates Metal device creation and shader compilation
    ├── test_math_parity.py         # Numerical parity tests against studio3a CPU reference
    └── test_metal_benchmark.py     # Hardware performance and latency measurement suite
```

---

### 3. Detailed Component Specifications

#### 3.1 Common Data Structures (`metal2/shaders/common.metal`)
Shared header defining data contracts matching Python `StudioScene`:
```metal
struct CameraParams {
    float3 position;
    float3 forward;
    float3 right;
    float3 up;
    float fov_rad;
    uint width;
    uint height;
};

struct LightParams {
    float3 position;
    float3 normal;
    float3 u_tangent;
    float3 v_bitangent;
    float2 dimensions;
    float3 color_tint;
    float intensity;
    uint energy_convention; // 0: FIXED_RADIANCE, 1: FIXED_POWER
    uint n_samples;
    uint seed;
};

struct ProxyParams {
    uint proxy_type;        // 0: OBB, 1: SUPERQUADRIC, 2: MESH
    float3 position;
    float3 half_extents;    // For OBB or Superquadric radii
    float3x3 rotation_matrix;
    float2 sq_exponents;    // e1 (vertical), e2 (horizontal)
    uint num_triangles;
};

struct ReceiverParams {
    uint receiver_type;     // 0: PLANE, 1: CYCLORAMA
    float ground_y;
    float2 cove_center_yz;
    float cove_radius;
    float wall_z;
};
```

#### 3.2 Primary Ray & Scene Intersection Kernel (`metal2/shaders/geometry.metal`)
- Dispatches a 2D grid $(W, H)$ with $16 \times 16$ threadgroup tiles.
- For each pixel $(u, v)$:
  1. Computes normalized camera ray direction $D = \text{normalize}(D_x \cdot \text{right} + D_y \cdot \text{up} + \text{forward})$.
  2. Evaluates intersection against active subject proxy (OBB slab, Superquadric bracket line-search, or LowPolyMesh triangles).
  3. Evaluates intersection against receiver surface (Plane or Cyclorama floor/fillet/wall).
  4. Hit sorting: Identifies foreground hit vs receiver hit.
  5. **Sky Masking:** If neither proxy nor receiver is hit, writes `is_sky = true`, `surface_pos = cam.pos + 10.0 * D`, and `surface_norm = -D`. This directly cures the $[0, 0, 0]$ coordinate collapse.

#### 3.3 Stratified Area Light & Shadow Transport Kernel (`metal2/shaders/lighting.metal`)
- For valid surface points:
  1. Computes unshadowed Lambertian direct irradiance $E = \sum_k \max(N \cdot L_k, 0) \frac{\max(-N_{\text{light}} \cdot L_k, 0)}{d_k^2} \frac{A}{S} L_e$.
  2. Traces shadow rays $P + 10^{-3} N \to P_k^{\text{light}}$:
     - Tests intersection against subject proxy.
     - Tests intersection against cyclorama cove receiver to capture receiver self-shadowing.
     - Accumulates unoccluded visibility $V_{\text{direct}} = \frac{1}{S} \sum_k \chi_k$.
  3. For sky pixels (`is_sky == true`):
     - Sets $V_{\text{direct}} = 1.0$ (unshadowed sky), ensuring zero shadow leakage onto the background.

#### 3.4 Contact Occlusion Kernel (`metal2/shaders/contact.metal`)
- Evaluates near-field proximity between receiver surface points and proxy base contact boundary.
- For planar/cyclorama receivers, computes perpendicular distance to proxy footprint boundary and applies cubic Hermite smoothing $C_{\text{contact}} = 1.0 - 0.95 \cdot (3w^2 - 2w^3)$.

#### 3.5 Reconstruction & Color Space Kernels (`metal2/shaders/reconstruction.metal`)
- Guided-filter base/detail decomposition using 2D box filters with threadgroup shared memory caching.
- C3 Oklab gamut mapping: Converts target relit linear RGB to Oklab $(L, a, b)$, tests displayable sRGB gamut bounds, and executes a 10-iteration constant-hue bisection directly in GPU registers with zero CPU-GPU round-trips.
- Enforces bitwise zero-mutation on protected mask pixels: `out_rgb = is_protected ? orig_srgb : relit_srgb`.

#### 3.6 Metal Host Bridge (`metal2/src/metal_bridge.mm` & `metal2/bridge.py`)
- Objective-C++ implementation creating the `MTLDevice`, compiling MSL source into `MTLLibrary`, and instantiating pre-warmed `MTLComputePipelineState` objects for each shader.
- Uses `MTLResourceStorageModeShared` to map NumPy array pointers directly into Metal buffers with **zero memory copies**.
- Exposes clean C-ABI functions:
  ```cpp
  int metal2_init_device();
  int metal2_render_frame(
      const CameraParams* cam,
      const ProxyParams* proxy,
      const ReceiverParams* receiver,
      const LightParams* light,
      const float* img_orig_srgb,
      const float* depth_map,
      const float* normals_map,
      const uint8_t* fg_mask,
      const uint8_t* protected_mask,
      float* out_relit_srgb,
      float* out_visibility,
      float* out_irradiance,
      uint32_t width,
      uint32_t height,
      float* out_gpu_time_ms
  );
  void metal2_shutdown();
  ```

---

### 4. Implementation Tasks & Verification Steps (TDD)

```
+---------------------------------------------------------------------------------------------------------+
| PHASE / TASK | COMPONENT                 | IMPLEMENTATION ACTION            | TEST / VERIFICATION        |
+--------------+---------------------------+----------------------------------+----------------------------+
| Task 1       | Build Scaffolding & Setup | Create metal2/, Makefile, C dylib| test_metal_device.py passes|
| Task 2       | Camera & Geometry Shaders | camera.metal, geometry.metal     | Parity against Camera3D    |
| Task 3       | Area Light & Shadow Kernel| lighting.metal, contact.metal    | Parity against ShadowEngine|
| Task 4       | Reconstruction & Oklab    | reconstruction.metal             | Parity against ReconEngine |
| Task 5       | MetalRenderBackend Bridge | renderer.py, bridge.py           | Drop-in test in StudioScene|
| Task 6       | Parity & Benchmarking     | Run 6 test scenes on Apple M5    | JSON/CSV verified on GPU   |
+---------------------------------------------------------------------------------------------------------+
```

#### Task 1: Scaffolding, C++ Bridge & Device Initialization
- **Action:** Create `metal2/Makefile` compiling `metal_bridge.mm` via `clang -O3 -shared -fPIC -framework Metal -framework Foundation -o metal2/libmetal2.dylib`.
- **Test:** Write `metal2/tests/test_metal_device.py` verifying device creation, Apple M5 detection, and library loading.
- **Verification:** `pytest metal2/tests/test_metal_device.py` returns exit code 0.

#### Task 2: Camera Rays & Analytical Geometry Shaders
- **Action:** Author `metal2/shaders/common.metal`, `camera.metal`, and `geometry.metal`. Implement analytical ray-OBB slab intersection, Superquadric bracket line search, LowPolyMesh Möller-Trumbore intersection, Ground Plane, and Cyclorama fillet cove. Implement explicit sky masking.
- **Test:** Write `metal2/tests/test_geometry_parity.py` comparing ray hit masks, $t_{\text{hit}}$, and surface normals between Metal GPU and `studio3a/geometry.py` across $384 \times 256$ grids.
- **Verification:** Max normal error $< 10^{-3}$, hit mask agreement $> 99.9\%$.

#### Task 3: Stratified Monte Carlo Area Light & Shadow Shaders
- **Action:** Author `metal2/shaders/lighting.metal` and `contact.metal`. Implement stratified jittered area-light sampling, blackbody temperature conversion, direct diffuse accumulation, and shadow ray testing against proxy and receiver.
- **Test:** Write `metal2/tests/test_lighting_parity.py` comparing unshadowed direct irradiance and shadow visibility between Metal GPU and `studio3a/lighting.py` / `studio3a/shadows.py`.
- **Verification:** Direct irradiance error $< 10^{-3}$, visibility difference within Monte Carlo noise bounds ($< 0.05$).

#### Task 4: Reconstruction & Oklab Gamut Mapping Shader
- **Action:** Author `metal2/shaders/reconstruction.metal` implementing separable guided filter, log-ratio base modulation, constant-hue Oklab bisection, and protected mask pass-through.
- **Test:** Write `metal2/tests/test_reconstruction_parity.py` verifying that protected pixels have exact bitwise $0.00000000$ difference and in-gamut pixels match the CPU reference.
- **Verification:** Bitwise zero-mutation on protected mask confirmed on GPU.

#### Task 5: Python MetalRenderBackend Integration
- **Action:** Author `metal2/renderer.py` implementing `MetalRenderBackend` conforming to the exact interface of `studio3a.renderer.RenderBackend`.
- **Test:** Plug `MetalRenderBackend` into `studio3a/workspace.py` and verify interactive dual-viewport execution.
- **Verification:** Real-time interactive scrubbing with instant stage viewport update.

#### Task 6: Hardware Latency Benchmarking & Reporting
- **Action:** Author `metal2/tests/test_metal_benchmark.py` running all 6 synthetic scenes and the photographic Nike plate at Preview (4 samples) and Final (32 samples) quality across resolutions ($320 \times 240$, $1024 \times 1024$, $1920 \times 1080$).
- **Measurement Protocol:** Read GPU command buffer timestamps directly from `commandBuffer.GPUStartTime` and `commandBuffer.GPUEndTime`.
- **Outputs:** Write results to `metal2/benchmark_results/metal_benchmark_results.json` and generate `docs/metal2/RS-REP-METAL-2-RESULTS.md`.

---

### 5. Mathematical Parity & Verification Standards

To guarantee that RS-METAL-2 does not alter the mathematical behavior of the reference renderer:
1. **Unshadowed Irradiance Parity:** Max absolute difference between GPU and CPU must satisfy $\|E_{\text{GPU}} - E_{\text{CPU}}\|_\infty \le 10^{-3}$.
2. **Deterministic Replay Bitwise Parity:** Serializing a scene to JSON and rendering it on the Metal backend must yield bitwise identical GPU results on reload.
3. **Protected Region Invariance:** For all pixels where `protected_mask == True`, $\|I_{\text{relit}} - I_{\text{orig}}\|_\infty \equiv 0.00000000$.
4. **Sky Unshadowed Invariance:** For all pixels where `rec_hit == False && fg_mask == False`, $V_{\text{direct}} \equiv 1.000000$, curing the Spike 3A sky defect.

---

### 6. Risk Analysis & Mitigation

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Metal compilation overhead at startup** | First frame stutter | Pre-compile MSL to `default.metallib` or compile `MTLComputePipelineState` asynchronously during session initialization. |
| **Superquadric numerical divergence in MSL** | GPU thread hang or NaN normals | Enforce bounded bracket line search ($N=32$ iterations max) with hard clamping on semi-axes and exponent arguments in MSL. |
| **Threadgroup shared memory limits** | Kernel launch failure | Restrict threadgroup memory to $\le 16\text{ KB}$ per tile ($16 \times 16$ float4), well within Apple Silicon's 32 KB limit. |
| **Floating-point rounding differences (FP32)** | Slight sub-pixel edge discrepancies | Verify against ground-truth ray tracer rather than requiring bitwise equality against CPU NumPy transcendental approximations. |
