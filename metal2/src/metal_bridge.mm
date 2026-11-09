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

            id<MTLFunction> fn = [render_lib newFunctionWithName:@"render_hybrid_studio_kernel"];
            if (!fn) {
                fprintf(stderr, "[METAL2 ERROR] Function render_hybrid_studio_kernel not found in library.\n");
                return METAL_ERROR_PIPELINE_CREATION;
            }

            g_render_pso = [g_device newComputePipelineStateWithFunction:fn error:&err];
            if (!g_render_pso || err) {
                fprintf(stderr, "[METAL2 ERROR] Failed to create pipeline state for render_hybrid_studio_kernel:\n%s\n",
                        [[err localizedDescription] UTF8String]);
                return METAL_ERROR_PIPELINE_CREATION;
            }
        }

        uint32_t W = cam->width;
        uint32_t H = cam->height;
        size_t num_pixels = (size_t)W * H;

        size_t float_bytes = num_pixels * sizeof(float);
        size_t float3_bytes = num_pixels * sizeof(float) * 3;
        size_t mask_bytes = num_pixels * sizeof(uint8_t);

        // Allocate Shared UMA Buffers
        id<MTLBuffer> buf_depth = [g_device newBufferWithBytes:depth_map length:float_bytes options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_norm = [g_device newBufferWithBytes:normals_map length:float3_bytes options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_img = [g_device newBufferWithBytes:image_orig_srgb length:float3_bytes options:MTLResourceStorageModeShared];

        id<MTLBuffer> buf_fg = fg_mask ? [g_device newBufferWithBytes:fg_mask length:mask_bytes options:MTLResourceStorageModeShared] : [g_device newBufferWithLength:16 options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_prot = protected_mask ? [g_device newBufferWithBytes:protected_mask length:mask_bytes options:MTLResourceStorageModeShared] : [g_device newBufferWithLength:16 options:MTLResourceStorageModeShared];
        uint32_t has_prot = (protected_mask != nullptr) ? 1 : 0;

        id<MTLBuffer> buf_out_relit = [g_device newBufferWithLength:float3_bytes options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_out_vis = [g_device newBufferWithLength:float_bytes options:MTLResourceStorageModeShared];
        id<MTLBuffer> buf_out_irr = [g_device newBufferWithLength:float3_bytes options:MTLResourceStorageModeShared];

        id<MTLBuffer> buf_triangles = nil;
        if (triangles && num_triangles > 0) {
            buf_triangles = [g_device newBufferWithBytes:triangles length:num_triangles * sizeof(CTriangleMesh) options:MTLResourceStorageModeShared];
        }

        if (!buf_depth || !buf_norm || !buf_img || !buf_out_relit || !buf_out_vis || !buf_out_irr) {
            return METAL_ERROR_BUFFER_ALLOCATION;
        }

        id<MTLCommandBuffer> cmd_buf = [g_command_queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];

        [encoder setComputePipelineState:g_render_pso];
        [encoder setBytes:cam length:sizeof(CCameraParams) atIndex:0];
        [encoder setBytes:proxy length:sizeof(CProxyParams) atIndex:1];
        [encoder setBytes:receiver length:sizeof(CReceiverParams) atIndex:2];
        [encoder setBytes:light length:sizeof(CLightParams) atIndex:3];
        if (buf_triangles) {
            [encoder setBuffer:buf_triangles offset:0 atIndex:4];
        } else {
            [encoder setBuffer:buf_depth offset:0 atIndex:4]; // Dummy binding
        }
        [encoder setBuffer:buf_depth offset:0 atIndex:5];
        [encoder setBuffer:buf_norm offset:0 atIndex:6];
        [encoder setBuffer:buf_fg offset:0 atIndex:7];
        [encoder setBuffer:buf_prot offset:0 atIndex:8];
        [encoder setBuffer:buf_img offset:0 atIndex:9];
        [encoder setBuffer:buf_out_relit offset:0 atIndex:10];
        [encoder setBuffer:buf_out_vis offset:0 atIndex:11];
        [encoder setBuffer:buf_out_irr offset:0 atIndex:12];
        [encoder setBytes:&has_prot length:sizeof(uint32_t) atIndex:13];

        // 16x16 2D Threadgroups
        MTLSize threadsPerGroup = MTLSizeMake(16, 16, 1);
        MTLSize numGroups = MTLSizeMake((W + 15) / 16, (H + 15) / 16, 1);

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
        memcpy(out_relit_srgb, [buf_out_relit contents], float3_bytes);
        memcpy(out_visibility, [buf_out_vis contents], float_bytes);
        memcpy(out_irradiance, [buf_out_irr contents], float3_bytes);

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

void metal2_shutdown() {
    @autoreleasepool {
        g_render_pso = nil;
        g_vec_add_pso = nil;
        g_library = nil;
        g_command_queue = nil;
        g_device = nil;
    }
}

} // extern "C"
