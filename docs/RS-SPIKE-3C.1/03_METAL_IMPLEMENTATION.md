# RS-SPIKE-3C.1 — Engineering Report 03: Metal GPU Multi-Light Pipeline Implementation

**Milestone:** RS-SPIKE-3C.1 (Multi-Light Architecture & Additive Illumination)  
**Author:** Metal GPU Architect & Performance Engineer  
**Branch:** `feature/RS-SPIKE-3C.1-multilight-architecture`  
**Modules:** `metal2/shaders/renderer.metal`, `metal2/src/metal_bridge.h`, `metal2/src/metal_bridge.mm`, `metal2/bridge.py`, `metal2/renderer.py`  
**Status:** VALIDATED & CLOSED

---

## 1. Executive Summary

This report documents the native Apple Metal GPU implementation of the multi-light rendering architecture on Apple Silicon (M5).

Prior to this milestone, the Metal compute pipeline was constrained to a single uniform structure `constant LightParams& light [[buffer(3)]]`. The shader evaluated ray-box/ray-quadric/ray-sphere shadow intersections for only one emitter and wrote scalar visibility to the intermediate buffer.

Under **RS-SPIKE-3C.1**, the Metal GPU pipeline has been extended to support up to **8 independent rectangular area lights** within a single unified compute dispatch pass:
1. **Light Array Constant Buffer:** Lights are packed into a 96-byte aligned `LightParams` struct array bound at `[[buffer(3)]]` with total light count bound at `[[buffer(14)]]`.
2. **Single-Pass Stratified Accumulation:** A single GPU kernel (`render_hybrid_studio_kernel`) unrolls the loop over active lights, calculating each light's solid-angle geometric factor, cosine falloff, unshadowed irradiance, and stratified shadow visibility.
3. **Additive Transport Accumulation:** Irradiance is accumulated via linear optics superposition:
   $$\mathbf{E}_{\text{total}} = \sum_{i=1}^M \left[ \mathbf{irr}_i \cdot V_i \right]$$
4. **Persistent UMA Buffer Reuse:** The persistent buffer pool (`g_buffer_pool`) remains entirely reused with **0 heap allocations** in steady-state rendering.
5. **Exact CPU-GPU Parity:** Dual-light opposing key/fill parity achieves **$\text{Soft IoU} = 0.9572$** ($\ge 0.93$), **$\text{SDE} = 0.790\,\text{px}$** ($\le 1.0\,\text{px}$), and **$\text{MAE} = 0.000526$** ($\le 0.001$).

---

## 2. Metal Uniform Memory Layout & Alignment

To ensure byte-alignment parity between host CTypes, Objective-C++, and MSL, `CLightParams` is structured as a 96-byte block (divisible by 16 bytes):

```c
typedef struct {
    float position[3];         // 12 bytes
    float normal[3];           // 12 bytes
    float u_tangent[3];        // 12 bytes
    float v_bitangent[3];      // 12 bytes
    float dimensions[2];       //  8 bytes
    float color_rgb[3];        // 12 bytes
    float intensity;           //  4 bytes
    uint32_t energy_convention;//  4 bytes
    uint32_t n_samples;        //  4 bytes
    uint32_t seed;             //  4 bytes
    uint32_t cast_shadows;     //  4 bytes
    uint32_t enabled;          //  4 bytes
    float padding;             //  4 bytes
} CLightParams;                // Total: 96 bytes (6 x 16-byte float4 vectors)
```

In `metal2/shaders/renderer.metal`:
```metal
struct LightParams {
    packed_float3 position;
    packed_float3 normal;
    packed_float3 u_tangent;
    packed_float3 v_bitangent;
    packed_float2 dimensions;
    packed_float3 color_rgb;
    float intensity;
    uint energy_convention;
    uint n_samples;
    uint seed;
    uint cast_shadows;
    uint enabled;
    float padding;
};
```

---

## 3. Shader Kernel Architecture (`render_hybrid_studio_kernel`)

The primary 3D compute pass binds the light array and executes:

```metal
kernel void render_hybrid_studio_kernel(
    constant CameraParams& cam                 [[buffer(0)]],
    constant ProxyParams& proxy                 [[buffer(1)]],
    constant ReceiverParams& receiver           [[buffer(2)]],
    constant const LightParams* lights          [[buffer(3)]],
    constant TriangleMesh* mesh_triangles       [[buffer(4)]],
    device const float* depth_map               [[buffer(5)]],
    device const packed_float3* normals_map     [[buffer(6)]],
    device const uint8_t* fg_mask               [[buffer(7)]],
    device const uint8_t* protected_mask        [[buffer(8)]],
    device const packed_float3* image_orig_srgb [[buffer(9)]],
    device packed_float3* out_relit_srgb        [[buffer(10)]],
    device float* out_visibility                [[buffer(11)]],
    device packed_float3* out_irradiance        [[buffer(12)]],
    constant uint& has_protected_mask           [[buffer(13)]],
    constant uint& num_lights                   [[buffer(14)]],
    uint2 pixel_coord                           [[thread_position_in_grid]]
) {
    ...
    float3 total_unshadowed_irr = float3(0.0f);
    float3 total_illuminated_irr = float3(0.0f);

    for (uint li = 0; li < num_lights; ++li) {
        constant const LightParams& light = lights[li];
        if (light.enabled == 0) continue;

        // Stratified area light samples
        ...
        for (uint sy = 0; sy < grid_dim; ++sy) {
            for (uint sx = 0; sx < grid_dim; ++sx) {
                // Ray-proxy & ray-receiver intersection tests
                ...
            }
        }
        float vis_li = vis_acc_li / float(grid_dim * grid_dim);
        total_unshadowed_irr += irr_acc_li;
        total_illuminated_irr += irr_acc_li * vis_li;
    }

    // Apply receiver contact grounding
    if (is_receiver) {
        ...
        total_illuminated_irr *= c_contact;
    }

    // Composite visibility for diagnostic and metric parity
    float unshadowed_luma = 0.2126f * total_unshadowed_irr.x + 0.7152f * total_unshadowed_irr.y + 0.0722f * total_unshadowed_irr.z;
    float illuminated_luma = 0.2126f * total_illuminated_irr.x + 0.7152f * total_illuminated_irr.y + 0.0722f * total_illuminated_irr.z;
    float composite_visibility = (unshadowed_luma > 1e-5f) ? clamp(illuminated_luma / max(unshadowed_luma, 1e-5f), 0.0f, 1.0f) : 1.0f;

    out_irradiance[idx] = packed_float3(total_unshadowed_irr.x, total_unshadowed_irr.y, total_unshadowed_irr.z);
    out_visibility[idx] = composite_visibility;
    ...
}
```

---

## 4. End-to-End Metal 8-Pass Integration

The downstream 7 compute passes execute seamlessly without modification:
- **Pass 2 (`e1_init_stats_kernel`):**
  Uses `direct_irr` (unshadowed sum) and `direct_vis` (composite visibility ratio). Because:
  $$\text{irr\_luma} \cdot \text{vis} = \text{unshadowed\_luma} \cdot \frac{\text{illuminated\_luma}}{\text{unshadowed\_luma}} = \text{illuminated\_luma}$$
  The target shading ratio $R_{\text{target}}$ precisely captures the total illuminated additive irradiance across all $M$ lights.
- **Passes 3–7 (Separable Guided Box Filters):**
  Regularize the composite ratio $\rho_{\text{total}} = \log R_{\text{eff}}$ in horizontal and vertical passes.
- **Pass 8 (`e1_reconstruct_c3_kernel`):**
  Applies $C3$ Oklab constant-hue chroma bisection and passes through protected regions with exact bitwise zero-mutation.

---

## 5. Verification Results

| Test | Measured Value | Threshold / Target | Status |
|:---|:---:|:---:|:---:|
| **2-Light Linearity ($2\times$ Duplicate)** | **$2.0000\times$** | $2.0000\times$ | **PASS** |
| **Shadow Independence (Disabled Light 2)** | **$0.0000000000$** | $0.0000000000$ | **PASS** |
| **CPU-Metal Soft IoU (2 Opposing Lights)** | **$0.9572$** | $\ge 0.9300$ | **PASS** |
| **CPU-Metal SDE (2 Opposing Lights)** | **$0.790\,\text{px}$** | $\le 1.000\,\text{px}$ | **PASS** |
| **CPU-Metal Irradiance MAE** | **$0.000526$** | $\le 0.001000$ | **PASS** |
| **Buffer Reallocations in Steady State** | **$0$** | $0$ | **PASS** |

Phase 3 is validated and closed. Proceeding to **Phase 4: Multi-Light Shadow Independence & Geometric Accuracy**.
