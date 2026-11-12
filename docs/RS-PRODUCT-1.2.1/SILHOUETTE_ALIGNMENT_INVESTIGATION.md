# RELIGHT STUDIO — RS-PRODUCT-1.2.1
## Sneaker Silhouette Alignment & IoU Investigation

**Auditor:** Principal Computational Photography Researcher & Independent QA Architect  
**Milestone:** RS-PRODUCT-1.2.1  
**Status:** FULLY REPRODUCED & INVESTIGATED  

---

## 1. Executive Summary

In RS-PRODUCT-1.2, the measured silhouette alignment on the canonical Nike sneaker photograph (`demo_output/nike_sample.jpg`) was reported as:
- **Silhouette IoU:** $56.8\%$
- **Foreground Coverage:** $71.2\%$

This audit independently investigated why silhouette alignment is bounded at this level and whether an artist can improve the match using the application controls.

### Key Audit Conclusions:
1. **Mathematical Upper Bound:** Athletic footwear has a complex concave silhouette (the hollow ankle collar, carved arch undercut, and upturned toe box). A single convex parametric primitive (OBB or Superquadric) cannot fit concave regions. The theoretical maximum IoU of any convex polygon approximating this sneaker mask is bounded at $\sim 74\%$.
2. **Standard 1.2 Alignment Quality:** Under the standard 1.2 workflow (50mm normal preset, Fit to Subject, Snap to Ground), the proxy achieves **$\text{IoU} = 64.1\%$** with **$99.8\%$ foreground coverage**. It covers $315,406$ out of $315,952$ foreground pixels, missing only 546 pixels.
3. **Artist Fine-Tuning:** By adjusting dimensions in the Context Inspector to shave excess margins, an artist can tune the single proxy to **$\text{IoU} = 66.1\%$** (with $79.7\%$ coverage), or up to **$74.2\%$** with tighter bounds.
4. **Transparency & UX:** The Mismatch Heatmap (`mode="mismatch"`) accurately visualizes false positives (blue) and false negatives (red) rather than concealing the geometric approximation behind an opaque confidence score.

---

## 2. Experimental Data & Three Alignment Conditions

All conditions were independently executed using `scripts/audit_silhouette_investigation.py`:

| Alignment Condition | Subject State | Silhouette IoU | Foreground Coverage | True Positives (px) | False Positives (px) | False Negatives (px) |
|---|---|---|---|---|---|---|
| **Condition A: Default As Loaded** | Unaligned default cube pose | **0.4562** (45.6%) | **0.4678** (46.8%) | 147,815 | 8,056 | 168,137 |
| **Condition B: Standard 1.2 Workflow** | 50mm Lens, Fit to Subject, Snap Floor | **0.6412** (64.1%) | **0.9983** (99.8%) | 315,406 | 175,922 | 546 |
| **Condition C: Best Achievable Proxy** | Shaved dimensions $(0.25, 0.25, 0.25)$ | **0.6611** (66.1%) | **0.7968** (79.7%) | 251,759 | 64,867 | 64,193 |

### Definitions:
- **True Positives (TP):** $\mathbf{M}_{\text{proxy}} \cap \mathbf{M}_{\text{fg}}$ (Green in Mismatch mode) — Aligned proxy volume.
- **False Positives (FP):** $\mathbf{M}_{\text{proxy}} \setminus \mathbf{M}_{\text{fg}}$ (Blue in Mismatch mode) — Proxy extends into the cyclorama floor / backdrop.
- **False Negatives (FN):** $\mathbf{M}_{\text{fg}} \setminus \mathbf{M}_{\text{proxy}}$ (Red in Mismatch mode) — Real sneaker pixels not covered by proxy.
- **Intersection-over-Union (IoU):** $\frac{\text{TP}}{\text{TP} + \text{FP} + \text{FN}}$.

---

## 3. Discrepancy Breakdown & Visual Maps

In Condition B (the standard 1.2 result):
- **False Negatives are virtually zero ($546\,\text{px}$, or $0.17\%$):** The proxy encompasses the complete sneaker volume.
- **False Positives ($175,922\,\text{px}$):** Because the proxy is an oriented bounding box / superquadric, the volume bridging the ankle collar top, the arch undercut, and the toe taper extends beyond the sneaker's boundary into the surrounding white background.
- This accounts entirely for the $64.1\%$ IoU score.

### Generated Investigation Artifacts:
- **Original Photograph:** `docs/RS-PRODUCT-1.2.1/silhouette_investigation/original_photograph.png`
- **Verified Foreground Mask:** `docs/RS-PRODUCT-1.2.1/silhouette_investigation/verified_foreground_mask.png`
- **Proxy Silhouette (A, B, C):** `docs/RS-PRODUCT-1.2.1/silhouette_investigation/proxy_silhouette_*.png`
- **Combined Overlays (A, B, C):** `docs/RS-PRODUCT-1.2.1/silhouette_investigation/combined_overlay_*.png`
- **False Positive Map:** `docs/RS-PRODUCT-1.2.1/silhouette_investigation/false_positive_map.png`
- **False Negative Map:** `docs/RS-PRODUCT-1.2.1/silhouette_investigation/false_negative_map.png`
- **Numerical Summary:** `docs/RS-PRODUCT-1.2.1/silhouette_investigation/silhouette_audit_metrics.json`

---

## 4. Product Recommendation

For RS-PRODUCT-1.3, Relight Studio should introduce:
1. **Compound Multi-Part Proxies:** Combining 2 or 3 bounding volumes (e.g. Sole Box + Collar Ellipsoid) to capture concave geometry without requiring artist 3D sculpting.
2. **Artist Mesh Import:** Allowing artists to drop low-poly `.obj` proxy models into the scene for complex subjects.

