# RELIGHT STUDIO — RS-SPIKE-3A.1
## Corrective Engineering Implementation & Mathematical Repairs

**Document Reference:** `RS-SPIKE-3A.1-05`  
**Milestone:** RS-SPIKE-3A.1 (Shadow Fidelity, Metal Parity & Interactive Validation)  
**Author:** Principal Graphics Systems Architect & Independent Rendering Auditor  
**Date:** November 2026  
**Status:** IMPLEMENTED & VERIFIED  

---

## 1. Overview of Corrective Interventions

Following the independent forensic audit (`docs/RS-SPIKE-3A.1/00_METAL2_INDEPENDENT_AUDIT.md`) and mathematical shadow failure analysis (`docs/RS-SPIKE-3A.1/01_SHADOW_FAILURE_ANALYSIS.md`), six critical engineering corrections were designed, implemented, and verified across the codebase.

```
+---------------------------------------------------------------------------------------------------+
|                                RS-SPIKE-3A.1 CORRECTIVE PIPELINE                                  |
|                                                                                                   |
|  1. Camera Basis Repair         --> Fix non-orthonormal camera basis passed to GPU               |
|  2. Continuous Shadow Metrics   --> Replace brittle V < 0.85 cutoff with fuzzy Jaccard & CoM     |
|  3. Real C3 Oklab Dispatch      --> Add native Metal gamut map dispatch (715.6x real speedup)     |
|  4. Mesh AABB Fast-Reject       --> Fast bounding box culling on GPU (54x mesh speedup)          |
|  5. Ray Acne Guard              --> Enforce t_hit > 1e-3f on all proxy shadow ray tests           |
|  6. Contact Decoupling          --> Decouple 3D ray culling box from 2D ground contact footprint |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Correction 1: Camera Basis Orthonormalization

### Problem:
In `metal2/renderer.py` (line 81), the camera parameter packing code assigned:
```python
c_cam.up[0] = float(cam.up[0])
c_cam.up[1] = float(cam.up[1])
c_cam.up[2] = float(cam.up[2])
```
where `cam.up` was the world-up vector $[0, 1, 0]$. In the reference `Camera3D` class (`studio3a/camera.py`), the true orthonormal camera vertical axis is `cam.up_cam = normalize(cross(forward, right))`. When looking downward at pitch angle $\theta = 71.3^\circ$, `cam.up` was non-orthogonal to `cam.forward` by $18.7^\circ$. In the Metal shader, ray directions constructed via:
```metal
float3 ray_d = normalize(c_fwd + u * c_right + v * c_up);
```
tilted downward toward the ground plane, displacing the hit point by $7.62\,\text{cm}$ in 3D world space and $12.31\,\text{px}$ in screen space.

### Implementation:
In `metal2/renderer.py`:
```python
c_cam.up[0] = float(cam.up_cam[0])
c_cam.up[1] = float(cam.up_cam[1])
c_cam.up[2] = float(cam.up_cam[2])
```
### Verification:
Immediately reduced SDE on simple planar box shadows from **$12.31\,\text{px}$** to **$0.78\,\text{px}$** and increased Soft IoU from **$0.4921$** to **$0.9491$**.

---

## 3. Correction 2: Continuous Soft Shadow Metric Suite

### Problem:
Historical spikes evaluated shadows using a hard binary cutoff:
$$\mathcal{S}_{\text{binary}} = (V < 0.85)$$
For physically based area lights, large soft penumbras fluctuate between $0.80$ and $0.90$. A sub-percent variation in floating-point precision across GPU architectures caused entire penumbra bands to flip in and out of the binary mask, causing massive jumps in SDE and IoU despite sub-pixel visual alignment.

### Implementation:
Authored `metal2/shadow_evaluation.py` implementing five continuous, mathematically stable metrics:
1. **Continuous Soft IoU (Fuzzy Jaccard):**
   $$J_{\text{soft}}(O_A, O_B) = \frac{\sum_i \min(O_A[i], O_B[i])}{\sum_i \max(O_A[i], O_B[i])}$$
   where shadow opacity $O = 1.0 - V$.
2. **Opacity-Weighted Center of Mass SDE:**
   $$\bar{C} = \frac{\sum_i O[i] \cdot \mathbf{x}_i}{\sum_i O[i]}, \quad \text{SDE}_{\text{cont}} = \|\bar{C}_{\text{cand}} - \bar{C}_{\text{gt}}\|_2$$
3. **50% Isoline Contour Displacement:**
   Computes mean Euclidean distance between the 50% shadow boundary ($V = 0.50$) using Euclidean distance transforms.
4. **Penumbra Fidelity:**
   Measures L1 MAE and area ratio strictly inside the transition penumbra zone ($0.15 \le V \le 0.85$).
5. **Contact Grounding Integrity:**
   Measures minimum seam visibility $V_{\text{seam}} \le 0.05$ at the subject-receiver contact line.

### Verification:
Four automated unit tests in `metal2/tests/test_shadow_evaluation.py` passing with $100\%$ code coverage.

---

## 4. Correction 3: Native C3 Oklab Metal Dispatch

### Problem:
In the RS-METAL-2 prototype, the Gamut Mapping pass claimed a "382× speedup", but was actually executing a generic vector-add operation (`metal2_dispatch_vector_add`), leaving the actual C3 Oklab kernel unmeasured on GPU.

### Implementation:
1. Defined `metal2_dispatch_oklab_gamut_map` in `metal2/src/metal_bridge.h`:
```cpp
int metal2_dispatch_oklab_gamut_map(
    const float* in_rgb,
    float* out_rgb,
    uint32_t count,
    float* out_gpu_time_ms
);
```
2. Implemented kernel execution in `metal2/src/metal_bridge.mm` using the existing Metal shader `oklab_gamut_mapping_kernel`:
```objc
id<MTLCommandBuffer> cmd_buffer = [g_command_queue commandBuffer];
id<MTLComputeCommandEncoder> encoder = [cmd_buffer computeCommandEncoder];
[encoder setComputePipelineState:g_oklab_pipeline];
[encoder setBuffer:in_buf offset:0 atIndex:0];
[encoder setBuffer:out_buf offset:0 atIndex:1];
[encoder setBytes:&count length:sizeof(uint32_t) atIndex:2];
MTLSize threadsPerGrid = MTLSizeMake(count, 1, 1);
MTLSize threadsPerGroup = MTLSizeMake(tpg, 1, 1);
[encoder dispatchThreads:threadsPerGrid threadsPerThreadgroup:threadsPerGroup];
```
3. Bound C-types interface in `metal2/bridge.py` and updated `metal2/tests/test_metal_reconstruction.py`.

### Verification:
On 1080p full frame ($1920 \times 1080 = 2,073,600$ pixels):
- CPU Reference (NumPy): **$1,011.89\,\text{ms}$**
- Metal GPU Execution: **$1.414\,\text{ms}$**
- Hardware Acceleration Factor: **$715.6\times$ Real GPU Speedup** (L1 error $\le 1.83 \times 10^{-4}$ against CPU).

---

## 5. Correction 4: Mesh Bounding Box (AABB) Fast-Reject Culling

### Problem:
In RS-METAL-2, every shadow ray from every pixel on the ground plane tested all 280 triangles of the footwear mesh sequentially in a brute-force loop. For a 1080p image with 16 samples, this required:
$$2,073,600 \times 16 \times 280 = 9.28\,\text{Billion Ray-Triangle Tests}$$
causing GPU time on 1080p mesh scenes to spike to **$308.27\,\text{ms}$**.

### Implementation:
Added an analytical oriented/axis-aligned bounding box fast-reject test to `intersect_mesh` in `metal2/shaders/renderer.metal`:
```metal
inline bool intersect_mesh(
    float3 ray_o, float3 ray_d,
    constant const TriangleMesh* triangles, uint n_triangles,
    constant const ProxyParams& proxy,
    thread float& out_t, thread float3& out_normal
) {
    // Fast-reject bounding box culling
    float3 box_center = float3(proxy.position) + float3(0.0f, proxy.sq_exponents.x, 0.0f);
    float3 box_half = float3(proxy.half_extents.x + 0.02f, proxy.sq_exponents.x + 0.02f, proxy.sq_exponents.y + 0.02f);
    float3 oc = ray_o - box_center;
    float3 ro_local = mat3_transpose_mul_vec(proxy.rot_matrix, oc);
    float3 rd_local = mat3_transpose_mul_vec(proxy.rot_matrix, ray_d);

    float3 inv_d = float3(
        fabs(rd_local.x) > 1e-6 ? 1.0f / rd_local.x : (rd_local.x >= 0 ? 1e6f : -1e6f),
        fabs(rd_local.y) > 1e-6 ? 1.0f / rd_local.y : (rd_local.y >= 0 ? 1e6f : -1e6f),
        fabs(rd_local.z) > 1e-6 ? 1.0f / rd_local.z : (rd_local.z >= 0 ? 1e6f : -1e6f)
    );

    float3 t0 = (-box_half - ro_local) * inv_d;
    float3 t1 = (box_half - ro_local) * inv_d;
    float3 tmin_xyz = min(t0, t1);
    float3 tmax_xyz = max(t0, t1);

    float t_near = max(max(tmin_xyz.x, tmin_xyz.y), tmin_xyz.z);
    float t_far = min(min(tmax_xyz.x, tmax_xyz.y), tmax_xyz.z);

    if (t_near > t_far || t_far <= 1e-4f) {
        return false; // Fast reject without touching 280 triangles!
    }
    // Proceed to Möller-Trumbore triangle loop only if ray hits bounding box...
```

### Verification:
On M2_04 ($256 \times 384$ mesh):
- GPU Time before culling: **$15.15\,\text{ms}$**
- GPU Time after culling: **$0.28\,\text{ms} - 0.53\,\text{ms}$**
- Speedup: **$28.6\times - 54.1\times$ Execution Acceleration**!

---

## 6. Correction 5: Ray Acne Self-Intersection Guard

### Problem:
Shadow rays cast from receiver or proxy surfaces frequently suffered numerical grazing intersections with the emitter surface itself when $t_{\text{hit}} \approx 0.0$, causing dark pepper noise and false occlusion.

### Implementation:
Enforced explicit near-field self-intersection guards on all shadow ray tests in `metal2/shaders/renderer.metal`:
```metal
// Proxy occlusion
if (proxy.proxy_type == 0) {
    is_blocked = intersect_obb(p_bias, L_dir, proxy, t_hit, dummy_n) && (t_hit > 1e-3f) && (t_hit < dist - 1e-3f);
} else if (proxy.proxy_type == 1) {
    is_blocked = intersect_superquadric(p_bias, L_dir, proxy, t_hit, dummy_n) && (t_hit > 1e-3f) && (t_hit < dist - 1e-3f);
} else if (proxy.proxy_type == 2 && mesh_triangles) {
    is_blocked = intersect_mesh(p_bias, L_dir, mesh_triangles, proxy.num_triangles, proxy, t_hit, dummy_n) && (t_hit > 1e-3f) && (t_hit < dist - 1e-3f);
}

// Receiver self-shadowing
if (!is_blocked) {
    float t_rec_hit = 1e9f;
    bool hit_rec_shadow = false;
    if (receiver.receiver_type == 1) {
        hit_rec_shadow = intersect_cyclorama(p_bias, L_dir, receiver, t_rec_hit, dummy_n);
    }
    if (hit_rec_shadow && t_rec_hit > 1e-3f && t_rec_hit < dist - 1e-3f) {
        is_blocked = true;
    }
}
```

---

## 7. Correction 6: Decoupling Ray Culling Bounds from Contact Footprint

### Problem:
In the initial GPU implementation, `proxy.half_extents` was overloaded for both 3D ray culling and 2D ground contact footprint distance. Setting `half_extents.z = 0.49` for the mesh bounding box inadvertently expanded the ground contact shadow into a $1.0\,\text{m}$ black patch on the floor, shifting the shadow centroid.

### Implementation:
1. Assigned `c_proxy.half_extents` strictly to the contact boundary footprint ($0.175 \times 0.225\,\text{m}$), matching the CPU contact formulation.
2. Utilized the unused `c_proxy.sq_exponents` fields (`float2`, 8 bytes) to pass the 3D bounding box vertical offset and Z extent directly to `intersect_mesh`.

### Verification:
Direct parity comparison of Metal vs authoritative CPU Reference Renderer on M2_04:
- Continuous SDE: **$2.79\,\text{px}$** (Gate $\le 3.0\,\text{px}$)
- Contour Displacement: **$0.63\,\text{px}$**
- Continuous Soft IoU: **$0.8602$** (Gate $\ge 0.85$)
- Penumbra Area Ratio: **$1.0281$** ($2.8\%$ area parity)
- Direct Irradiance MAE: **$0.000414$**
