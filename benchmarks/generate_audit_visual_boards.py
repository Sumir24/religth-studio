"""
RELIGHT STUDIO — RS-SPIKE-3B.1: VISUAL EVIDENCE AUDIT GENERATOR
===============================================================
Generates comprehensive visual contact sheets for independent inspection:
  - Original Image
  - Relit Output (Metal GPU, FINAL 64 samples)
  - Amplified Difference Map (5x absolute delta in sRGB)
  - Direct Visibility / Shadow Field
  - Subject Proxy & Receiver Wireframe Overlay
Saves images to docs/RS-SPIKE-3B.1/visual_boards/
"""

import os
import cv2
import numpy as np
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, ProxyType, ReceiverType, RenderQuality
)
from studio3a.camera import Camera3D
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture
from benchmarks.validate_photographic_fidelity import load_photographic_case

OUTPUT_DIR = "docs/RS-SPIKE-3B.1/visual_boards"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_contact_sheet(
    title: str,
    orig_srgb: np.ndarray,
    relit_srgb: np.ndarray,
    vis_field: np.ndarray,
    proxy_overlay: np.ndarray,
    out_path: str
):
    H, W = orig_srgb.shape[:2]
    
    # 1. Diff map (5x amplified absolute difference)
    diff = np.abs(relit_srgb - orig_srgb) * 5.0
    diff = np.clip(diff, 0.0, 1.0)
    
    # 2. Visibility heatmap (sRGB representation of scalar visibility)
    vis_u8 = (np.clip(vis_field, 0.0, 1.0) * 255.0).astype(np.uint8)
    vis_color = cv2.applyColorMap(vis_u8, cv2.COLORMAP_VIRIDIS)
    vis_color_rgb = cv2.cvtColor(vis_color, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    
    # Convert all panels to uint8 BGR for OpenCV canvas
    p1 = cv2.cvtColor((np.clip(orig_srgb, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLOR_RGB2BGR)
    p2 = cv2.cvtColor((np.clip(relit_srgb, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLOR_RGB2BGR)
    p3 = cv2.cvtColor((np.clip(diff, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLOR_RGB2BGR)
    p4 = cv2.cvtColor((np.clip(vis_color_rgb, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLOR_RGB2BGR)
    p5 = cv2.cvtColor((np.clip(proxy_overlay, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLOR_RGB2BGR)
    
    # Add title headers to each panel
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.5, W / 1200.0)
    thick = max(1, int(W / 600.0))
    
    def annotate(img, text):
        out = img.copy()
        cv2.rectangle(out, (0, 0), (W, int(H * 0.08)), (20, 20, 20), -1)
        cv2.putText(out, text, (15, int(H * 0.06)), font, font_scale, (255, 255, 255), thick, cv2.LINE_AA)
        return out
        
    p1 = annotate(p1, "1. ORIGINAL PLATE")
    p2 = annotate(p2, "2. RELIT (METAL GPU)")
    p3 = annotate(p3, "3. DIFF MAP (5x AMPLIFIED)")
    p4 = annotate(p4, "4. SHADOW VISIBILITY")
    p5 = annotate(p5, "5. PROXY ALIGNMENT")
    
    # Stack panels horizontally
    top_row = np.hstack([p1, p2, p3])
    # For bottom row, pad p4 and p5 to match width of 3 panels
    pad_w = top_row.shape[1] - (p4.shape[1] + p5.shape[1])
    blank = np.zeros((H, pad_w, 3), dtype=np.uint8)
    # Add info banner on the blank panel
    cv2.putText(blank, "RELIGHT STUDIO AUDIT", (20, int(H * 0.35)), font, font_scale * 1.1, (100, 200, 255), thick + 1, cv2.LINE_AA)
    cv2.putText(blank, title, (20, int(H * 0.50)), font, font_scale * 0.9, (220, 220, 220), thick, cv2.LINE_AA)
    cv2.putText(blank, "Quality: FINAL (64 samples)", (20, int(H * 0.65)), font, font_scale * 0.8, (180, 180, 180), thick, cv2.LINE_AA)
    
    bot_row = np.hstack([p4, p5, blank])
    sheet = np.vstack([top_row, bot_row])
    
    cv2.imwrite(out_path, sheet)
    print(f"  [SAVED] {out_path} ({sheet.shape[1]}x{sheet.shape[0]} px)")


def generate_all_visual_boards():
    print("=" * 80)
    print("RS-SPIKE-3B.1: GENERATING VISUAL AUDIT CONTACT SHEETS")
    print("=" * 80)
    
    metal_b = MetalRenderBackend()
    
    # 1. Photographic Plates P1, P2, P3
    photo_cases = ["P1_nike_sneaker", "P2_classical_statue", "P3_architectural_relief"]
    for pid in photo_cases:
        print(f"\nProcessing Photographic Plate: {pid}...")
        cid, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case(pid)
        res = metal_b.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL)
        
        # Wireframe overlay from renderer
        overlay = res["proxy_overlay"] / 255.0 if res["proxy_overlay"].max() > 1.0 else res["proxy_overlay"]
        
        out_file = os.path.join(OUTPUT_DIR, f"{pid}_audit_board.png")
        build_contact_sheet(
            title=f"Photographic Plate: {pid}",
            orig_srgb=img_srgb,
            relit_srgb=res["relit_srgb"],
            vis_field=res["direct_visibility"],
            proxy_overlay=overlay,
            out_path=out_file
        )
        
    # 2. Canonical Synthetic Cases: M2_03 (Cosmetic Bottle on Cyclorama) & M2_04 (Footwear Mesh on Plane)
    canon_cases = [
        ("M2_03_cosmetic_bottle_cyclorama", "cat2_cosmetic_bottle", ProxyType.SUPERQUADRIC, ReceiverType.CYCLORAMA, "Cosmetic Bottle on Cyclorama Cove"),
        ("M2_04_sneaker_mesh_plane", "cat3_sneaker", ProxyType.MESH, ReceiverType.PLANE, "Footwear Hull Mesh (280 Triangles)")
    ]
    
    for case_id, cat_id, p_type, r_type, desc in canon_cases:
        print(f"\nProcessing Canonical Case: {case_id}...")
        scene, img, depth, normals, fg, rec, _ = generate_scene_fixture(cat_id, p_type, r_type, H=576, W=768)
        scene.render_settings.final_samples = 64
        res = metal_b.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)
        
        overlay = res["proxy_overlay"] / 255.0 if res["proxy_overlay"].max() > 1.0 else res["proxy_overlay"]
        out_file = os.path.join(OUTPUT_DIR, f"{case_id}_audit_board.png")
        build_contact_sheet(
            title=f"Canonical: {desc}",
            orig_srgb=img,
            relit_srgb=res["relit_srgb"],
            vis_field=res["direct_visibility"],
            proxy_overlay=overlay,
            out_path=out_file
        )
        
    print("\nVisual audit contact sheets successfully generated.")


if __name__ == "__main__":
    generate_all_visual_boards()
