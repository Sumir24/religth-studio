#pragma once

#ifdef __METAL_VERSION__
#include <metal_stdlib>
using namespace metal;
#else
#include <simd/simd.h>
typedef simd_float2 float2;
typedef simd_float3 float3;
typedef simd_float4 float4;
typedef simd_float3x3 float3x3;
typedef simd_uint2 uint2;
typedef uint32_t uint;
#endif

// Camera parameters
struct CameraParams {
    float3 position;
    float3 forward;
    float3 right;
    float3 up;
    float fov_rad;
    uint width;
    uint height;
    float near_clip;
    float far_clip;
};

// Rectangular Area Light parameters
struct LightParams {
    float3 position;
    float3 normal;
    float3 u_tangent;
    float3 v_bitangent;
    float2 dimensions;
    float3 color_rgb;
    float intensity;
    uint energy_convention; // 0: FIXED_RADIANCE, 1: FIXED_POWER
    uint n_samples;
    uint seed;
};

// Subject Proxy parameters
struct ProxyParams {
    uint proxy_type;        // 0: OBB, 1: SUPERQUADRIC, 2: MESH
    float3 position;
    float3 half_extents;    // For OBB or Superquadric radii
    float3x3 rotation_matrix;
    float2 sq_exponents;    // e1 (vertical), e2 (horizontal)
    uint num_triangles;
    uint bvh_root_index;
};

// Receiver parameters
struct ReceiverParams {
    uint receiver_type;     // 0: PLANE, 1: CYCLORAMA
    float ground_y;
    float2 cove_center_yz;
    float cove_radius;
    float wall_z;
};

// Triangle for LowPolyMesh
struct TriangleMesh {
    float3 v0;
    float3 v1;
    float3 v2;
    float3 normal;
};

// BVH Node for accelerated mesh ray tracing
struct BVHNode {
    float3 aabb_min;
    float3 aabb_max;
    int left_child;         // < 0 implies leaf node with -left_child - 1 start face index
    int right_child;        // Count of triangles if leaf
};

// Primary Ray Hit result
struct RayHit {
    bool has_hit;
    bool is_foreground;
    bool is_receiver;
    bool is_sky;
    float t;
    float3 position;
    float3 normal;
};

