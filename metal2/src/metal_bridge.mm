#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include "metal_bridge.h"
#include <string.h>
#include <stdio.h>
#include <chrono>

static id<MTLDevice> g_device = nil;
static id<MTLCommandQueue> g_command_queue = nil;
static id<MTLLibrary> g_library = nil;
static id<MTLComputePipelineState> g_vec_add_pso = nil;
static id<MTLComputePipelineState> g_render_pso = nil;
static id<MTLComputePipelineState> g_e1_init_pso = nil;
static id<MTLComputePipelineState> g_box_h4_pso = nil;
static id<MTLComputePipelineState> g_box_v4_pso = nil;
static id<MTLComputePipelineState> g_e1_ab_pso = nil;
static id<MTLComputePipelineState> g_box_h2_pso = nil;
static id<MTLComputePipelineState> g_box_v2_pso = nil;
static id<MTLComputePipelineState> g_e1_recon_pso = nil;

struct PersistentBufferPool {
    uint32_t width = 0;
    uint32_t height = 0;
    
    id<MTLBuffer> buf_depth = nil;
    id<MTLBuffer> buf_norm = nil;
    id<MTLBuffer> buf_img = nil;
    id<MTLBuffer> buf_fg = nil;
    id<MTLBuffer> buf_prot = nil;
    id<MTLBuffer> buf_out_relit = nil;
    id<MTLBuffer> buf_out_vis = nil;
    id<MTLBuffer> buf_out_irr = nil;
    
    id<MTLBuffer> buf_triangles = nil;
    uint32_t num_triangles = 0;
    
    // E.1 Intermediate Buffers
    id<MTLBuffer> buf_stats4 = nil;     // float4
    id<MTLBuffer> buf_stats4_tmp = nil; // float4
    id<MTLBuffer> buf_mean4 = nil;      // float4
    id<MTLBuffer> buf_ab = nil;         // float2
    id<MTLBuffer> buf_ab_tmp = nil;     // float2
    id<MTLBuffer> buf_mean_ab = nil;    // float2
    
    uint32_t alloc_count = 0;
    uint32_t steady_frames = 0;
};
static PersistentBufferPool g_buffer_pool;

extern "C" {

int metal2_init_device() {
    @autoreleasepool {
        if (g_device != nil) {
            return METAL_SUCCESS;
        }
        g_device = MTLCreateSystemDefaultDevice();
        if (!g_device) {
            fprintf(stderr, "[METAL2 ERROR] Failed to create system default Metal device.\n");
            return METAL_ERROR_NO_DEVICE;
        }
        g_command_queue = [g_device newCommandQueue];
        if (!g_command_queue) {
            fprintf(stderr, "[METAL2 ERROR] Failed to create Metal command queue.\n");
            return METAL_ERROR_PIPELINE_CREATION;
        }
        return METAL_SUCCESS;
    }
}

int metal2_get_device_info(MetalDeviceInfo* out_info) {
    if (!out_info) return METAL_ERROR_INVALID_ARGUMENT;
    if (!g_device) {
        int err = metal2_init_device();
        if (err != METAL_SUCCESS) return err;
    }

    @autoreleasepool {
        const char* name = [[g_device name] UTF8String];
        strncpy(out_info->device_name, name ? name : "Unknown Apple GPU", sizeof(out_info->device_name) - 1);
        out_info->device_name[sizeof(out_info->device_name) - 1] = '\0';
        
        out_info->max_buffer_length = [g_device maxBufferLength];
        out_info->recommended_working_set_size = [g_device recommendedMaxWorkingSetSize];
        out_info->has_unified_memory = [g_device hasUnifiedMemory];
        
        MTLSize max_threads = [g_device maxThreadsPerThreadgroup];
        out_info->max_threads_per_threadgroup_x = (uint32_t)max_threads.width;
        out_info->max_threads_per_threadgroup_y = (uint32_t)max_threads.height;
        out_info->max_threads_per_threadgroup_z = (uint32_t)max_threads.depth;
        
        out_info->supports_ray_tracing = [g_device supportsFamily:MTLGPUFamilyApple8]; // M3/M4/M5 Ray Tracing
        return METAL_SUCCESS;
    }
}

int metal2_compile_shaders_from_source(const char* source_code) {
    if (!source_code) return METAL_ERROR_INVALID_ARGUMENT;
    if (!g_device) {
        int err = metal2_init_device();
        if (err != METAL_SUCCESS) return err;
    }

    @autoreleasepool {
        NSString* src = [NSString stringWithUTF8String:source_code];
        MTLCompileOptions* options = [[MTLCompileOptions alloc] init];
        options.fastMathEnabled = YES;
        if (@available(macOS 13.0, *)) {
            options.languageVersion = MTLLanguageVersion3_0;
        }

        NSError* error = nil;
        id<MTLLibrary> lib = [g_device newLibraryWithSource:src options:options error:&error];
        if (!lib || error) {
            fprintf(stderr, "[METAL2 ERROR] Shader compilation failed:\n%s\n",
                    [[error localizedDescription] UTF8String]);
            return METAL_ERROR_COMPILATION_FAILED;
        }

        g_library = lib;

        // Try to initialize basic vector_add pipeline if present
        id<MTLFunction> fn = [g_library newFunctionWithName:@"test_vector_add"];
        if (fn) {
            g_vec_add_pso = [g_device newComputePipelineStateWithFunction:fn error:&error];
            if (!g_vec_add_pso || error) {
                fprintf(stderr, "[METAL2 ERROR] Failed to create test_vector_add pipeline:\n%s\n",
                        [[error localizedDescription] UTF8String]);
            }
        }
        return METAL_SUCCESS;
    }
}

int metal2_dispatch_vector_add(
    const float* a_vec,
    const float* b_vec,
    float scalar,
    float* out_vec,
    uint32_t count,
    float* out_gpu_time_ms
) {
    if (!a_vec || !b_vec || !out_vec || count == 0) return METAL_ERROR_INVALID_ARGUMENT;
    if (!g_vec_add_pso) {
        // Compile default test shader if not yet compiled
        const char* default_test_shader =
            "#include <metal_stdlib>\n"
            "using namespace metal;\n"
            "kernel void test_vector_add(\n"
            "    device const float* a [[buffer(0)]],\n"
            "    device const float* b [[buffer(1)]],\n"
            "    constant float& scalar [[buffer(2)]],\n"
            "    device float* out [[buffer(3)]],\n"
            "    constant uint& count [[buffer(4)]],\n"
            "    uint id [[thread_position_in_grid]])\n"
            "{\n"
            "    if (id < count) {\n"
            "        out[id] = a[id] * scalar + b[id];\n"
            "    }\n"
            "}\n";
        int err = metal2_compile_shaders_from_source(default_test_shader);
        if (err != METAL_SUCCESS || !g_vec_add_pso) return METAL_ERROR_PIPELINE_CREATION;
    }

    @autoreleasepool {
        size_t byte_len = count * sizeof(float);
        
        // Use MTLResourceStorageModeShared for zero-copy UMA access on Apple Silicon
        id<MTLBuffer> buf_a = [g_device newBufferWithBytes:a_vec length:byte_len options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_b = [g_device newBufferWithBytes:b_vec length:byte_len options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_out = [g_device newBufferWithLength:byte_len options:MTLResourceStorageModeShared];
        
        if (!buf_a || !buf_b || !buf_out) {
            return METAL_ERROR_BUFFER_ALLOCATION;
        }

        id<MTLCommandBuffer> cmd_buf = [g_command_queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];
        
        [encoder setComputePipelineState:g_vec_add_pso];
        [encoder setBuffer:buf_a offset:0 atIndex:0];
        [encoder setBuffer:buf_b offset:0 atIndex:1];
        [encoder setBytes:&scalar length:sizeof(float) atIndex:2];
        [encoder setBuffer:buf_out offset:0 atIndex:3];
        [encoder setBytes:&count length:sizeof(uint32_t) atIndex:4];

        NSUInteger threadGroupSize = g_vec_add_pso.maxTotalThreadsPerThreadgroup;
        if (threadGroupSize > 256) threadGroupSize = 256;
        MTLSize threadsPerGroup = MTLSizeMake(threadGroupSize, 1, 1);
        MTLSize numGroups = MTLSizeMake((count + threadGroupSize - 1) / threadGroupSize, 1, 1);

        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];
        [encoder endEncoding];

        auto t_start = std::chrono::high_resolution_clock::now();
        [cmd_buf commit];
        [cmd_buf waitUntilCompleted];
        auto t_end = std::chrono::high_resolution_clock::now();

        if (cmd_buf.status == MTLCommandBufferStatusError) {
            fprintf(stderr, "[METAL2 ERROR] Command buffer failed: %s\n",
                    [[cmd_buf.error localizedDescription] UTF8String]);
            return METAL_ERROR_EXECUTION_FAILED;
        }

        // Copy result to destination pointer
        memcpy(out_vec, [buf_out contents], byte_len);

        if (out_gpu_time_ms) {
            if (@available(macOS 10.15, *)) {
                CFTimeInterval gpu_time = cmd_buf.GPUEndTime - cmd_buf.GPUStartTime;
                if (gpu_time > 0.0) {
                    *out_gpu_time_ms = (float)(gpu_time * 1000.0);
                } else {
                    double elapsed = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                    *out_gpu_time_ms = (float)elapsed;
                }
            } else {
                double elapsed = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                *out_gpu_time_ms = (float)elapsed;
            }
        }
        return METAL_SUCCESS;
    }
}

static id<MTLComputePipelineState> g_oklab_pso = nil;

int metal2_dispatch_oklab_gamut_map(
    const float* in_rgb,
    float* out_rgb,
    uint32_t count,
    float* out_gpu_time_ms
) {
    if (!in_rgb || !out_rgb || count == 0) {
        return METAL_ERROR_INVALID_ARGUMENT;
    }

    if (g_device == nil) {
        int err = metal2_init_device();
        if (err != METAL_SUCCESS) return err;
    }

    @autoreleasepool {
        if (!g_oklab_pso) {
            NSArray* candidate_paths = @[
                @"metal2/shaders/reconstruction.metal",
                @"shaders/reconstruction.metal",
                @"../shaders/reconstruction.metal",
                @"/Users/sumirdayal/religth studio/metal2/shaders/reconstruction.metal"
            ];
            NSString* shader_src = nil;
            for (NSString* p in candidate_paths) {
                if ([[NSFileManager defaultManager] fileExistsAtPath:p]) {
                    shader_src = [NSString stringWithContentsOfFile:p encoding:NSUTF8StringEncoding error:nil];
                    if (shader_src) break;
                }
            }

            if (!shader_src) {
                fprintf(stderr, "[METAL2 ERROR] reconstruction.metal not found.\n");
                return METAL_ERROR_COMPILATION_FAILED;
            }

            MTLCompileOptions* options = [[MTLCompileOptions alloc] init];
            if (@available(macOS 13.0, *)) {
                options.languageVersion = MTLLanguageVersion3_0;
            }

            NSError* err = nil;
            id<MTLLibrary> lib = [g_device newLibraryWithSource:shader_src options:options error:&err];
            if (!lib || err) {
                fprintf(stderr, "[METAL2 ERROR] Failed to compile reconstruction.metal: %s\n",
                        [[err localizedDescription] UTF8String]);
                return METAL_ERROR_COMPILATION_FAILED;
            }

            id<MTLFunction> fn = [lib newFunctionWithName:@"oklab_gamut_mapping_kernel"];
            if (!fn) {
                fprintf(stderr, "[METAL2 ERROR] Kernel oklab_gamut_mapping_kernel not found.\n");
                return METAL_ERROR_PIPELINE_CREATION;
            }

            g_oklab_pso = [g_device newComputePipelineStateWithFunction:fn error:&err];
            if (!g_oklab_pso || err) {
                fprintf(stderr, "[METAL2 ERROR] Pipeline creation failed: %s\n",
                        [[err localizedDescription] UTF8String]);
                return METAL_ERROR_PIPELINE_CREATION;
            }
        }

        size_t byte_len = (size_t)count * 3 * sizeof(float);
        id<MTLBuffer> buf_in = [g_device newBufferWithBytes:in_rgb length:byte_len options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_out = [g_device newBufferWithLength:byte_len options:MTLResourceStorageModeShared];

        if (!buf_in || !buf_out) {
            return METAL_ERROR_BUFFER_ALLOCATION;
        }

        id<MTLCommandBuffer> cmd_buf = [g_command_queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];

        [encoder setComputePipelineState:g_oklab_pso];
        [encoder setBuffer:buf_in offset:0 atIndex:0];
        [encoder setBuffer:buf_out offset:0 atIndex:1];
        [encoder setBytes:&count length:sizeof(uint32_t) atIndex:2];

        NSUInteger threadGroupSize = g_oklab_pso.maxTotalThreadsPerThreadgroup;
        if (threadGroupSize > 256) threadGroupSize = 256;
        MTLSize threadsPerGroup = MTLSizeMake(threadGroupSize, 1, 1);
        MTLSize numGroups = MTLSizeMake((count + threadGroupSize - 1) / threadGroupSize, 1, 1);

        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];
        [encoder endEncoding];

        auto t_start = std::chrono::high_resolution_clock::now();
        [cmd_buf commit];
        [cmd_buf waitUntilCompleted];
        auto t_end = std::chrono::high_resolution_clock::now();

        if (cmd_buf.status == MTLCommandBufferStatusError) {
            fprintf(stderr, "[METAL2 ERROR] Command buffer failed: %s\n",
                    [[cmd_buf.error localizedDescription] UTF8String]);
            return METAL_ERROR_EXECUTION_FAILED;
        }

        memcpy(out_rgb, [buf_out contents], byte_len);

        if (out_gpu_time_ms) {
            if (@available(macOS 10.15, *)) {
                CFTimeInterval gpu_time = cmd_buf.GPUEndTime - cmd_buf.GPUStartTime;
                if (gpu_time > 0.0) {
                    *out_gpu_time_ms = (float)(gpu_time * 1000.0);
                } else {
                    double elapsed = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                    *out_gpu_time_ms = (float)elapsed;
                }
            } else {
                double elapsed = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                *out_gpu_time_ms = (float)elapsed;
            }
        }
        return METAL_SUCCESS;
    }
}

int metal2_render_frame(
    const CCameraParams* cam,
    const CProxyParams* proxy,
    const CReceiverParams* receiver,
    const CLightParams* light,
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
    float* out_gpu_time_ms
) {
    if (!cam || !proxy || !receiver || !light || !depth_map || !normals_map ||
        !image_orig_srgb || !out_relit_srgb || !out_visibility || !out_irradiance) {
        return METAL_ERROR_INVALID_ARGUMENT;
    }

    if (!g_device) {
        int err = metal2_init_device();
        if (err != METAL_SUCCESS) return err;
    }

    @autoreleasepool {
        // Compile renderer shader if not yet initialized
        if (!g_render_pso) {
            // Find path to shaders/renderer.metal relative to current binary or project
            NSArray* candidate_paths = @[
                @"metal2/shaders/renderer.metal",
                @"shaders/renderer.metal",
                @"../shaders/renderer.metal",
                @"/Users/sumirdayal/religth studio/metal2/shaders/renderer.metal"
            ];
            NSString* shader_src = nil;
            for (NSString* p in candidate_paths) {
                if ([[NSFileManager defaultManager] fileExistsAtPath:p]) {
                    shader_src = [NSString stringWithContentsOfFile:p encoding:NSUTF8StringEncoding error:nil];
                    if (shader_src) break;
                }
            }

            if (!shader_src) {
                fprintf(stderr, "[METAL2 ERROR] renderer.metal not found.\n");
                return METAL_ERROR_COMPILATION_FAILED;
            }

            MTLCompileOptions* options = [[MTLCompileOptions alloc] init];
            if (@available(macOS 13.0, *)) {
                options.languageVersion = MTLLanguageVersion3_0;
            }

            NSError* err = nil;
            id<MTLLibrary> render_lib = [g_device newLibraryWithSource:shader_src options:options error:&err];
            if (!render_lib || err) {
                fprintf(stderr, "[METAL2 ERROR] Failed to compile renderer.metal:\n%s\n",
                        [[err localizedDescription] UTF8String]);
                return METAL_ERROR_COMPILATION_FAILED;
            }

            auto create_pso = [&](NSString* fn_name, id<MTLComputePipelineState>& out_pso) -> int {
                id<MTLFunction> fn = [render_lib newFunctionWithName:fn_name];
                if (!fn) {
                    fprintf(stderr, "[METAL2 ERROR] Function %s not found in library.\n", [fn_name UTF8String]);
                    return METAL_ERROR_PIPELINE_CREATION;
                }
                out_pso = [g_device newComputePipelineStateWithFunction:fn error:&err];
                if (!out_pso || err) {
                    fprintf(stderr, "[METAL2 ERROR] Failed to create pipeline state for %s:\n%s\n",
                            [fn_name UTF8String], [[err localizedDescription] UTF8String]);
                    return METAL_ERROR_PIPELINE_CREATION;
                }
                return METAL_SUCCESS;
            };

            int s;
            if ((s = create_pso(@"render_hybrid_studio_kernel", g_render_pso)) != METAL_SUCCESS) return s;
            if ((s = create_pso(@"e1_init_stats_kernel", g_e1_init_pso)) != METAL_SUCCESS) return s;
            if ((s = create_pso(@"box_filter_h_float4", g_box_h4_pso)) != METAL_SUCCESS) return s;
            if ((s = create_pso(@"box_filter_v_float4", g_box_v4_pso)) != METAL_SUCCESS) return s;
            if ((s = create_pso(@"e1_compute_ab_kernel", g_e1_ab_pso)) != METAL_SUCCESS) return s;
            if ((s = create_pso(@"box_filter_h_float2", g_box_h2_pso)) != METAL_SUCCESS) return s;
            if ((s = create_pso(@"box_filter_v_float2", g_box_v2_pso)) != METAL_SUCCESS) return s;
            if ((s = create_pso(@"e1_reconstruct_c3_kernel", g_e1_recon_pso)) != METAL_SUCCESS) return s;
        }

        uint32_t W = cam->width;
        uint32_t H = cam->height;
        size_t num_pixels = (size_t)W * H;

        size_t float_bytes = num_pixels * sizeof(float);
        size_t float2_bytes = num_pixels * sizeof(float) * 2;
        size_t float3_bytes = num_pixels * sizeof(float) * 3;
        size_t float4_bytes = num_pixels * sizeof(float) * 4;
        size_t mask_bytes = num_pixels * sizeof(uint8_t);

        // Persistent Buffer Pool Allocation / Resize Guard
        if (g_buffer_pool.width != W || g_buffer_pool.height != H || !g_buffer_pool.buf_depth) {
            g_buffer_pool.buf_depth = [g_device newBufferWithLength:float_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_norm = [g_device newBufferWithLength:float3_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_img = [g_device newBufferWithLength:float3_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_fg = [g_device newBufferWithLength:mask_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_prot = [g_device newBufferWithLength:mask_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_out_relit = [g_device newBufferWithLength:float3_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_out_vis = [g_device newBufferWithLength:float_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_out_irr = [g_device newBufferWithLength:float3_bytes options:MTLResourceStorageModeShared];

            // E.1 Intermediate Buffers
            g_buffer_pool.buf_stats4 = [g_device newBufferWithLength:float4_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_stats4_tmp = [g_device newBufferWithLength:float4_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_mean4 = [g_device newBufferWithLength:float4_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_ab = [g_device newBufferWithLength:float2_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_ab_tmp = [g_device newBufferWithLength:float2_bytes options:MTLResourceStorageModeShared];
            g_buffer_pool.buf_mean_ab = [g_device newBufferWithLength:float2_bytes options:MTLResourceStorageModeShared];

            g_buffer_pool.width = W;
            g_buffer_pool.height = H;
            g_buffer_pool.alloc_count++;
        } else {
            g_buffer_pool.steady_frames++;
        }

        if (!g_buffer_pool.buf_depth || !g_buffer_pool.buf_norm || !g_buffer_pool.buf_img ||
            !g_buffer_pool.buf_out_relit || !g_buffer_pool.buf_out_vis || !g_buffer_pool.buf_out_irr ||
            !g_buffer_pool.buf_stats4 || !g_buffer_pool.buf_mean4 || !g_buffer_pool.buf_mean_ab) {
            return METAL_ERROR_BUFFER_ALLOCATION;
        }

        // Copy input buffers into persistent shared UMA memory
        memcpy([g_buffer_pool.buf_depth contents], depth_map, float_bytes);
        memcpy([g_buffer_pool.buf_norm contents], normals_map, float3_bytes);
        memcpy([g_buffer_pool.buf_img contents], image_orig_srgb, float3_bytes);
        if (fg_mask) {
            memcpy([g_buffer_pool.buf_fg contents], fg_mask, mask_bytes);
        } else {
            memset([g_buffer_pool.buf_fg contents], 0, mask_bytes);
        }
        if (protected_mask) {
            memcpy([g_buffer_pool.buf_prot contents], protected_mask, mask_bytes);
        } else {
            memset([g_buffer_pool.buf_prot contents], 0, mask_bytes);
        }
        uint32_t has_prot = (protected_mask != nullptr) ? 1 : 0;

        if (triangles && num_triangles > 0) {
            if (!g_buffer_pool.buf_triangles || g_buffer_pool.num_triangles < num_triangles) {
                g_buffer_pool.buf_triangles = [g_device newBufferWithLength:num_triangles * sizeof(CTriangleMesh) options:MTLResourceStorageModeShared];
                g_buffer_pool.num_triangles = num_triangles;
            }
            memcpy([g_buffer_pool.buf_triangles contents], triangles, num_triangles * sizeof(CTriangleMesh));
        }

        id<MTLCommandBuffer> cmd_buf = [g_command_queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];

        // 16x16 2D Threadgroups
        MTLSize threadsPerGroup = MTLSizeMake(16, 16, 1);
        MTLSize numGroups = MTLSizeMake((W + 15) / 16, (H + 15) / 16, 1);

        // --- PASS 1: Direct 3D Lighting & Shadows ---
        [encoder setComputePipelineState:g_render_pso];
        [encoder setBytes:cam length:sizeof(CCameraParams) atIndex:0];
        [encoder setBytes:proxy length:sizeof(CProxyParams) atIndex:1];
        [encoder setBytes:receiver length:sizeof(CReceiverParams) atIndex:2];
        [encoder setBytes:light length:sizeof(CLightParams) atIndex:3];
        if (g_buffer_pool.buf_triangles && num_triangles > 0) {
            [encoder setBuffer:g_buffer_pool.buf_triangles offset:0 atIndex:4];
        } else {
            [encoder setBuffer:g_buffer_pool.buf_depth offset:0 atIndex:4]; // Dummy binding
        }
        [encoder setBuffer:g_buffer_pool.buf_depth offset:0 atIndex:5];
        [encoder setBuffer:g_buffer_pool.buf_norm offset:0 atIndex:6];
        [encoder setBuffer:g_buffer_pool.buf_fg offset:0 atIndex:7];
        [encoder setBuffer:g_buffer_pool.buf_prot offset:0 atIndex:8];
        [encoder setBuffer:g_buffer_pool.buf_img offset:0 atIndex:9];
        [encoder setBuffer:g_buffer_pool.buf_out_relit offset:0 atIndex:10];
        [encoder setBuffer:g_buffer_pool.buf_out_vis offset:0 atIndex:11];
        [encoder setBuffer:g_buffer_pool.buf_out_irr offset:0 atIndex:12];
        [encoder setBytes:&has_prot length:sizeof(uint32_t) atIndex:13];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        // --- PASS 2: E.1 Guidance & Target Shading Ratio Initialization ---
        float ambient_fill = 0.15f;
        int e1_radius = 16;
        float e1_eps = 0.0004f; // 0.02^2

        [encoder setComputePipelineState:g_e1_init_pso];
        [encoder setBuffer:g_buffer_pool.buf_img offset:0 atIndex:0];
        [encoder setBuffer:g_buffer_pool.buf_out_irr offset:0 atIndex:1];
        [encoder setBuffer:g_buffer_pool.buf_out_vis offset:0 atIndex:2];
        [encoder setBuffer:g_buffer_pool.buf_prot offset:0 atIndex:3];
        [encoder setBuffer:g_buffer_pool.buf_stats4 offset:0 atIndex:4];
        [encoder setBytes:&ambient_fill length:sizeof(float) atIndex:5];
        [encoder setBytes:&has_prot length:sizeof(uint32_t) atIndex:6];
        [encoder setBytes:&W length:sizeof(uint32_t) atIndex:7];
        [encoder setBytes:&H length:sizeof(uint32_t) atIndex:8];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        // --- PASS 3: Box Filter Horizontal (float4) ---
        [encoder setComputePipelineState:g_box_h4_pso];
        [encoder setBuffer:g_buffer_pool.buf_stats4 offset:0 atIndex:0];
        [encoder setBuffer:g_buffer_pool.buf_stats4_tmp offset:0 atIndex:1];
        [encoder setBytes:&e1_radius length:sizeof(int) atIndex:2];
        [encoder setBytes:&W length:sizeof(uint32_t) atIndex:3];
        [encoder setBytes:&H length:sizeof(uint32_t) atIndex:4];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        // --- PASS 4: Box Filter Vertical (float4) ---
        [encoder setComputePipelineState:g_box_v4_pso];
        [encoder setBuffer:g_buffer_pool.buf_stats4_tmp offset:0 atIndex:0];
        [encoder setBuffer:g_buffer_pool.buf_mean4 offset:0 atIndex:1];
        [encoder setBytes:&e1_radius length:sizeof(int) atIndex:2];
        [encoder setBytes:&W length:sizeof(uint32_t) atIndex:3];
        [encoder setBytes:&H length:sizeof(uint32_t) atIndex:4];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        // --- PASS 5: Compute Linear Coefficients a and b ---
        [encoder setComputePipelineState:g_e1_ab_pso];
        [encoder setBuffer:g_buffer_pool.buf_mean4 offset:0 atIndex:0];
        [encoder setBuffer:g_buffer_pool.buf_ab offset:0 atIndex:1];
        [encoder setBytes:&e1_eps length:sizeof(float) atIndex:2];
        [encoder setBytes:&W length:sizeof(uint32_t) atIndex:3];
        [encoder setBytes:&H length:sizeof(uint32_t) atIndex:4];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        // --- PASS 6: Box Filter Horizontal (float2) ---
        [encoder setComputePipelineState:g_box_h2_pso];
        [encoder setBuffer:g_buffer_pool.buf_ab offset:0 atIndex:0];
        [encoder setBuffer:g_buffer_pool.buf_ab_tmp offset:0 atIndex:1];
        [encoder setBytes:&e1_radius length:sizeof(int) atIndex:2];
        [encoder setBytes:&W length:sizeof(uint32_t) atIndex:3];
        [encoder setBytes:&H length:sizeof(uint32_t) atIndex:4];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        // --- PASS 7: Box Filter Vertical (float2) ---
        [encoder setComputePipelineState:g_box_v2_pso];
        [encoder setBuffer:g_buffer_pool.buf_ab_tmp offset:0 atIndex:0];
        [encoder setBuffer:g_buffer_pool.buf_mean_ab offset:0 atIndex:1];
        [encoder setBytes:&e1_radius length:sizeof(int) atIndex:2];
        [encoder setBytes:&W length:sizeof(uint32_t) atIndex:3];
        [encoder setBytes:&H length:sizeof(uint32_t) atIndex:4];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        // --- PASS 8: Final E.1 Reconstruction with C3 Oklab Constant-Hue Gamut Mapping ---
        [encoder setComputePipelineState:g_e1_recon_pso];
        [encoder setBuffer:g_buffer_pool.buf_img offset:0 atIndex:0];
        [encoder setBuffer:g_buffer_pool.buf_mean_ab offset:0 atIndex:1];
        [encoder setBuffer:g_buffer_pool.buf_prot offset:0 atIndex:2];
        [encoder setBuffer:g_buffer_pool.buf_out_relit offset:0 atIndex:3];
        [encoder setBytes:&has_prot length:sizeof(uint32_t) atIndex:4];
        [encoder setBytes:&W length:sizeof(uint32_t) atIndex:5];
        [encoder setBytes:&H length:sizeof(uint32_t) atIndex:6];
        [encoder dispatchThreadgroups:numGroups threadsPerThreadgroup:threadsPerGroup];

        [encoder endEncoding];

        auto t_start = std::chrono::high_resolution_clock::now();
        [cmd_buf commit];
        [cmd_buf waitUntilCompleted];
        auto t_end = std::chrono::high_resolution_clock::now();

        if (cmd_buf.status == MTLCommandBufferStatusError) {
            fprintf(stderr, "[METAL2 ERROR] Render command buffer failed: %s\n",
                    [[cmd_buf.error localizedDescription] UTF8String]);
            return METAL_ERROR_EXECUTION_FAILED;
        }

        // Copy outputs back to host pointers
        memcpy(out_relit_srgb, [g_buffer_pool.buf_out_relit contents], float3_bytes);
        memcpy(out_visibility, [g_buffer_pool.buf_out_vis contents], float_bytes);
        memcpy(out_irradiance, [g_buffer_pool.buf_out_irr contents], float3_bytes);

        if (out_gpu_time_ms) {
            if (@available(macOS 10.15, *)) {
                CFTimeInterval gpu_time = cmd_buf.GPUEndTime - cmd_buf.GPUStartTime;
                if (gpu_time > 0.0) {
                    *out_gpu_time_ms = (float)(gpu_time * 1000.0);
                } else {
                    double elapsed = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                    *out_gpu_time_ms = (float)elapsed;
                }
            } else {
                double elapsed = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                *out_gpu_time_ms = (float)elapsed;
            }
        }
        return METAL_SUCCESS;
    }
}

int metal2_get_buffer_pool_stats(uint32_t* out_alloc_count, uint32_t* out_steady_frames) {
    if (out_alloc_count) *out_alloc_count = g_buffer_pool.alloc_count;
    if (out_steady_frames) *out_steady_frames = g_buffer_pool.steady_frames;
    return METAL_SUCCESS;
}

int metal2_reset_buffer_pool(void) {
    g_buffer_pool.buf_depth = nil;
    g_buffer_pool.buf_norm = nil;
    g_buffer_pool.buf_img = nil;
    g_buffer_pool.buf_fg = nil;
    g_buffer_pool.buf_prot = nil;
    g_buffer_pool.buf_out_relit = nil;
    g_buffer_pool.buf_out_vis = nil;
    g_buffer_pool.buf_out_irr = nil;
    g_buffer_pool.buf_triangles = nil;
    g_buffer_pool.num_triangles = 0;
    g_buffer_pool.buf_stats4 = nil;
    g_buffer_pool.buf_stats4_tmp = nil;
    g_buffer_pool.buf_mean4 = nil;
    g_buffer_pool.buf_ab = nil;
    g_buffer_pool.buf_ab_tmp = nil;
    g_buffer_pool.buf_mean_ab = nil;
    g_buffer_pool.width = 0;
    g_buffer_pool.height = 0;
    g_buffer_pool.alloc_count = 0;
    g_buffer_pool.steady_frames = 0;
    return METAL_SUCCESS;
}

void metal2_shutdown() {
    @autoreleasepool {
        metal2_reset_buffer_pool();
        g_render_pso = nil;
        g_e1_init_pso = nil;
        g_box_h4_pso = nil;
        g_box_v4_pso = nil;
        g_e1_ab_pso = nil;
        g_box_h2_pso = nil;
        g_box_v2_pso = nil;
        g_e1_recon_pso = nil;
        g_vec_add_pso = nil;
        g_oklab_pso = nil;
        g_library = nil;
        g_command_queue = nil;
        g_device = nil;
    }
}

} // extern "C"
