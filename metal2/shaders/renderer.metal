#include <metal_stdlib>
using namespace metal;

// -----------------------------------------------------------------------------
// 1. DATA STRUCTURES & UNIFORMS
// -----------------------------------------------------------------------------

struct CameraParams {
    packed_float3 position;
    packed_float3 forward;
    packed_float3 right;
    packed_float3 up;
    float fov_rad;
    uint width;
    uint height;
};

struct LightParams {
    packed_float3 position;
    packed_float3 normal;
    packed_float3 u_tangent;
    packed_float3 v_bitangent;
    packed_float2 dimensions; // width, height
    packed_float3 color_rgb;
    float intensity;
    uint energy_convention; // 0: FIXED_RADIANCE, 1: FIXED_POWER
    uint n_samples;
    uint seed;
};

struct ProxyParams {
    uint proxy_type;          // 0: OBB, 1: SUPERQUADRIC, 2: MESH, 3: SPHERE
    packed_float3 position;
    packed_float3 half_extents;
    float rot_matrix[9];      // 3x3 rotation matrix (row-major)
    packed_float2 sq_exponents; // e1, e2
    uint num_triangles;
};

struct ReceiverParams {
    uint receiver_type;       // 0: PLANE, 1: CYCLORAMA
    float ground_y;
    packed_float2 cove_center_yz;
    float cove_radius;
    float wall_z;
};

struct TriangleMesh {
    packed_float3 v0;
    packed_float3 v1;
    packed_float3 v2;
    packed_float3 normal;
};

// -----------------------------------------------------------------------------
// 2. MATRIX & VECTOR HELPERS
// -----------------------------------------------------------------------------

inline float3 mat3_mul_vec(constant const float* m, float3 v) {
    return float3(
        m[0] * v.x + m[1] * v.y + m[2] * v.z,
        m[3] * v.x + m[4] * v.y + m[5] * v.z,
        m[6] * v.x + m[7] * v.y + m[8] * v.z
    );
}

inline float3 mat3_transpose_mul_vec(constant const float* m, float3 v) {
    return float3(
        m[0] * v.x + m[3] * v.y + m[6] * v.z,
        m[1] * v.x + m[4] * v.y + m[7] * v.z,
        m[2] * v.x + m[5] * v.y + m[8] * v.z
    );
}

// -----------------------------------------------------------------------------
// 3. GEOMETRIC INTERSECTION HELPERS
// -----------------------------------------------------------------------------

inline bool intersect_obb(
    float3 ray_o, float3 ray_d,
    constant const ProxyParams& proxy,
    thread float& out_t, thread float3& out_normal
) {
    float3 p_pos = float3(proxy.position);
    float3 h = float3(proxy.half_extents);
    float3 oc = ray_o - p_pos;
    
    // Transform ray to OBB local space
    float3 ro_local = mat3_transpose_mul_vec(proxy.rot_matrix, oc);
    float3 rd_local = mat3_transpose_mul_vec(proxy.rot_matrix, ray_d);

    float3 inv_d = float3(
        fabs(rd_local.x) > 1e-6 ? 1.0f / rd_local.x : (rd_local.x >= 0 ? 1e6f : -1e6f),
        fabs(rd_local.y) > 1e-6 ? 1.0f / rd_local.y : (rd_local.y >= 0 ? 1e6f : -1e6f),
        fabs(rd_local.z) > 1e-6 ? 1.0f / rd_local.z : (rd_local.z >= 0 ? 1e6f : -1e6f)
    );

    float3 t0 = (-h - ro_local) * inv_d;
    float3 t1 = (h - ro_local) * inv_d;
    float3 tmin_xyz = min(t0, t1);
    float3 tmax_xyz = max(t0, t1);

    float t_near = max(max(tmin_xyz.x, tmin_xyz.y), tmin_xyz.z);
    float t_far = min(min(tmax_xyz.x, tmax_xyz.y), tmax_xyz.z);

    if (t_near <= t_far && t_far > 1e-4f) {
        float t_hit = (t_near > 1e-4f) ? t_near : t_far;
        out_t = t_hit;
        
        float3 p_local = ro_local + t_hit * rd_local;
        float3 n_local = float3(0.0f);
        float eps = 1e-3f;
        if (fabs(p_local.x - (-h.x)) < eps) n_local = float3(-1.0f, 0.0f, 0.0f);
        else if (fabs(p_local.x - h.x) < eps) n_local = float3(1.0f, 0.0f, 0.0f);
        else if (fabs(p_local.y - (-h.y)) < eps) n_local = float3(0.0f, -1.0f, 0.0f);
        else if (fabs(p_local.y - h.y) < eps) n_local = float3(0.0f, 1.0f, 0.0f);
        else if (fabs(p_local.z - (-h.z)) < eps) n_local = float3(0.0f, 0.0f, -1.0f);
        else if (fabs(p_local.z - h.z) < eps) n_local = float3(0.0f, 0.0f, 1.0f);

        out_normal = normalize(mat3_mul_vec(proxy.rot_matrix, n_local));
        return true;
    }
    return false;
}

inline float eval_sq_inside_outside(float3 p, float3 radii, float2 sq_e) {
    float nx = fabs(p.x) / max(radii.x, 1e-4f);
    float ny = fabs(p.y) / max(radii.y, 1e-4f);
    float nz = fabs(p.z) / max(radii.z, 1e-4f);
    float e1 = max(sq_e.x, 0.05f);
    float e2 = max(sq_e.y, 0.05f);
    
    float p_xy = pow(nx, 2.0f / e2) + pow(ny, 2.0f / e2);
    float val = pow(max(p_xy, 1e-6f), e2 / e1) + pow(nz, 2.0f / e1);
    float rho = pow(max(val, 1e-6f), e1 * 0.5f);
    return rho - 1.0f;
}

inline bool intersect_superquadric(
    float3 ray_o, float3 ray_d,
    constant const ProxyParams& proxy,
    thread float& out_t, thread float3& out_normal
) {
    float3 p_pos = float3(proxy.position);
    float3 radii = float3(proxy.half_extents);
    float2 sq_e = float2(proxy.sq_exponents);
    float3 oc = ray_o - p_pos;
    float3 ro_local = mat3_transpose_mul_vec(proxy.rot_matrix, oc);
    float3 rd_local = mat3_transpose_mul_vec(proxy.rot_matrix, ray_d);

    // Bounding sphere
    float R_bound = max(max(radii.x, radii.y), radii.z) * 1.5f;
    float b = dot(ro_local, rd_local);
    float c = dot(ro_local, ro_local) - R_bound * R_bound;
    float disc = b * b - c;
    if (disc < 0.0f) return false;
    
    float sqrt_disc = sqrt(disc);
    float t_enter = max(0.0f, -b - sqrt_disc);
    float t_exit = -b + sqrt_disc;
    if (t_exit < 1e-4f) return false;

    // 32-step interval search
    const int N_STEPS = 32;
    float dt = (t_exit - t_enter) / float(N_STEPS);
    float t_curr = t_enter;
    float f_prev = eval_sq_inside_outside(ro_local + t_curr * rd_local, radii, sq_e);

    for (int i = 0; i < N_STEPS; ++i) {
        float t_next = t_curr + dt;
        float f_next = eval_sq_inside_outside(ro_local + t_next * rd_local, radii, sq_e);
        if (f_prev > 0.0f && f_next <= 0.0f) {
            // Root bracket [t_curr, t_next] found
            float ta = t_curr;
            float tb = t_next;
            // 4 bisection steps for guaranteed interval reduction (factor of 16)
            for (int k = 0; k < 4; ++k) {
                float t_mid = 0.5f * (ta + tb);
                float f_mid = eval_sq_inside_outside(ro_local + t_mid * rd_local, radii, sq_e);
                if (f_mid > 0.0f) {
                    ta = t_mid;
                } else {
                    tb = t_mid;
                }
            }
            // 1 safe secant refinement step on normalized metric
            float fa = eval_sq_inside_outside(ro_local + ta * rd_local, radii, sq_e);
            float fb = eval_sq_inside_outside(ro_local + tb * rd_local, radii, sq_e);
            float denom = fb - fa;
            float t_root = (fabs(denom) > 1e-6f) ? (ta - fa * (tb - ta) / denom) : ta;
            t_root = clamp(t_root, min(ta, tb), max(ta, tb));
            out_t = t_root;
            
            // Gradient normal
            float3 p_hit = ro_local + t_root * rd_local;
            float e1 = max(sq_e.x, 0.05f);
            float e2 = max(sq_e.y, 0.05f);
            float nx = fabs(p_hit.x) / max(radii.x, 1e-4f);
            float ny = fabs(p_hit.y) / max(radii.y, 1e-4f);
            float nz = fabs(p_hit.z) / max(radii.z, 1e-4f);
            float p_xy = pow(nx, 2.0f / e2) + pow(ny, 2.0f / e2);
            float prefix = pow(max(p_xy, 1e-6f), e2 / e1 - 1.0f);
            
            float gx = (2.0f / (radii.x * e1)) * prefix * pow(max(nx, 1e-6f), 2.0f / e2 - 1.0f) * sign(p_hit.x);
            float gy = (2.0f / (radii.y * e1)) * prefix * pow(max(ny, 1e-6f), 2.0f / e2 - 1.0f) * sign(p_hit.y);
            float gz = (2.0f / (radii.z * e1)) * pow(max(nz, 1e-6f), 2.0f / e1 - 1.0f) * sign(p_hit.z);
            float3 n_local = normalize(float3(gx, gy, gz));
            out_normal = normalize(mat3_mul_vec(proxy.rot_matrix, n_local));
            return true;
        }
        t_curr = t_next;
        f_prev = f_next;
    }
    return false;
}

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
        return false;
    }

    float best_t = 1e9f;
    float3 best_norm = float3(0.0f);
    bool hit_any = false;

    for (uint i = 0; i < n_triangles; ++i) {
        float3 v0 = float3(triangles[i].v0);
        float3 v1 = float3(triangles[i].v1);
        float3 v2 = float3(triangles[i].v2);
        
        float3 e1 = v1 - v0;
        float3 e2 = v2 - v0;
        float3 pvec = cross(ray_d, e2);
        float det = dot(e1, pvec);
        if (fabs(det) < 1e-6f) continue;
        
        float inv_det = 1.0f / det;
        float3 tvec = ray_o - v0;
        float u = dot(tvec, pvec) * inv_det;
        if (u < 0.0f || u > 1.0f) continue;
        
        float3 qvec = cross(tvec, e1);
        float v = dot(ray_d, qvec) * inv_det;
        if (v < 0.0f || u + v > 1.0f) continue;
        
        float t = dot(e2, qvec) * inv_det;
        if (t > 1e-4f && t < best_t) {
            best_t = t;
            best_norm = float3(triangles[i].normal);
            hit_any = true;
        }
    }
    if (hit_any) {
        out_t = best_t;
        out_normal = best_norm;
        return true;
    }
    return false;
}

inline bool intersect_sphere(
    float3 ray_o, float3 ray_d,
    constant const ProxyParams& proxy,
    thread float& out_t, thread float3& out_normal
) {
    float3 center = float3(proxy.position);
    float radius = proxy.half_extents.x;
    float3 oc = ray_o - center;
    float b = dot(oc, ray_d);
    
    // Numerically robust closest-approach formulation
    float3 p_perp = oc - b * ray_d;
    float d_perp_sq = dot(p_perp, p_perp);
    float r_sq = radius * radius;
    if (d_perp_sq > r_sq) return false;
    
    float half_chord = sqrt(max(0.0f, r_sq - d_perp_sq));
    float t0 = -b - half_chord;
    float t1 = -b + half_chord;
    
    if (t0 > 1e-4f) {
        out_t = t0;
        out_normal = normalize(oc + t0 * ray_d);
        return true;
    }
    if (t1 > 1e-4f) {
        out_t = t1;
        out_normal = normalize(oc + t1 * ray_d);
        return true;
    }
    return false;
}

inline bool intersect_cyclorama(
    float3 ray_o, float3 ray_d,
    constant const ReceiverParams& rec,
    thread float& out_t, thread float3& out_normal
) {
    float best_t = 1e9f;
    float3 best_n = float3(0.0f, 1.0f, 0.0f);
    bool hit_any = false;

    // 1. Floor (Z >= cove_center_z)
    if (fabs(ray_d.y) > 1e-5f) {
        float t_fl = (rec.ground_y - ray_o.y) / ray_d.y;
        float pz_fl = ray_o.z + t_fl * ray_d.z;
        if (t_fl > 1e-4f && pz_fl >= rec.cove_center_yz.y) {
            if (t_fl < best_t) {
                best_t = t_fl;
                best_n = float3(0.0f, 1.0f, 0.0f);
                hit_any = true;
            }
        }
    }

    // 2. Vertical Wall (Z = wall_z, Y >= cove_top)
    if (fabs(ray_d.z) > 1e-5f) {
        float t_w = (rec.wall_z - ray_o.z) / ray_d.z;
        float py_w = ray_o.y + t_w * ray_d.y;
        if (t_w > 1e-4f && py_w >= rec.cove_center_yz.x) {
            if (t_w < best_t) {
                best_t = t_w;
                best_n = float3(0.0f, 0.0f, 1.0f);
                hit_any = true;
            }
        }
    }

    // 3. Cove Fillet Cylinder
    float dy = ray_o.y - rec.cove_center_yz.x;
    float dz = ray_o.z - rec.cove_center_yz.y;
    float a = ray_d.y * ray_d.y + ray_d.z * ray_d.z;
    if (a > 1e-6f) {
        float b = 2.0f * (dy * ray_d.y + dz * ray_d.z);
        float c = dy * dy + dz * dz - rec.cove_radius * rec.cove_radius;
        float disc = b * b - 4.0f * a * c;
        if (disc >= 0.0f) {
            float sqrt_disc = sqrt(disc);
            float t1 = (-b - sqrt_disc) / (2.0f * a);
            float t2 = (-b + sqrt_disc) / (2.0f * a);
            float cand_ts[2] = {t1, t2};
            
            for (int k = 0; k < 2; ++k) {
                float tc = cand_ts[k];
                if (tc > 1e-4f && tc < best_t) {
                    float py = ray_o.y + tc * ray_d.y;
                    float pz = ray_o.z + tc * ray_d.z;
                    if (py >= rec.ground_y - 1e-4f && py <= rec.cove_center_yz.x + 1e-4f &&
                        pz >= rec.wall_z - 1e-4f && pz <= rec.cove_center_yz.y + 1e-4f) {
                        best_t = tc;
                        float3 cyl_n = normalize(float3(0.0f, -(py - rec.cove_center_yz.x), -(pz - rec.cove_center_yz.y)));
                        best_n = cyl_n;
                        hit_any = true;
                    }
                }
            }
        }
    }

    if (hit_any) {
        out_t = best_t;
        out_normal = best_n;
        return true;
    }
    return false;
}

inline bool intersect_ground_plane(
    float3 ray_o, float3 ray_d,
    float ground_y,
    thread float& out_t, thread float3& out_normal
) {
    if (fabs(ray_d.y) > 1e-5f) {
        float t = (ground_y - ray_o.y) / ray_d.y;
        if (t > 1e-4f) {
            out_t = t;
            out_normal = float3(0.0f, 1.0f, 0.0f);
            return true;
        }
    }
    return false;
}

// -----------------------------------------------------------------------------
// 4. MAIN RENDERING COMPUTE KERNEL
// -----------------------------------------------------------------------------

kernel void render_hybrid_studio_kernel(
    constant CameraParams& cam               [[buffer(0)]],
    constant ProxyParams& proxy               [[buffer(1)]],
    constant ReceiverParams& receiver         [[buffer(2)]],
    constant LightParams& light               [[buffer(3)]],
    constant TriangleMesh* mesh_triangles     [[buffer(4)]],
    device const float* depth_map             [[buffer(5)]],
    device const packed_float3* normals_map   [[buffer(6)]],
    device const uint8_t* fg_mask             [[buffer(7)]],
    device const uint8_t* protected_mask      [[buffer(8)]],
    device const packed_float3* image_orig_srgb [[buffer(9)]],
    device packed_float3* out_relit_srgb      [[buffer(10)]],
    device float* out_visibility              [[buffer(11)]],
    device packed_float3* out_irradiance      [[buffer(12)]],
    constant uint& has_protected_mask         [[buffer(13)]],
    uint2 pixel_coord                         [[thread_position_in_grid]]
) {
    if (pixel_coord.x >= cam.width || pixel_coord.y >= cam.height) return;
    uint idx = pixel_coord.y * cam.width + pixel_coord.x;

    // 1. Primary Camera Ray
    float aspect = float(cam.width) / float(cam.height);
    float half_h = tan(cam.fov_rad * 0.5f);
    float half_w = half_h * aspect;
    float u = (2.0f * (float(pixel_coord.x) + 0.5f) / float(cam.width) - 1.0f) * half_w;
    float v = (1.0f - 2.0f * (float(pixel_coord.y) + 0.5f) / float(cam.height)) * half_h;
    
    float3 c_pos = float3(cam.position);
    float3 c_fwd = float3(cam.forward);
    float3 c_right = float3(cam.right);
    float3 c_up = float3(cam.up);
    float3 ray_d = normalize(u * c_right + v * c_up + c_fwd);
    float3 ray_o = c_pos;

    // 2. Scene Intersections
    bool is_fg = fg_mask ? (fg_mask[idx] != 0) : false;
    
    float rec_t = 1e9f;
    float3 rec_norm = float3(0.0f, 1.0f, 0.0f);
    bool hit_rec = false;
    if (receiver.receiver_type == 1) {
        hit_rec = intersect_cyclorama(ray_o, ray_d, receiver, rec_t, rec_norm);
    } else {
        hit_rec = intersect_ground_plane(ray_o, ray_d, receiver.ground_y, rec_t, rec_norm);
    }

    bool is_receiver = (!is_fg) && hit_rec;
    bool is_sky = (!is_fg) && (!hit_rec);

    float3 surface_pos;
    float3 surface_norm;

    if (is_fg) {
        float cos_forward = max(0.1f, dot(ray_d, c_fwd));
        float t_depth = (depth_map[idx] * 2.5f + 0.5f) / cos_forward;
        surface_pos = ray_o + t_depth * ray_d;
        surface_norm = normalize(float3(normals_map[idx]));
    } else if (is_receiver) {
        surface_pos = ray_o + rec_t * ray_d;
        surface_norm = normalize(rec_norm);
    } else {
        // Sky pixel: far plane, normal pointing opposite to ray
        surface_pos = ray_o + 50.0f * ray_d;
        surface_norm = -ray_d;
    }

    // Sky pixels: unshadowed, zero direct irradiance
    if (is_sky) {
        out_visibility[idx] = 1.0f;
        out_irradiance[idx] = packed_float3(0.0f, 0.0f, 0.0f);
        out_relit_srgb[idx] = image_orig_srgb[idx];
        return;
    }

    // 3. Stratified Area Light Direct Illumination & Shadow Transport
    float3 light_pos = float3(light.position);
    float3 light_norm = float3(light.normal);
    float3 u_tan = float3(light.u_tangent);
    float3 v_bit = float3(light.v_bitangent);
    float2 l_dim = float2(light.dimensions);
    float area = l_dim.x * l_dim.y;
    
    float radiance = (light.energy_convention == 1) ? (light.intensity / max(area * 3.141592653589793f, 1e-4f)) : light.intensity;
    float3 emitter_radiance = float3(light.color_rgb) * radiance;

    uint n_samples = max(light.n_samples, 1u);
    uint grid_dim = uint(sqrt(float(n_samples)));
    if (grid_dim < 1) grid_dim = 1;

    float3 irr_acc = float3(0.0f);
    float vis_acc = 0.0f;

    float3 p_bias = surface_pos + 1e-3f * surface_norm;

    for (uint sy = 0; sy < grid_dim; ++sy) {
        for (uint sx = 0; sx < grid_dim; ++sx) {
            float su = (float(sx) + 0.5f) / float(grid_dim) - 0.5f;
            float sv = (float(sy) + 0.5f) / float(grid_dim) - 0.5f;
            float3 p_sample = light_pos + (su * l_dim.x) * u_tan + (sv * l_dim.y) * v_bit;

            float3 L_vec = p_sample - p_bias;
            float dist_sq = max(dot(L_vec, L_vec), 1e-6f);
            float dist = sqrt(dist_sq);
            float3 L_dir = L_vec / dist;

            float cos_surf = max(dot(surface_norm, L_dir), 0.0f);
            float cos_light = max(dot(-light_norm, L_dir), 0.0f);

            // Shadow Ray Intersection
            bool is_blocked = false;
            float t_hit = 1e9f;
            float3 dummy_n;

            // 1. Occlusion by subject proxy
            if (proxy.proxy_type == 0) {
                is_blocked = intersect_obb(p_bias, L_dir, proxy, t_hit, dummy_n) && (t_hit > 1e-3f) && (t_hit < dist - 1e-3f);
            } else if (proxy.proxy_type == 1) {
                is_blocked = intersect_superquadric(p_bias, L_dir, proxy, t_hit, dummy_n) && (t_hit > 1e-3f) && (t_hit < dist - 1e-3f);
            } else if (proxy.proxy_type == 2 && mesh_triangles) {
                is_blocked = intersect_mesh(p_bias, L_dir, mesh_triangles, proxy.num_triangles, proxy, t_hit, dummy_n) && (t_hit > 1e-3f) && (t_hit < dist - 1e-3f);
            } else if (proxy.proxy_type == 3) {
                is_blocked = intersect_sphere(p_bias, L_dir, proxy, t_hit, dummy_n) && (t_hit > 1e-3f) && (t_hit < dist - 1e-3f);
            }

            // 2. Occlusion by receiver geometry (cyclorama cove self-shadowing)
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

            if (!is_blocked) {
                vis_acc += 1.0f;
            }

            float geom_factor = (cos_surf * cos_light) / dist_sq;
            irr_acc += emitter_radiance * (geom_factor * (area / float(grid_dim * grid_dim)));
        }
    }

    float visibility = vis_acc / float(grid_dim * grid_dim);
    out_irradiance[idx] = packed_float3(irr_acc.x, irr_acc.y, irr_acc.z);

    // 4. Contact Occlusion on Receiver
    if (is_receiver) {
        float dist_to_ground = fabs(surface_pos.y - receiver.ground_y);
        if (dist_to_ground < 0.04f) {
            float dist_to_edge = 0.0f;
            float3 p_rel = surface_pos - float3(proxy.position);
            float3 p_loc = mat3_transpose_mul_vec(proxy.rot_matrix, p_rel);

            if (proxy.proxy_type == 1) {
                // Superquadric: analytical superellipse boundary distance in horizontal XZ plane
                float rx = proxy.half_extents.x;
                float rz = proxy.half_extents.z;
                float e2 = max(proxy.sq_exponents.y, 0.05f);
                float theta = atan2(p_loc.z, p_loc.x);
                float cos_t = cos(theta);
                float sin_t = sin(theta);
                float xb = rx * sign(cos_t) * pow(fabs(cos_t), 2.0f / e2);
                float zb = rz * sign(sin_t) * pow(fabs(sin_t), 2.0f / e2);
                float d_pts = sqrt(p_loc.x * p_loc.x + p_loc.z * p_loc.z);
                float d_bnd = sqrt(xb * xb + zb * zb);
                dist_to_edge = max(0.0f, d_pts - d_bnd);
            } else if (proxy.proxy_type == 3) {
                // Sphere: exact circular contact footprint at tangential base point
                float d_pts = length(p_loc.xz);
                dist_to_edge = d_pts;
            } else {
                // OBB & default: 2D box boundary distance
                float hx = proxy.half_extents.x;
                float hz = proxy.half_extents.z;
                float dx = max(0.0f, fabs(p_loc.x) - hx);
                float dz = max(0.0f, fabs(p_loc.z) - hz);
                dist_to_edge = sqrt(dx * dx + dz * dz);
            }

            float r_contact = 0.08f;
            float contact_weight = clamp(1.0f - (dist_to_edge / r_contact), 0.0f, 1.0f);
            float contact_att = contact_weight * contact_weight * (3.0f - 2.0f * contact_weight);
            float c_contact = 1.0f - 0.95f * contact_att;
            visibility = min(visibility, c_contact);
        }
    }

    out_visibility[idx] = visibility;

    // 5. Non-Destructive Linear Reconstruction & Protected Mask Pass-through
    if (has_protected_mask != 0 && protected_mask[idx] != 0) {
        out_relit_srgb[idx] = image_orig_srgb[idx]; // Bitwise zero-mutation guarantee
        return;
    }

    // Direct linear relighting: Y_relit = Y_orig * (irr * vis + ambient)
    float3 orig_srgb = float3(image_orig_srgb[idx]);
    float3 orig_lin = pow(orig_srgb, 2.2f);
    float3 relit_lin = orig_lin * (irr_acc * visibility + 0.15f);
    float3 relit_srgb = clamp(pow(relit_lin, 1.0f / 2.2f), 0.0f, 1.0f);
    out_relit_srgb[idx] = packed_float3(relit_srgb.x, relit_srgb.y, relit_srgb.z);
}

// -----------------------------------------------------------------------------
// 5. E.1 GUIDED-FILTER REGULARIZATION & C3 OKLAB CONSTANT-HUE GAMUT MAPPING
// -----------------------------------------------------------------------------

inline float3 srgb_to_linear_exact(float3 srgb) {
    float3 lin;
    lin.r = (srgb.r <= 0.04045f) ? (srgb.r / 12.92f) : pow((srgb.r + 0.055f) / 1.055f, 2.4f);
    lin.g = (srgb.g <= 0.04045f) ? (srgb.g / 12.92f) : pow((srgb.g + 0.055f) / 1.055f, 2.4f);
    lin.b = (srgb.b <= 0.04045f) ? (srgb.b / 12.92f) : pow((srgb.b + 0.055f) / 1.055f, 2.4f);
    return lin;
}

inline float3 linear_to_srgb_exact(float3 lin) {
    float3 srgb;
    srgb.r = (lin.r <= 0.0031308f) ? (lin.r * 12.92f) : (1.055f * pow(max(lin.r, 0.0f), 1.0f / 2.4f) - 0.055f);
    srgb.g = (lin.g <= 0.0031308f) ? (lin.g * 12.92f) : (1.055f * pow(max(lin.g, 0.0f), 1.0f / 2.4f) - 0.055f);
    srgb.b = (lin.b <= 0.0031308f) ? (lin.b * 12.92f) : (1.055f * pow(max(lin.b, 0.0f), 1.0f / 2.4f) - 0.055f);
    return clamp(srgb, 0.0f, 1.0f);
}

inline float3 linear_srgb_to_oklab(float3 c) {
    float l = 0.4122214708f * c.r + 0.5363325363f * c.g + 0.0514459929f * c.b;
    float m = 0.2119034982f * c.r + 0.6806995451f * c.g + 0.1073969566f * c.b;
    float s = 0.0883024619f * c.r + 0.2817188376f * c.g + 0.6299787005f * c.b;

    float l_ = pow(max(l, 0.0f), 1.0f / 3.0f);
    float m_ = pow(max(m, 0.0f), 1.0f / 3.0f);
    float s_ = pow(max(s, 0.0f), 1.0f / 3.0f);

    return float3(
        0.2104542553f * l_ + 0.7936177850f * m_ - 0.0040720468f * s_,
        1.9779984951f * l_ - 2.4285922050f * m_ + 0.4505937099f * s_,
        0.0259040371f * l_ + 0.7827717662f * m_ - 0.8086757660f * s_
    );
}

inline float3 oklab_to_linear_srgb(float3 c) {
    float l_ = c.x + 0.3963377774f * c.y + 0.2158037573f * c.z;
    float m_ = c.x - 0.1055613458f * c.y - 0.0638541728f * c.z;
    float s_ = c.x - 0.0894841775f * c.y - 1.2914855480f * c.z;

    float l = l_ * l_ * l_;
    float m = m_ * m_ * m_;
    float s = s_ * s_ * s_;

    return float3(
        +4.0767416621f * l - 3.3077115913f * m + 0.2309699292f * s,
        -1.2684380046f * l + 2.6097574011f * m - 0.3413193965f * s,
        -0.0041960863f * l - 0.7034186147f * m + 1.7076147010f * s
    );
}

inline bool is_in_srgb_gamut(float3 rgb) {
    return (rgb.r >= -1e-4f && rgb.r <= 1.0f + 1e-4f &&
            rgb.g >= -1e-4f && rgb.g <= 1.0f + 1e-4f &&
            rgb.b >= -1e-4f && rgb.b <= 1.0f + 1e-4f);
}

inline int reflect_index(int k, int n) {
    while (k < 0 || k >= n) {
        if (k < 0) {
            k = -1 - k;
        } else if (k >= n) {
            k = 2 * n - 1 - k;
        }
    }
    return k;
}

// Pass 1: Initialize E.1 Guidance & Target Shading Ratio into float4
kernel void e1_init_stats_kernel(
    device const packed_float3* image_orig_srgb [[buffer(0)]],
    device const packed_float3* direct_irr      [[buffer(1)]],
    device const float* direct_vis              [[buffer(2)]],
    device const uint8_t* protected_mask        [[buffer(3)]],
    device float4* out_stats4                   [[buffer(4)]],
    constant float& ambient_fill                [[buffer(5)]],
    constant uint& has_protected_mask           [[buffer(6)]],
    constant uint& width                        [[buffer(7)]],
    constant uint& height                       [[buffer(8)]],
    uint2 coord                                 [[thread_position_in_grid]]
) {
    if (coord.x >= width || coord.y >= height) return;
    uint idx = coord.y * width + coord.x;

    float3 srgb = float3(image_orig_srgb[idx]);
    float3 lin = srgb_to_linear_exact(srgb);
    float Y_orig = 0.2126f * lin.r + 0.7152f * lin.g + 0.0722f * lin.b;

    float3 irr = float3(direct_irr[idx]);
    float irr_luma = 0.2126f * irr.r + 0.7152f * irr.g + 0.0722f * irr.b;
    float vis = direct_vis[idx];

    float R_target = clamp(ambient_fill + irr_luma * vis, 0.05f, 20.0f);

    // Highlight protection shoulder
    float m_high = clamp((Y_orig - 0.75f) / (0.98f - 0.75f), 0.0f, 1.0f);
    m_high = m_high * m_high * (3.0f - 2.0f * m_high);
    float R_eff = (1.0f - m_high) * R_target + m_high * 1.0f;

    if (has_protected_mask != 0 && protected_mask[idx] != 0) {
        R_eff = 1.0f;
    }

    float rho = log(max(R_eff, 1e-4f));

    // Pack: (I, p, I*I, I*p)
    out_stats4[idx] = float4(Y_orig, rho, Y_orig * Y_orig, Y_orig * rho);
}

// Pass 2: Separable Horizontal Box Filter for float4
kernel void box_filter_h_float4(
    device const float4* src                    [[buffer(0)]],
    device float4* dst                          [[buffer(1)]],
    constant int& radius                        [[buffer(2)]],
    constant uint& width                        [[buffer(3)]],
    constant uint& height                       [[buffer(4)]],
    uint2 coord                                 [[thread_position_in_grid]]
) {
    if (coord.x >= width || coord.y >= height) return;
    int y = int(coord.y);
    int x = int(coord.x);
    int W = int(width);

    float4 sum = float4(0.0f);
    for (int dx = -radius; dx <= radius; ++dx) {
        int rx = reflect_index(x + dx, W);
        sum += src[y * W + rx];
    }
    dst[y * W + x] = sum / float(2 * radius + 1);
}

// Pass 3: Separable Vertical Box Filter for float4
kernel void box_filter_v_float4(
    device const float4* src                    [[buffer(0)]],
    device float4* dst                          [[buffer(1)]],
    constant int& radius                        [[buffer(2)]],
    constant uint& width                        [[buffer(3)]],
    constant uint& height                       [[buffer(4)]],
    uint2 coord                                 [[thread_position_in_grid]]
) {
    if (coord.x >= width || coord.y >= height) return;
    int y = int(coord.y);
    int x = int(coord.x);
    int W = int(width);
    int H = int(height);

    float4 sum = float4(0.0f);
    for (int dy = -radius; dy <= radius; ++dy) {
        int ry = reflect_index(y + dy, H);
        sum += src[ry * W + x];
    }
    dst[y * W + x] = sum / float(2 * radius + 1);
}

// Pass 4: Compute Linear Coefficients a and b from mean4
kernel void e1_compute_ab_kernel(
    device const float4* mean4                  [[buffer(0)]],
    device float2* out_ab                       [[buffer(1)]],
    constant float& eps                         [[buffer(2)]],
    constant uint& width                        [[buffer(3)]],
    constant uint& height                       [[buffer(4)]],
    uint2 coord                                 [[thread_position_in_grid]]
) {
    if (coord.x >= width || coord.y >= height) return;
    uint idx = coord.y * width + coord.x;

    float4 m = mean4[idx];
    float mean_I = m.x;
    float mean_p = m.y;
    float mean_II = m.z;
    float mean_Ip = m.w;

    float var_I = max(0.0f, mean_II - mean_I * mean_I);
    float cov_Ip = mean_Ip - mean_I * mean_p;

    float a = cov_Ip / (var_I + eps);
    float b = mean_p - a * mean_I;

    out_ab[idx] = float2(a, b);
}

// Pass 5: Separable Horizontal Box Filter for float2
kernel void box_filter_h_float2(
    device const float2* src                    [[buffer(0)]],
    device float2* dst                          [[buffer(1)]],
    constant int& radius                        [[buffer(2)]],
    constant uint& width                        [[buffer(3)]],
    constant uint& height                       [[buffer(4)]],
    uint2 coord                                 [[thread_position_in_grid]]
) {
    if (coord.x >= width || coord.y >= height) return;
    int y = int(coord.y);
    int x = int(coord.x);
    int W = int(width);

    float2 sum = float2(0.0f);
    for (int dx = -radius; dx <= radius; ++dx) {
        int rx = reflect_index(x + dx, W);
        sum += src[y * W + rx];
    }
    dst[y * W + x] = sum / float(2 * radius + 1);
}

// Pass 6: Separable Vertical Box Filter for float2
kernel void box_filter_v_float2(
    device const float2* src                    [[buffer(0)]],
    device float2* dst                          [[buffer(1)]],
    constant int& radius                        [[buffer(2)]],
    constant uint& width                        [[buffer(3)]],
    constant uint& height                       [[buffer(4)]],
    uint2 coord                                 [[thread_position_in_grid]]
) {
    if (coord.x >= width || coord.y >= height) return;
    int y = int(coord.y);
    int x = int(coord.x);
    int W = int(width);
    int H = int(height);

    float2 sum = float2(0.0f);
    for (int dy = -radius; dy <= radius; ++dy) {
        int ry = reflect_index(y + dy, H);
        sum += src[ry * W + x];
    }
    dst[y * W + x] = sum / float(2 * radius + 1);
}

// Pass 7: Final E.1 Reconstruction with C3 Oklab Constant-Hue Gamut Mapping
kernel void e1_reconstruct_c3_kernel(
    device const packed_float3* image_orig_srgb [[buffer(0)]],
    device const float2* mean_ab                [[buffer(1)]],
    device const uint8_t* protected_mask        [[buffer(2)]],
    device packed_float3* out_relit_srgb        [[buffer(3)]],
    constant uint& has_protected_mask           [[buffer(4)]],
    constant uint& width                        [[buffer(5)]],
    constant uint& height                       [[buffer(6)]],
    uint2 coord                                 [[thread_position_in_grid]]
) {
    if (coord.x >= width || coord.y >= height) return;
    uint idx = coord.y * width + coord.x;

    if (has_protected_mask != 0 && protected_mask[idx] != 0) {
        out_relit_srgb[idx] = image_orig_srgb[idx];
        return;
    }

    float3 srgb_orig = float3(image_orig_srgb[idx]);
    float3 lin_orig = srgb_to_linear_exact(srgb_orig);
    float Y_orig = 0.2126f * lin_orig.r + 0.7152f * lin_orig.g + 0.0722f * lin_orig.b;

    float2 ab = mean_ab[idx];
    float rho_bar = ab.x * Y_orig + ab.y;
    float Y_relit = max(1e-4f, Y_orig * exp(rho_bar));

    // C3 Oklab Constant-Hue Gamut Mapping
    float scale = Y_relit / max(Y_orig, 1e-6f);
    float3 ref_rgb = lin_orig * scale;
    float3 lab_ref = linear_srgb_to_oklab(max(ref_rgb, 0.0f));
    float3 lab_orig = linear_srgb_to_oklab(max(lin_orig, 0.0f));

    float L_target = lab_ref.x;
    float L_disp = (L_target <= 0.90f) ? max(1e-4f, L_target) : (0.90f + 0.10f * tanh((L_target - 0.90f) / 0.10f));

    float a_orig = lab_orig.y;
    float b_orig = lab_orig.z;
    float chroma = sqrt(a_orig * a_orig + b_orig * b_orig);
    float a_init = (chroma < 1e-4f) ? 0.0f : a_orig;
    float b_init = (chroma < 1e-4f) ? 0.0f : b_orig;

    float3 test_rgb = oklab_to_linear_srgb(float3(L_disp, a_init, b_init));
    float3 final_lin;

    if (is_in_srgb_gamut(test_rgb) || chroma < 1e-4f) {
        final_lin = clamp(test_rgb, 0.0f, 1.0f);
    } else {
        float t_low = 0.0f;
        float t_high = 1.0f;
        for (int iter = 0; iter < 8; ++iter) {
            float t_mid = 0.5f * (t_low + t_high);
            float3 rgb_mid = oklab_to_linear_srgb(float3(L_disp, a_init * t_mid, b_init * t_mid));
            if (is_in_srgb_gamut(rgb_mid)) {
                t_low = t_mid;
            } else {
                t_high = t_mid;
            }
        }
        final_lin = clamp(oklab_to_linear_srgb(float3(L_disp, a_init * t_low, b_init * t_low)), 0.0f, 1.0f);
    }

    float3 final_srgb = linear_to_srgb_exact(final_lin);
    out_relit_srgb[idx] = packed_float3(final_srgb.x, final_srgb.y, final_srgb.z);
}
