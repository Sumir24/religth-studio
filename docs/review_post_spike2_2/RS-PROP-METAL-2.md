# RELIGHT STUDIO — MILESTONE PROPOSAL
## RS-METAL-2: Native Metal Shading Language & Real-Time GPU Engine

- **Document ID:** RS-PROP-METAL-2-v1.0
- **Status:** APPROVED PROPOSAL FOR IMMEDIATE EXECUTION
- **Author:** Principal GPU Performance Engineer & Systems Architect
- **Date:** 2026-11-09
- **Preceding Audit:** RS-REP-POST-SPIKE-2.2-INDEPENDENT-REVIEW.md (Unmasked PyTorch MPS Bottlenecks)

---

### 1. Executive Summary & Problem Statement

The post-Spike 2.2 independent audit revealed that previous performance claims ($32.08\text{ ms}$ at 1080p) were based on a synthetic mock bisection kernel executed on PyTorch MPS.
When measured under genuine production conditions on PyTorch MPS:
1. Gamut mapping alone consumes **$239.24\text{ ms}$** ($4.1\text{ FPS}$) due to $112+$ individual graph kernel dispatches per frame.
2. The pipeline is bound by CPU-GPU dispatch synchronization, intermediate memory allocation churn, and host-side driver overhead.
3. Crucial lighting passes ($C_{\text{contact}}$, $V_{\text{self}}$, and $V_{\text{cast}}$) were never implemented on GPU.

PyTorch MPS is an exploratory research wrapper; it is fundamentally unsuitable as the production rendering runtime for Relight Studio.

**Milestone Objective:**
Build and validate **RS-METAL-2**, a pure native Metal compute engine written in **Metal Shading Language (MSL)** with an Objective-C / Swift / C-Metal host harness.
RS-METAL-2 will execute the entire CAHRA pipeline (Diffuse shading, Multi-scale HBAO, 3D Proxy Shadow Cone Tracing, Microfacet Specular PBR, E.1 Guided Filter, and Hybrid 3D LUT Oklab Gamut Mapping) within a **single `MTLCommandBuffer`** on Apple Silicon GPU, achieving **$> 60\text{ FPS}$ ($< 16.6\text{ ms}$) at 1080p** and **$< 50\text{ ms}$ at 4K**.

---

### 2. Core Research Questions

1. **RQ-M2.1 (Single-Pass Kernel Fusion):** Can diffuse shading, 3D proxy cone tracing, and additive radiance compositing be fused into a single Metal compute kernel to eliminate intermediate device memory read/writes?
2. **RQ-M2.2 (Gamut Mapping Acceleration):** Can a hybrid $33 \times 33 \times 33$ 3D LUT texture fetch combined with a 1-step secant correction in MSL registers reduce Oklab gamut mapping from $239\text{ ms}$ to $< 1.0\text{ ms}$ at 1080p without exceeding $\Delta E < 0.10$?
3. **RQ-M2.3 (Threadgroup Shared Memory HBAO):** Can multi-scale horizon search utilize Apple Silicon threadgroup memory (`threadgroup float tile_depth[18][18]`) to reduce global memory bandwidth by $> 70\%$?
4. **RQ-M2.4 (Unified Memory Zero-Copy Pipeline):** How does `MTLResourceStorageModeShared` eliminate PCIe transfer penalties between host image loading and display presentation?

---

### 3. Metal Engine Architecture & Technical Specifications

```
+===================================================================================================+
|                                RS-METAL-2 PIPELINE ARCHITECTURE                                    |
+===================================================================================================+

  Host Input (Camera / Disk) ---> MTLResourceStorageModeShared (Zero-Copy UMA)
                                                 |
                                                 v
  [ METAL COMMAND BUFFER: relight_frame_command_buffer ]
  |
  |-- [ PASS 1: HBAO Compute Kernel ] (kernel_hbao_multiscale.metal)
  |   - Threadgroup caching: 16x16 pixels + 2px halo in tile_depth[]
  |   - 8-direction horizon search across dual radii (6px, 24px)
  |   - Output: texture2d<float, access::write> out_ao (R16Float)
  |
  |-- [ PASS 2: 3D Proxy Shadow & Shading Kernel ] (kernel_proxy_transport.metal)
  |   - Fuses: Diffuse Orientation + Analytical 3D Proxy Cone Intersection
  |   - Fuses: Near-field Contact Grounding + Bleed Guard
  |   - Output: texture2d<float, access::write> out_radiance (RG16Float: Y_indir, Y_dir)
  |
  |-- [ PASS 3: Separable Guided Filter ] (kernel_guided_filter.metal)
  |   - Horizontal & Vertical box convs using simdgroup reduction instructions
  |   - Preserves high-frequency photographic texture
  |
  |-- [ PASS 4: Hybrid Oklab Gamut & Tone Kernel ] (kernel_oklab_hybrid_lut.metal)
  |   - Reads: 3D LUT texture (texture3d<float, access::sample> lut_33) in 1 instruction
  |   - 1-step secant root refinement executed purely in registers
  |   - Output: texture2d<float, access::write> final_srgb (RGBA8Unorm)
  |
  v
  [ PRESENTATION ] ---> CAMetalLayer (Direct to Screen at 60 FPS)
```

#### 3.1 Kernel Fusion & Register-Level Gamut Mapping
The hybrid Oklab kernel in Metal Shading Language:
```metal
kernel void oklab_gamut_hybrid_kernel(
    texture2d<float, access::read> in_rgb [[texture(0)]],
    texture2d<float, access::read> in_relit_y [[texture(1)]],
    texture3d<float, access::sample> lut_33 [[texture(2)]],
    sampler lut_sampler [[sampler(0)]],
    texture2d<float, access::write> out_rgb [[texture(3)]],
    uint2 gid [[thread_position_in_grid]])
{
    float3 rgb = in_rgb.read(gid).rgb;
    float y_relit = in_relit_y.read(gid).r;
    
    // Matrix transform to Oklab in thread registers
    float3 lms = M1 * rgb;
    float3 oklab = M2 * cbrt(max(lms, 1e-5f));
    oklab.x = y_relit; // Apply relit luminance
    
    // 1-instruction hardware 3D LUT sampler fetch
    float3 lut_coords = float3(oklab.x, (oklab.y + 0.4f) * 1.25f, (oklab.z + 0.4f) * 1.25f);
    float t_initial = lut_33.sample(lut_sampler, lut_coords).r;
    
    // 1-step secant refinement in registers
    float t_refined = refine_gamut_boundary(oklab, t_initial);
    
    // Convert back to linear RGB and sRGB display
    float3 rgb_out = oklab_to_rgb(float3(oklab.x, oklab.yz * t_refined));
    out_rgb.write(float4(linear_to_srgb(rgb_out), 1.0f), gid);
}
```

---

### 4. Experimental Methodology & Hardware Profiling Protocol

The prototype will be implemented in `metal2/` using native C++ / Metal API bindings.
Testing will be performed on an Apple Silicon M-series GPU using Xcode Instruments (Metal System Trace and GPU Counters):

| Profiling Resolution | Frame Dimensions | Target Execution Time | Target Framerate | Maximum VRAM Allocation |
| :--- | :---: | :---: | :---: | :---: |
| **Interactive Preview** | $384 \times 256$ | **$< 2.0\text{ ms}$** | **$> 500\text{ FPS}$** | $< 8\text{ MB}$ |
| **Full HD 1080p** | $1920 \times 1080$ | **$< 16.0\text{ ms}$** | **$> 60\text{ FPS}$** | $< 45\text{ MB}$ |
| **Ultra HD 4K** | $3840 \times 2160$ | **$< 50.0\text{ ms}$** | **$> 20\text{ FPS}$** | $< 180\text{ MB}$ |

#### Measurement Protocol:
1. **Xcode GPU Timers:** Use `MTLCommandBuffer.gpuStartTime` and `gpuEndTime` rather than host CPU wall-clock timers.
2. **Instruments GPU Profiling:** Measure Arithmetic Throughput %, Texture Memory Bandwidth %, and Occupancy per compute shader.
3. **Sustained Thermal Run:** Continuous 10-minute 60 FPS stress test to detect thermal throttling or memory leaks.

---

### 5. Quantitative Acceptance Gates

| Diagnostic Metric | Baseline (PyTorch MPS) | RS-METAL-2 Target Gate | Critical Significance |
| :--- | :---: | :---: | :--- |
| **Oklab Gamut Kernel Latency (1080p)** | $239.24\text{ ms}$ | **$\le 1.0\text{ ms}$** | Eliminates the single largest pipeline bottleneck |
| **End-to-End Pipeline Latency (1080p)** | $> 300\text{ ms}$ | **$\le 16.6\text{ ms}$** | Unlocks rock-solid 60 FPS interactive viewport |
| **Tail Latency Stability (p95 / p50)** | $1.05\times$ | **$\le 1.10\times$** | Zero stutter during active gizmo dragging |
| **Peak VRAM Allocation (1080p)** | $56.0\text{ MB}$ | **$\le 45.0\text{ MB}$** | Reduced via texture recycling & transient heaps |
| **Command Buffer Count per Frame** | $> 112$ dispatches | **Exactly 1 Command Buffer** | Eliminates CPU-GPU driver round-trip stalls |
| **Gamut Mapping Accuracy ($\Delta E_{\text{Oklab}}$)** | $0.000$ (Ref) | **Mean $\le 0.010$, Max $\le 0.100$** | Below visible perception threshold ($\Delta E < 1.0$) |

---

### 6. Dependencies, Risks & Mitigation Strategies

1. **Risk 1: 3D Texture Interpolation Clamping along Boundaries**
   - *Risk:* Sampling near the $[0, 1]^3$ LUT edge might clamp coordinates and induce false color shifts.
   - *Mitigation:* Add a half-texel border padding to the 3D LUT generation kernel and enforce `MTLSamplerAddressModeClampToEdge`.
2. **Risk 2: Metal Shading Language Compiler Variations**
   - *Risk:* Differences between Apple Silicon generations (M1/M2/M3/M4).
   - *Mitigation:* Target `MTLStandardLibrary` with `MTLGPUFamilyApple7` baseline compatibility.
3. **Dependencies:**
   - Independent of Spike 3A and Spike 3B algorithmic code; operates as the low-level rendering backend.

---

### 7. Expected Deliverables

- `metal2/shaders/`: Complete suite of `.metal` compute kernels (HBAO, Proxy Transport, Guided Filter, Hybrid Oklab).
- `metal2/src/`: C++ / Metal pipeline host orchestrator (`MetalRelightEngine.cpp`).
- `metal2/benchmarks/`: Native benchmark harness reading GPU timestamps and emitting JSON performance logs.
- `docs/metal2/RS-REP-METAL-2-PERFORMANCE.md`: Xcode GPU Trace audit report and verification data.
- `docs/metal2/RS-DECISION-METAL-2.md`: Formal production engine backend sign-off.
