# RELIGHT STUDIO — RS-PRODUCT-1.2
## Receiver & Ground-Contact Alignment Specification

**Author:** Principal 3D Graphics Engineer & PBR Rendering Specialist  
**Milestone:** RS-PRODUCT-1.2  
**Status:** VALIDATED & ACCEPTED  

---

## 1. Executive Overview

In photographic studio lighting, the background receiver (whether a flat floor, an infinite backdrop, or a curved studio cyclorama) governs contact shadows, ambient occlusion, and floor reflections. Mismatched receiver elevation causes objects to appear floating or submerged beneath the floor.

RS-PRODUCT-1.2 provides comprehensive receiver controls and visual guides:
1. **Receiver Types:** Infinite Ground Plane and Curved Studio Cyclorama (Seamless Cove).
2. **Ground Elevation Control:** Sub-millimeter height alignment ($y_{\text{ground}} \in [-2.0, 2.0]\,\text{m}$).
3. **Cyclorama Transition Alignment:** Smooth fillet curve defined by cove fillet radius $r_{\text{cove}}$ and back wall distance $z_{\text{wall}}$.
4. **Visual Guides:** Ground perspective grid, cyclorama cove transition boundary, and ground contact patch projected directly onto the photograph.

---

## 2. Cyclorama & Floor Mathematics

### 2.1 Cyclorama Surface Profile
A seamless studio cyclorama consists of three continuous geometric sections along the $Z$ (depth) axis:
1. **Horizontal Floor:** $z \in (-\infty, z_{\text{cove\_start}}]$, where $y = y_{\text{ground}}$.
2. **Curved Cove Fillet:** $z \in (z_{\text{cove\_start}}, z_{\text{wall}}]$, where the surface follows a circular arc of radius $R$:

$$(z - z_{\text{center}})^2 + (y - y_{\text{center}})^2 = R^2$$

with center coordinates $z_{\text{center}} = z_{\text{wall}} - R$ and $y_{\text{center}} = y_{\text{ground}} + R$.
3. **Vertical Back Wall:** $z = z_{\text{wall}}$, extending vertically $y \in [y_{\text{center}}, +\infty)$.

### 2.2 Image-Space Cove Transition Line
To visually guide the artist in positioning the studio backdrop, Relight Studio computes the 3D boundary line where the floor meets the cyclorama cove:

$$\mathbf{p}_1 = [-2.0, y_{\text{ground}}, z_{\text{wall}} - R], \quad \mathbf{p}_2 = [2.0, y_{\text{ground}}, z_{\text{wall}} - R]$$

Projecting $\mathbf{p}_1$ and $\mathbf{p}_2$ via the camera view-projection matrix yields the exact screen-space cyclorama transition guide:

$$\mathbf{p}_{1,\text{screen}} = \text{project}(\mathbf{p}_1), \quad \mathbf{p}_{2,\text{screen}} = \text{project}(\mathbf{p}_2)$$

Displayed as a dashed cyan guide in the Photograph Viewport (`mode="guides"`), allowing artists to verify that the virtual cyclorama inflection matches the physical photo's backdrop bend.

---

## 3. Ground Contact Shadow Transport

Contact shadow fidelity is enforced by geometry-aware ray-plane and ray-cove intersection in the Metal rendering kernel (`render_pipeline.metal`):
- When virtual lights illuminate the scene, the shadow ray originating from receiver sample $\mathbf{x}_{\text{rec}}$ towards light point $\mathbf{x}_{\text{light}}$ is tested against the subject proxy geometry.
- If $y_{\min} == y_{\text{ground}}$, the distance between the proxy contact patch and the receiver approaches zero, generating intense, sharp ambient occlusion and contact penumbrae as governed by physical light transport.
- Moving the subject vertically immediately scales the contact shadow softness and intensity in accordance with the inverse square law and solid angle subtended by the proxy.

---

## 4. Visual Evidence & Screenshots

- **Guides Overlay with Horizon & Cyclorama Line:** `docs/RS-PRODUCT-1.2/screenshots/08_photograph_guides_horizon_ground.png`
- **Snap to Ground Contact Badge in Inspector:** `docs/RS-PRODUCT-1.2/screenshots/11_subject_snap_to_ground_contact.png`
- **Receiver Lighting Response:** `docs/RS-PRODUCT-1.2/lighting_scenarios/scenario_1_render_after_right_key.png`
