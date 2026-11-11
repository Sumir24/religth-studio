"""
RELIGHT STUDIO — RS-PRODUCT-1.2.1
==================================
Sneaker Silhouette Investigation Script
Generates independent verification assets for Audit C:
- Original photograph
- Verified foreground mask
- Proxy silhouette (Conditions A, B, C)
- Combined overlays
- False-positive and false-negative difference maps
- Exact quantitative calculations (IoU, Coverage, Bbox Delta)
"""

import os
import json
import numpy as np
import cv2
from pathlib import Path
from relight_studio.controller import StudioAppController

OUT_DIR = Path("docs/RS-PRODUCT-1.2.1/silhouette_investigation")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_investigation():
    print("=" * 80)
    print("RELIGHT STUDIO — RS-PRODUCT-1.2.1 SNEAKER SILHOUETTE INVESTIGATION")
    print("=" * 80)

    sample_img = "demo_output/nike_sample.jpg"
    ctrl = StudioAppController(sample_image_path=sample_img, use_metal=True)

    H, W = ctrl.project.fg_mask.shape
    fg_mask = ctrl.project.fg_mask
    photo_bgr = cv2.cvtColor((ctrl.project.img_orig_srgb * 255.0).astype(np.uint8), cv2.COLOR_RGB2BGR)

    # 1. Save Original Photograph & Verified Mask
    cv2.imwrite(str(OUT_DIR / "original_photograph.png"), photo_bgr)
    mask_u8 = (fg_mask.astype(np.uint8) * 255)
    cv2.imwrite(str(OUT_DIR / "verified_foreground_mask.png"), mask_u8)

    # Helper function to get rasterized silhouette and metrics
    def evaluate_state():
        meta = ctrl.get_alignment_projection_meta(canvas_w=W, canvas_h=H)
        poly = meta.get("silhouette_polygon", [])
        poly_mask = np.zeros((H, W), dtype=np.uint8)
        if len(poly) >= 3:
            pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(poly_mask, [pts], 255)
        poly_bool = poly_mask > 0

        tp = np.logical_and(poly_bool, fg_mask)
        fp = np.logical_and(poly_bool, ~fg_mask)
        fn = np.logical_and(~poly_bool, fg_mask)

        iou = float(tp.sum()) / float(max(np.logical_or(poly_bool, fg_mask).sum(), 1))
        coverage = float(tp.sum()) / float(max(fg_mask.sum(), 1))

        # Bounding box delta
        y_fg, x_fg = np.where(fg_mask)
        bbox_fg = [int(np.min(x_fg)), int(np.min(y_fg)), int(np.max(x_fg)), int(np.max(y_fg))]

        if np.any(poly_bool):
            y_pr, x_pr = np.where(poly_bool)
            bbox_pr = [int(np.min(x_pr)), int(np.min(y_pr)), int(np.max(x_pr)), int(np.max(y_pr))]
        else:
            bbox_pr = [0, 0, 0, 0]

        bbox_delta = [bbox_pr[i] - bbox_fg[i] for i in range(4)]

        # Combined visualization
        vis = photo_bgr.copy()
        # Green for TP, Blue for FP, Red for FN
        heatmap = np.zeros_like(photo_bgr)
        heatmap[tp] = [0, 255, 0]    # Green
        heatmap[fp] = [255, 0, 0]    # Blue
        heatmap[fn] = [0, 0, 255]    # Red
        blend = cv2.addWeighted(vis, 0.5, heatmap, 0.5, 0)

        return {
            "iou": round(iou, 4),
            "coverage": round(coverage, 4),
            "bbox_fg": bbox_fg,
            "bbox_pr": bbox_pr,
            "bbox_delta_px": bbox_delta,
            "tp_pixels": int(tp.sum()),
            "fp_pixels": int(fp.sum()),
            "fn_pixels": int(fn.sum()),
            "poly_mask": poly_mask,
            "tp_mask": (tp.astype(np.uint8) * 255),
            "fp_mask": (fp.astype(np.uint8) * 255),
            "fn_mask": (fn.astype(np.uint8) * 255),
            "blend_vis": blend
        }

    # Condition A: Initial default alignment
    res_A = evaluate_state()
    cv2.imwrite(str(OUT_DIR / "proxy_silhouette_A.png"), res_A["poly_mask"])
    cv2.imwrite(str(OUT_DIR / "combined_overlay_A.png"), res_A["blend_vis"])

    # Condition B: Standard artist workflow (50mm lens preset, fit to subject, snap to ground)
    ctrl.apply_camera_preset("50mm")
    ctrl.fit_camera_to_subject()
    ctrl.snap_subject_to_ground()
    res_B = evaluate_state()
    cv2.imwrite(str(OUT_DIR / "proxy_silhouette_B.png"), res_B["poly_mask"])
    cv2.imwrite(str(OUT_DIR / "combined_overlay_B.png"), res_B["blend_vis"])
    cv2.imwrite(str(OUT_DIR / "false_positive_map.png"), res_B["fp_mask"])
    cv2.imwrite(str(OUT_DIR / "false_negative_map.png"), res_B["fn_mask"])

    # Condition C: Best achievable single proxy alignment
    # Shave width and height slightly to reduce false positive margin
    ctrl.current_scene.subject.dimensions = [0.25, 0.25, 0.25]
    ctrl.snap_subject_to_ground()
    res_C = evaluate_state()
    cv2.imwrite(str(OUT_DIR / "proxy_silhouette_C.png"), res_C["poly_mask"])
    cv2.imwrite(str(OUT_DIR / "combined_overlay_C.png"), res_C["blend_vis"])

    metrics = {
        "condition_A_default": {
            "iou": res_A["iou"],
            "coverage": res_A["coverage"],
            "bbox_delta_px": res_A["bbox_delta_px"],
            "tp_pixels": res_A["tp_pixels"],
            "fp_pixels": res_A["fp_pixels"],
            "fn_pixels": res_A["fn_pixels"]
        },
        "condition_B_standard_workflow": {
            "iou": res_B["iou"],
            "coverage": res_B["coverage"],
            "bbox_delta_px": res_B["bbox_delta_px"],
            "tp_pixels": res_B["tp_pixels"],
            "fp_pixels": res_B["fp_pixels"],
            "fn_pixels": res_B["fn_pixels"]
        },
        "condition_C_best_achievable": {
            "iou": res_C["iou"],
            "coverage": res_C["coverage"],
            "bbox_delta_px": res_C["bbox_delta_px"],
            "tp_pixels": res_C["tp_pixels"],
            "fp_pixels": res_C["fp_pixels"],
            "fn_pixels": res_C["fn_pixels"]
        }
    }

    with open(OUT_DIR / "silhouette_audit_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print("Condition A (Default):", metrics["condition_A_default"])
    print("Condition B (Standard 1.2):", metrics["condition_B_standard_workflow"])
    print("Condition C (Best Achievable):", metrics["condition_C_best_achievable"])
    print("\nAssets saved to:", OUT_DIR)


if __name__ == "__main__":
    run_investigation()

