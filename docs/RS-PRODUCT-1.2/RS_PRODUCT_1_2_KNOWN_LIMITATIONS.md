# RELIGHT STUDIO — RS-PRODUCT-1.2
## Known Limitations, Technical Debt & Unresolved Risks

**Author:** Principal 3D Graphics Engineer & Independent QA Lead  
**Milestone:** RS-PRODUCT-1.2  
**Status:** RECORDED FOR AUDIT  

---

## 1. Geometric Approximation Limitations

### 1.1 Single Parametric Convex Proxies
Current proxies (Sphere, OBB, Superquadric) are mathematically convex surfaces. Real-world photographic subjects (e.g., athletic sneakers with hollow collars and sculpted soles, classical sculptures with separated limbs and flowing drapery) exhibit complex concave topology.
- **Impact:** Maximum achievable IoU for non-convex subjects tops out around 0.55–0.65.
- **Mitigation:** The Mismatch Heatmap (`mode="mismatch"`) transparently illustrates the geometric discrepancy in Red (under-coverage) and Blue (over-coverage) rather than presenting a falsified high confidence.
- **Future Direction (RS-PRODUCT-1.3+):** Support for multi-part proxy hierarchies (compound bounding boxes) or artist-imported low-poly OBJ proxy meshes.

---

## 2. Lens Distortion & Non-Planar Optical Effects

### 2.1 Ideal Pinhole Camera Assumption
The current camera model assumes a rectilinear, zero-distortion pinhole perspective:

$$\mathbf{x}_{\text{ndc}} = \frac{f}{z} \mathbf{x}_{\text{eye}}$$

- **Limitation:** Real camera lenses (particularly wide-angle lenses below 28mm) exhibit barrel or pincushion distortion, optical vignetting, and chromatic aberration.
- **Impact:** Perfectly straight 3D wireframe edges projected onto an uncorrected ultra-wide photograph may show slight divergence towards the image corners.
- **Future Direction:** Implement Brown-Conrady radial and tangential lens distortion coefficients $(k_1, k_2, p_1, p_2)$ in the photographic projection pipeline.

---

## 3. Application Architecture: Web vs Native macOS

### 3.1 Architectural Reality
The current Relight Studio implementation runs as a high-performance local Python backend (`uvicorn` + `FastAPI`) driving native Apple Silicon Metal 3 GPU kernels via PyObjC/C++ bridge, connected to a HTML5/Canvas frontend.
- **Strengths:** Rapid UI iteration, zero-compilation CSS styling, native Metal 3 GPU compute speed (>100 FPS), headless testability via Chrome.
- **Limitations:** Browser-imposed color management (sRGB canvas clamp), lack of native macOS window menus and native AppKit/SwiftUI drag gestures.
- **Recommendation:** Keep current web-over-Metal architecture for product validation through RS-PRODUCT-1.3; migrate frontend to SwiftUI / MetalKit viewport when preparing for Mac App Store distribution.

---

## 4. Unresolved Risks & Mitigations

| Risk | Severity | Mitigation in RS-PRODUCT-1.2 |
|---|---|---|
| Near-parallel drag singularity | Low | Implemented $L < 4\,\text{px}$ screen-space fallback preventing jumps |
| Missing project assets | Medium | Explicit warning pill in UI and `is_missing_assets` flag, zero silent substitution |
| Source photo accidental overwrite | Critical | Enforced SHA-256 pre/post integrity assertions; project bundles store isolated copies |
| Memory exhaustion from undo stack | Low | Bounded `SceneStateManager` stack depth to 50 snapshots |
