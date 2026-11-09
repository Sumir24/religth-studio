// Relight Studio v3.0 — WebGPU Compute Shader
// Full RGB Linear Reconstruction with Detail Coupling (lambda) and Soft Shoulder Rolloff.

struct Uniforms {
    lambda: f32,           // Detail coupling parameter in [0, 1]
    shoulder_start: f32,   // Soft highlight rolloff threshold (e.g. 0.85)
    pad0: f32,
    pad1: f32,
};

@group(0) @binding(0) var<uniform> uniforms: Uniforms;
@group(0) @binding(1) var in_linear_rgb: texture_2d<f32>;
@group(0) @binding(2) var in_yb: texture_2d<f32>;
@group(0) @binding(3) var in_yd: texture_2d<f32>;
@group(0) @binding(4) var in_ratio_r: texture_2d<f32>;
@group(0) @binding(5) var out_rgb: texture_storage_2d<rgba8unorm, write>;

const LUMA_COEFFS = vec3<f32>(0.2126, 0.7152, 0.0722);

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let dims = textureDimensions(out_rgb);
    if (gid.x >= dims.x || gid.y >= dims.y) {
        return;
    }

    let coords = vec2<i32>(i32(gid.x), i32(gid.y));
    let rgb = textureLoad(in_linear_rgb, coords, 0);
    let y_b = textureLoad(in_yb, coords, 0).r;
    let y_d = textureLoad(in_yd, coords, 0).r;
    let r = textureLoad(in_ratio_r, coords, 0).r;

    // 1. Current Linear Luminance
    let y_orig = max(dot(rgb.rgb, LUMA_COEFFS), 1e-6);

    // 2. Detail Coupling with Lambda: Y' = Yb * R + Yd * (R^lambda)
    let r_clamped = max(r, 1e-4);
    let r_lambda = pow(r_clamped, uniforms.lambda);
    let y_prime = max(y_b * r + y_d * r_lambda, 0.0);

    // 3. Chromaticity Preservation
    var c_lin = rgb.rgb * (y_prime / y_orig);

    // 4. Soft Highlight Shoulder Rolloff
    let shoulder = uniforms.shoulder_start;
    var out_color = c_lin;
    if (out_color.r > shoulder) {
        let ex = out_color.r - shoulder;
        out_color.r = shoulder + (ex / (1.0 + ex)) * (1.0 - shoulder);
    }
    if (out_color.g > shoulder) {
        let ex = out_color.g - shoulder;
        out_color.g = shoulder + (ex / (1.0 + ex)) * (1.0 - shoulder);
    }
    if (out_color.b > shoulder) {
        let ex = out_color.b - shoulder;
        out_color.b = shoulder + (ex / (1.0 + ex)) * (1.0 - shoulder);
    }

    // 5. Transfer to sRGB for display output
    let srgb = select(
        out_color * 12.92,
        1.055 * pow(clamp(out_color, vec3<f32>(0.0), vec3<f32>(1.0)), vec3<f32>(1.0 / 2.4)) - 0.055,
        out_color > vec3<f32>(0.0031308)
    );

    textureStore(out_rgb, coords, vec4<f32>(clamp(srgb, vec3<f32>(0.0), vec3<f32>(1.0)), rgb.a));
}
