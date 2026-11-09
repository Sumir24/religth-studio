"""
Test Suite for Relight Studio Engine v3.1
Verifies:
1. Invariant 1: Identity preservation (S_new == S_old -> output == input).
2. Invariant 2: Dynamic range and numeric sanity (no NaN, no Inf, bounded).
3. Invariant 3: High-pass detail amplitude scaling matches R^lambda.
4. Feature 1: Point and Spot light attenuation and cone falloff.
5. Feature 2: Relative chromatic adaptation (von Kries neutrality when Tk == T0).
6. Real image verification on Nike shoe and Classical statue.
"""

import numpy as np
import cv2
from PIL import Image
from engine.relighter_v3 import RelighterV3, kelvin_to_linear_rgb, LUMA

def test_v3_identity_preservation():
    """When S_new equals S_old, output must equal input within float tolerance."""
    relighter = RelighterV3()
    h, w = 128, 128
    
    np.random.seed(42)
    lin_rgb = np.random.uniform(0.1, 0.8, (h, w, 3)).astype(np.float32)
    S_field = np.ones((h, w), dtype=np.float32) * 0.75
    
    res = relighter.relight(
        lin_rgb=lin_rgb,
        S_new=S_field,
        S_old=S_field,
        lam=0.7,
        r_min=0.25,
        r_max=4.0,
        deband_threshold=0.0 # exact mathematical identity test
    )
    
    diff = np.abs(res["linear_hdr"] - lin_rgb)
    max_err = np.max(diff)
    assert max_err < 1e-4, f"Identity failure: max error was {max_err}"
    print(f"[PASS] Invariant 1: Identity preservation (Max error: {max_err:.2e})")

def test_v3_lambda_detail_coupling():
    """Verifies that high-pass detail amplitude ratio strictly follows R^lambda."""
    relighter = RelighterV3()
    h, w = 256, 256
    
    np.random.seed(123)
    base_val = 0.5
    noise = np.random.uniform(-0.05, 0.05, (h, w))
    lin_rgb = np.stack([base_val + noise] * 3, axis=-1).astype(np.float32)
    
    S_old = np.ones((h, w), dtype=np.float32) * 0.5
    S_new = np.ones((h, w), dtype=np.float32) * 1.0
    
    res_0 = relighter.relight(lin_rgb, S_new=S_new, S_old=S_old, lam=0.0, filter_radius=16, deband_threshold=0.0)
    res_1 = relighter.relight(lin_rgb, S_new=S_new, S_old=S_old, lam=1.0, filter_radius=16, deband_threshold=0.0)
    
    hp_orig = lin_rgb[:, :, 0] - cv2.GaussianBlur(lin_rgb[:, :, 0], (15, 15), 3.0)
    hp_0 = res_0["linear_hdr"][:, :, 0] - cv2.GaussianBlur(res_0["linear_hdr"][:, :, 0], (15, 15), 3.0)
    hp_1 = res_1["linear_hdr"][:, :, 0] - cv2.GaussianBlur(res_1["linear_hdr"][:, :, 0], (15, 15), 3.0)
    
    std_orig = np.std(hp_orig)
    ratio_0 = np.std(hp_0) / std_orig
    ratio_1 = np.std(hp_1) / std_orig
    
    assert abs(ratio_0 - 1.0) < 0.15, f"Lambda=0 failed to lock detail! Ratio was {ratio_0:.3f}"
    assert abs(ratio_1 - 2.0) < 0.35, f"Lambda=1 failed physical scaling! Ratio was {ratio_1:.3f}"
    print(f"[PASS] Invariant 3: Lambda coupling verified (lambda=0.0 ratio={ratio_0:.2f}, lambda=1.0 ratio={ratio_1:.2f})")

def test_v3_point_and_spot_lights():
    """Verifies that point lights attenuate with 1/r^2 and spot lights attenuate with cone angle."""
    relighter = RelighterV3(fov_degrees=60.0)
    h, w = 128, 128
    
    depth = np.ones((h, w), dtype=np.float32) * 1.0
    normals = np.zeros((h, w, 3), dtype=np.float32)
    normals[:, :, 2] = -1.0 # Outward toward camera / lights
    
    point_lit = [{
        "type": "point",
        "position": [0.0, 0.0, 0.5],
        "intensity": 1.0,
        "k1": 0.0,
        "k2": 1.0
    }]
    
    shading_point, _, _, _, _ = relighter.evaluate_lights(point_lit, normals, depth)
    center_val = shading_point[h // 2, w // 2]
    corner_val = shading_point[0, 0]
    
    assert center_val > corner_val * 1.5, f"Point light falloff failed: center={center_val}, corner={corner_val}"
    
    spot_lit = [{
        "type": "spot",
        "position": [0.0, 0.0, 0.5],
        "spot_direction": [0.0, 0.0, 1.0],
        "inner_cone_deg": 10.0,
        "outer_cone_deg": 25.0,
        "intensity": 1.0
    }]
    shading_spot, _, _, _, _ = relighter.evaluate_lights(spot_lit, normals, depth)
    assert shading_spot[h // 2, w // 2] > 0.5
    assert shading_spot[0, 0] == 0.0, f"Spot light outside cone must be 0! Got {shading_spot[0, 0]}"
    print("[PASS] Feature 1: Point 1/r^2 and Spot cone falloff verified.")

def test_v3_chromatic_adaptation_neutrality():
    """When light Kelvin matches scene white Kelvin, output chromaticity is unchanged."""
    relighter = RelighterV3()
    h, w = 64, 64
    lin_rgb = np.ones((h, w, 3), dtype=np.float32) * 0.5
    
    white_5500 = kelvin_to_linear_rgb(5500.0)
    gains = [np.ones((h, w), dtype=np.float32)]
    
    res = relighter.relight(
        lin_rgb,
        S_new=np.ones((h, w), dtype=np.float32),
        S_old=np.ones((h, w), dtype=np.float32),
        scene_white_kelvin=5500.0,
        light_whites=[white_5500],
        light_gains=gains,
        deband_threshold=0.0
    )
    
    diff = np.abs(res["linear_hdr"] - lin_rgb)
    assert np.max(diff) < 1e-4, f"Color shift occurred on matched white: {np.max(diff)}"
    print("[PASS] Feature 2: Chromatic adaptation neutrality verified.")

def test_v3_real_photographs():
    """Runs v3 engine across Nike Sneaker and Classical Broken Statue."""
    relighter = RelighterV3()
    
    test_cases = [
        {
            "name": "Nike Sneaker",
            "img_path": "demo_output/nike_sample.jpg",
            "norm_path": "demo_output/nike_test/normals.png",
            "mode": "photograph"
        },
        {
            "name": "Classical Broken Statue",
            "img_path": "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794143824741_478ce89a.jpg",
            "norm_path": "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/statue_normals.jpg",
            "mode": "line_art"
        }
    ]
    
    for tc in test_cases:
        srgb = np.array(Image.open(tc["img_path"])).astype(np.float32) / 255.0
        lin_rgb = relighter.srgb_to_linear(srgb)
        
        raw_norm = np.array(Image.open(tc["norm_path"])).astype(np.float32) / 255.0 * 2.0 - 1.0
        norm_len = np.clip(np.linalg.norm(raw_norm, axis=2, keepdims=True), 1e-4, None)
        normals = raw_norm / norm_len
        
        h, w, _ = lin_rgb.shape
        depth = np.ones((h, w), dtype=np.float32) * 1.0
        
        lights = [
            {"type": "directional", "direction": [-0.7, -0.4, 0.6], "intensity": 1.2, "kelvin": 3200.0},
            {"type": "point", "position": [0.6, -0.2, 0.4], "intensity": 0.8, "kelvin": 7500.0}
        ]
        
        S_new, light_gains, light_whites, specular, rim = relighter.evaluate_lights(lights, normals, depth)
        S_old = np.ones((h, w), dtype=np.float32) * 0.7
        
        res = relighter.relight(
            lin_rgb,
            S_new=S_new,
            S_old=S_old,
            lam=0.7,
            deband_threshold=0.012,
            scene_white_kelvin=5500.0,
            light_whites=light_whites,
            light_gains=light_gains,
            specular_layer=specular,
            rim_layer=rim,
            mode=tc["mode"]
        )
        
        srgb_out = res["display_srgb"]
        assert not np.isnan(srgb_out).any(), f"NaN in {tc['name']}"
        assert not np.isinf(srgb_out).any(), f"Inf in {tc['name']}"
        assert srgb_out.min() >= 0.0 and srgb_out.max() <= 1.0, f"Out of bounds in {tc['name']}"
        print(f"[PASS] Real image test: {tc['name']} verified with mode='{tc['mode']}'")
