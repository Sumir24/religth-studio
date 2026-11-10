# RELIGHT STUDIO — RS-PRODUCT-1.2
## Camera Matching & Photographic Perspective Alignment Specification

**Author:** Principal 3D Graphics Engineer & Computational Photography Researcher  
**Milestone:** RS-PRODUCT-1.2  
**Status:** VALIDATED & ACCEPTED  

---

## 1. Executive Overview

Accurate camera matching is the foundation of photographic relighting. In traditional 3D software, users are forced to guess camera matrices, field-of-view angles, or arbitrary focal lengths, leading to distorted perspective, mismatched shadow casting, and synthetic lighting misalignment.

RS-PRODUCT-1.2 establishes a mathematically coupled, photographic camera model referenced to a 35mm full-frame film aperture ($36.0 \times 24.0\,\text{mm}$ standard format), providing instant 1-click lens presets, auto-framing ("Fit to Subject"), and real-time photographic projection overlays.

---

## 2. Mathematical Formulation & Lens Coupling

### 2.1 Full-Frame 35mm Equivalence
In computational photography and cinematography, focal length $f$ and vertical field-of-view $\theta$ are coupled via the vertical sensor dimension $h = 24.0\,\text{mm}$:

$$\tan\left(\frac{\theta}{2}\right) = \frac{h / 2}{f} = \frac{12.0}{f}$$

Rearranging gives the exact, closed-form bidirectional conversion functions:

$$f(\theta) = \frac{12.0}{\tan(\theta / 2)}$$

$$\theta(f) = 2 \cdot \arctan\left(\frac{12.0}{f}\right) \cdot \frac{180^\circ}{\pi}$$

### 2.2 Standard 35mm Lens Presets
To guarantee photographic consistency and eliminate guessing, Relight Studio exposes 5 verified industry-standard lens presets:

| Lens Preset | Equivalent Focal Length $f$ | Vertical FOV $\theta$ | Photographic Use Case |
|---|---|---|---|
| **24mm Wide** | $24.0\,\text{mm}$ | $53.1301^\circ$ | Environmental / Architecture / Interior scenes |
| **35mm Wide-Normal** | $35.0\,\text{mm}$ | $37.8493^\circ$ | Street photography / Environmental product context |
| **50mm Normal** | $50.0\,\text{mm}$ | $26.9915^\circ$ | Standard human vision / Neutral commercial product |
| **85mm Portrait** | $85.0\,\text{mm}$ | $16.1021^\circ$ | Editorial portraiture / Compressed commercial catalog |
| **105mm Telephoto** | $105.0\,\text{mm}$ | $13.0645^\circ$ | Macro photography / High-compression product studio |

Both `studio3a/camera.py` and `studio3a/scene.py` maintain 4-decimal precision, ensuring that round-trip conversions ($f \to \theta \to f$) incur zero rounding drift:

$$\Delta f_{\text{roundtrip}} < 0.001\,\text{mm}$$

---

## 3. Auto-Framing: "Fit Camera to Subject"

When adjusting lens focal lengths (e.g., from 24mm wide-angle to 85mm portrait telephoto), the subject size changes dramatically. Artists need to frame the subject without manually dragging camera translation along $Z$ and risking disorientation.

### 3.1 Framing Formulation
Relight Studio implements closed-form subject auto-framing:
1. The subject proxy's 3D bounding extents are evaluated: $r_{\text{max}} = \max(e_x, e_y, e_z)$ where $\mathbf{e} = 0.5 \cdot (\text{dimensions} \times \text{scale})$.
2. The required framing distance $d$ to fit the subject within $65\%$ of the camera frame height is:

$$d = \frac{r_{\text{max}}}{0.65 \cdot \tan(\theta / 2)}$$

3. The camera target $\mathbf{t}$ is locked to the subject center: $\mathbf{t} = \mathbf{pos}_{\text{subject}}$.
4. The camera position $\mathbf{c}$ is shifted along the camera viewing direction vector $\mathbf{v}_{\text{dir}} = \frac{\mathbf{c} - \mathbf{t}}{\|\mathbf{c} - \mathbf{t}\|}$:

$$\mathbf{c}_{\text{new}} = \mathbf{t} + d \cdot \mathbf{v}_{\text{dir}}$$

This preserves camera angle and pitch while instantly re-framing the subject proxy to optimal working scale.

---

## 4. Image-Space Alignment Overlays

The virtual camera matrix projects 3D scene elements directly into the Photograph Viewport 2D coordinate system:

$$\mathbf{x}_{\text{screen}} = \begin{bmatrix} \frac{x_{\text{ndc}} + 1}{2} \cdot W \\ \frac{1 - y_{\text{ndc}}}{2} \cdot H \end{bmatrix}$$

### 4.1 Overlay Modes
1. **Wireframe Overlay (`mode="wireframe"`):** Projects the 8 corner vertices and 12 connecting edges of the 3D proxy bounding box directly onto the photograph.
2. **Silhouette Blend (`mode="silhouette"`):** Evaluates the 2D convex hull of the projected proxy vertices and blends a semi-transparent cyan mask with artist-adjustable opacity $\alpha \in [0, 1]$.
3. **Alignment Guides (`mode="guides"`):**
   - **Horizon Line:** Computed by projecting two infinite ground-plane points at distance $10,000\,\text{m}$ in camera horizontal space, providing an exact perspective vanishing horizon.
   - **Ground Perspective Grid:** Projects longitudinal and latitudinal lines on the floor plane $y = \text{ground\_y}$.
   - **Contact Marker:** Projects the ground contact point $\mathbf{p}_{\text{contact}} = [x_{\text{subj}}, \text{ground\_y}, z_{\text{subj}}]$.
4. **Mismatch Diagnostic Heatmap (`mode="mismatch"`):** Rasterizes the projected silhouette polygon against the photograph foreground mask $\mathbf{M}_{\text{fg}}$, rendering a color-coded IoU difference map.

---

## 5. Visual Evidence & Screenshots

All modes were captured live using headless Google Chrome on Apple Silicon:

- **24mm Wide Preset:** `docs/RS-PRODUCT-1.2/screenshots/02_camera_preset_24mm_wide.png`
- **50mm Normal Preset:** `docs/RS-PRODUCT-1.2/screenshots/03_camera_preset_50mm_normal.png`
- **85mm Portrait Preset:** `docs/RS-PRODUCT-1.2/screenshots/04_camera_preset_85mm_portrait.png`
- **Fit Camera to Subject:** `docs/RS-PRODUCT-1.2/screenshots/05_camera_framing_fit_to_subject.png`
- **Wireframe Overlay:** `docs/RS-PRODUCT-1.2/screenshots/06_photograph_wireframe_overlay.png`
- **Silhouette Blend:** `docs/RS-PRODUCT-1.2/screenshots/07_photograph_silhouette_blend.png`
- **Horizon & Guides:** `docs/RS-PRODUCT-1.2/screenshots/08_photograph_guides_horizon_ground.png`
- **Mismatch Heatmap:** `docs/RS-PRODUCT-1.2/screenshots/09_photograph_mismatch_diagnostic.png`
