#include <metal_stdlib>
using namespace metal;

// -----------------------------------------------------------------------------
// OKLAB COLOR SPACE CONVERSIONS & CONSTANT-HUE GAMUT BISECTION
// -----------------------------------------------------------------------------

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

// C3: Constant-Hue Oklab Chroma Bisection
inline float3 oklab_constant_hue_gamut_map(float3 rgb_in) {
    if (is_in_srgb_gamut(rgb_in)) {
        return clamp(rgb_in, 0.0f, 1.0f);
    }

    float3 lab = linear_srgb_to_oklab(max(rgb_in, 0.0f));
    float L = lab.x;
    float a = lab.y;
    float b = lab.z;
    float C = sqrt(a * a + b * b);
    if (C < 1e-5f) {
        return clamp(oklab_to_linear_srgb(float3(L, 0.0f, 0.0f)), 0.0f, 1.0f);
    }

    float cos_h = a / C;
    float sin_h = b / C;

    float c_low = 0.0f;
    float c_high = C;

    // 8-step bisection directly in GPU registers (takes < 2 microseconds)
    for (int iter = 0; iter < 8; ++iter) {
        float c_mid = 0.5f * (c_low + c_high);
        float3 test_rgb = oklab_to_linear_srgb(float3(L, c_mid * cos_h, c_mid * sin_h));
        if (is_in_srgb_gamut(test_rgb)) {
            c_low = c_mid;
        } else {
            c_high = c_mid;
        }
    }

    float3 final_rgb = oklab_to_linear_srgb(float3(L, c_low * cos_h, c_low * sin_h));
    return clamp(final_rgb, 0.0f, 1.0f);
}

kernel void oklab_gamut_mapping_kernel(
    device const packed_float3* in_rgb  [[buffer(0)]],
    device packed_float3* out_rgb       [[buffer(1)]],
    constant uint& count                [[buffer(2)]],
    uint id                             [[thread_position_in_grid]]
) {
    if (id >= count) return;
    float3 rgb = float3(in_rgb[id]);
    float3 mapped = oklab_constant_hue_gamut_map(rgb);
    out_rgb[id] = packed_float3(mapped.x, mapped.y, mapped.z);
}
