#include <metal_stdlib>
using namespace metal;

// Relight Studio v3.0 — Metal Compute Shader
// Full RGB Linear Reconstruction with Detail Coupling (lambda) and Soft Shoulder Rolloff.

struct Uniforms {
    float lambda;           // Detail coupling parameter in [0, 1]
    float shoulder_start;   // Start threshold for soft highlight rolloff (e.g. 0.85)
    float pad0;
    float pad1;
};

constant float3 LUMA_COEFFS = float3(0.2126f, 0.7152f, 0.0722f);

kernel void relight_v3_reconstruction(
    texture2d<float, access::read> in_linear_rgb   [[texture(0)]],
    texture2d<float, access::read> in_yb           [[texture(1)]],
    texture2d<float, access::read> in_yd           [[texture(2)]],
    texture2d<float, access::read> in_ratio_r      [[texture(3)]],
    texture2d<float, access::write> out_rgb        [[texture(4)]],
    constant Uniforms &uniforms                    [[buffer(0)]],
    uint2 gid                                      [[thread_position_in_grid]])
{
    if (gid.x >= out_rgb.get_width() || gid.y >= out_rgb.get_height()) {
        return;
    }

    float4 rgb = in_linear_rgb.read(gid);
    float y_b = in_yb.read(gid).r;
    float y_d = in_yd.read(gid).r;
    float r = in_ratio_r.read(gid).r;

    // 1. Current Linear Luminance
    float y_orig = max(dot(rgb.rgb, LUMA_COEFFS), 1e-6f);

    // 2. Detail Coupling with Parameter Lambda: Y' = Yb * R + Yd * (R^lambda)
    float r_clamped = max(r, 1e-4f);
    float r_lambda = pow(r_clamped, uniforms.lambda);
    float y_prime = max(y_b * r + y_d * r_lambda, 0.0f);

    // 3. Chromaticity Preservation: Scale original RGB by luminance ratio
    float3 c_lin = rgb.rgb * (y_prime / y_orig);

    // 4. Soft Highlight Shoulder Rolloff (prevents harsh clipping above 1.0)
    float shoulder = uniforms.shoulder_start;
    float3 out_color = c_lin;
    
    // Per-channel soft rolloff
    for (int i = 0; i < 3; ++i) {
        if (out_color[i] > shoulder) {
            float excess = out_color[i] - shoulder;
            out_color[i] = shoulder + (excess / (1.0f + excess)) * (1.0f - shoulder);
        }
    }

    out_rgb.write(float4(clamp(out_color, 0.0f, 1.0f), rgb.a), gid);
}
