#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Device Diagnostics structure
typedef struct {
    char device_name[256];
    uint64_t max_buffer_length;
    uint64_t recommended_working_set_size;
    uint32_t max_threads_per_threadgroup_x;
    uint32_t max_threads_per_threadgroup_y;
    uint32_t max_threads_per_threadgroup_z;
    bool has_unified_memory;
    bool supports_ray_tracing;
} MetalDeviceInfo;

// Pipeline status & error return codes
enum MetalStatus {
    METAL_SUCCESS = 0,
    METAL_ERROR_NO_DEVICE = -1,
    METAL_ERROR_COMPILATION_FAILED = -2,
    METAL_ERROR_PIPELINE_CREATION = -3,
    METAL_ERROR_BUFFER_ALLOCATION = -4,
    METAL_ERROR_EXECUTION_FAILED = -5,
    METAL_ERROR_INVALID_ARGUMENT = -6
};

// Lifecycle & Diagnostics
int metal2_init_device();
int metal2_get_device_info(MetalDeviceInfo* out_info);
int metal2_compile_shaders_from_source(const char* source_code);
void metal2_shutdown();

// Basic Compute Dispatch for Phase 1 verification
// Computes out_vec = a_vec * scalar + b_vec on GPU
int metal2_dispatch_vector_add(
    const float* a_vec,
    const float* b_vec,
    float scalar,
    float* out_vec,
    uint32_t count,
    float* out_gpu_time_ms
);

// C3 Oklab Constant-Hue Gamut Mapping Compute Dispatch
int metal2_dispatch_oklab_gamut_map(
    const float* in_rgb,
    float* out_rgb,
    uint32_t count,
    float* out_gpu_time_ms
);

// Full Scene-Driven 3D Rendering Pipeline (Phases 2-6)
typedef struct {
    float position[3];
    float forward[3];
    float right[3];
    float up[3];
    float fov_rad;
    uint32_t width;
    uint32_t height;
} CCameraParams;

typedef struct {
    float position[3];
    float normal[3];
    float u_tangent[3];
    float v_bitangent[3];
    float dimensions[2];
    float color_rgb[3];
    float intensity;
    uint32_t energy_convention;
    uint32_t n_samples;
    uint32_t seed;
    uint32_t cast_shadows;
    uint32_t enabled;
    float padding;
} CLightParams;

typedef struct {
    uint32_t proxy_type;
    float position[3];
    float half_extents[3];
    float rot_matrix[9];
    float sq_exponents[2];
    uint32_t num_triangles;
} CProxyParams;

typedef struct {
    uint32_t receiver_type;
    float ground_y;
    float cove_center_yz[2];
    float cove_radius;
    float wall_z;
} CReceiverParams;

typedef struct {
    float base_color[3];
    float roughness;
    float metallic;
    float specular_f0;
    float specular_intensity;
    uint32_t enable_specular;
    uint32_t specular_only;
    float _pad[7];
} CMaterialParams;

typedef struct {
    uint32_t enabled;
    float intensity;
    float rotation_rad;
    float diffuse_weight;
    float specular_weight;
    float tint_rgb[3];
    uint32_t has_env_map;
    float _pad[7];
} CEnvironmentParams;

typedef struct {
    float v0[3];
    float v1[3];
    float v2[3];
    float normal[3];
} CTriangleMesh;

int metal2_set_environment_maps(
    const float* irr_map,
    uint32_t irr_w,
    uint32_t irr_h,
    const float* spec_04,
    const float* spec_50,
    uint32_t spec_w,
    uint32_t spec_h,
    const float* brdf_lut,
    uint32_t lut_size
);

int metal2_render_frame(
    const CCameraParams* cam,
    const CProxyParams* proxy,
    const CReceiverParams* receiver,
    const CLightParams* lights,
    uint32_t num_lights,
    const CMaterialParams* material,
    const CTriangleMesh* triangles,
    uint32_t num_triangles,
    const float* depth_map,
    const float* normals_map,
    const uint8_t* fg_mask,
    const uint8_t* protected_mask,
    const float* image_orig_srgb,
    float* out_relit_srgb,
    float* out_visibility,
    float* out_irradiance,
    float* out_specular,
    float* out_gpu_time_ms,
    const CEnvironmentParams* env_params
);

// Buffer Pool Diagnostics
int metal2_get_buffer_pool_stats(uint32_t* out_alloc_count, uint32_t* out_steady_frames);
int metal2_reset_buffer_pool(void);

#ifdef __cplusplus
}
#endif
