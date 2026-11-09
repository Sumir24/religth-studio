# RELIGHT STUDIO — MASTER ARCHITECTURAL BLUEPRINT v5.0
## Photometric De-Lighting, Micro-Relief Texture Shading, Energy-Conserving PBR & Subsurface Transport

**Engine Version:** 5.0-MASTER  
**Predecessors:** v4.0 (Polar Coordinates & GGX), v3.2 (Production Guided Filter)  
**Workspace:** `/Users/sumirdayal/religth studio`  
**Target Runtime:** High-Precision Python / NumPy Vectorized & GPU Compute Ready  
**Status:** Architecture Approved & Ready for Implementation  

---

## 1. THE 5 CORE SHORTCOMINGS OF v4 & THEIR v5 RESOLUTIONS

```
┌────┬──────────────────────────────────┬───────────────────────────────────────────────────────────────────┐
│ #  │ Engine v4 Limitation             │ Engine v5 Mathematical Resolution                                 │
├────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 1  │ Static Assumption of S_old       │ Automatic Photometric Inverse Estimator solves L_orig from        │
│    │ Baked shadows in original photo  │ image gradients and normals, unbaking original lighting.          │
│    │ fight new light directions.      │                                                                   │
├────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 2  │ Micro-Detail Angle Invariance    │ Incident Angle-Aware Micro-Relief Shading: micro-texture contrast │
│    │ Y_d scaled only by R^lam; looks  │ sharpens at grazing angles (raking light) and flattens under      │
│    │ flat under raking light.         │ frontal fill, mimicking true 3D micro-shadowing.                  │
├────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 3  │ Uniform Material Properties      │ Spatially-Varying Material Inference: automatically maps local    │
│    │ Single gloss/roughness applied   │ roughness alpha(x,y) from high-frequency detail variance, and     │
│    │ to all pixels across the mask.   │ derives specular F_0 from chroma saturation.                      │
├────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 4  │ Flat Ambient / No Crevice Depth  │ Screen-Space Horizon Ambient Occlusion (HBAO): deep crevices,     │
│    │ Sole grooves and facial folds    │ outsole treads, and hollows darken naturally even under soft fill.│
│    │ look washed out under ambient.   │                                                                   │
├────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 5  │ Chalky Terminator Boundaries     │ Chromatic Subsurface Scattering (SSS): bleeds spectral warm       │
│    │ Harsh gray transitions on stone, │ diffusion across the N.L ~ 0 terminator, eliminating artificial   │
│    │ marble, skin, and soft plastics. │ diffuse sharpness on translucent materials.                       │
└────┴──────────────────────────────────┴───────────────────────────────────────────────────────────────────┘
```

---

## 2. MATHEMATICAL FORMULATION

### 2.1 Scene-Referred Working Pipeline
$$\text{sRGB} \xrightarrow{\text{EOTF}} \mathbf{C}_{\text{lin}} \in [0, \infty)^3 \xrightarrow{\text{Rec.709}} Y \in (0, \infty) \xrightarrow{\ln} \log Y$$

### 2.2 Base/Detail Decomposition with Analytical Debanding
$$\text{guide} = \text{EOTF}^{-1}(Y)$$
$$B = \text{GuidedFilter}(\text{guide}, \log Y, r_{\text{base}}, \varepsilon_{\text{base}}), \quad D_{\text{raw}} = \log Y - B$$
$$t = \text{deband} \cdot \frac{2.4}{255 \cdot \max(\text{guide}, 0.05)}$$
$$D = D_{\text{raw}} \cdot \text{smoothstep}(t, 2t, |D_{\text{raw}}|)$$
$$Y_b = \exp(B), \quad Y_d = \exp(B + D) - Y_b$$

### 2.3 Photometric Inverse Estimator ($\mathbf{L}_{\text{orig}}$ Solver)
On regions where albedo variance is low:
$$\nabla B(x,y) \approx \nabla (\mathbf{N}(x,y) \cdot \mathbf{L}_{\text{orig}})$$
Solving the normal-gradient covariance matrix gives:
$$\mathbf{L}_{\text{orig}} = \text{normalize}\left(\sum_{x,y} w(x,y) \nabla B(x,y) \cdot \mathbf{J}_{\mathbf{N}}^{-1}(x,y)\right)$$
$$S_{\text{old}}(x,y) = A_{\text{orig}} + (1 - A_{\text{orig}}) \left(\frac{\mathbf{N} \cdot \mathbf{L}_{\text{orig}} + w}{1 + w}\right)^+$$

### 2.4 Horizon-Based Ambient Occlusion (HBAO)
$$h_{\text{mean}}(x,y) = \text{BoxFilter}(h, r_{\text{ao}})$$
$$\text{AO}(x,y) = \text{clip}\left(1.0 - \gamma_{\text{ao}} \cdot \frac{\max(0, h_{\text{mean}} - h)}{\sigma_h + 10^{-4}}, \, 0.20, \, 1.0\right)$$

### 2.5 Angle-Aware Micro-Relief Texture Shading
$$\theta_{\text{raking}} = 1.0 - \max(0, \mathbf{N} \cdot \mathbf{L}_{\text{dominant}})$$
$$Y_d' = Y_d \cdot R^\lambda \cdot \left(1.0 + \kappa_{\text{relief}} \cdot \theta_{\text{raking}} \cdot \text{clip}(R, 0.5, 2.0)\right)$$

### 2.6 Spatially-Varying Roughness & Specular Inference
$$\sigma_{\text{hf}}(x,y) = \sqrt{\text{BoxFilter}(Y_d^2, r_{\text{mat}}) - (\text{BoxFilter}(Y_d, r_{\text{mat}}))^2}$$
$$\alpha(x,y) = \text{clip}\left(\alpha_{\text{base}} + 0.5 \cdot \frac{\sigma_{\text{hf}}}{\sigma_{\text{max}} + 10^{-5}}, \, 0.08, \, 0.90\right)$$
$$F_0(x,y) = F_{0,\text{base}} \cdot (1.0 - \text{clip}(\sigma_{\text{hf}} / \sigma_{\text{max}}, 0, 0.7))$$

### 2.7 Energy-Conserving Cook-Torrance GGX Specular
$$F(\mathbf{H}) = F_0 + (1 - F_0)(1 - \mathbf{H} \cdot \mathbf{V})^5$$
$$f_{\text{spec}} = \frac{D_{\text{GGX}}(\mathbf{H}, \alpha) \cdot G_{\text{Smith}}(\mathbf{L}, \mathbf{V}, \mathbf{N}, \alpha) \cdot F(\mathbf{H})}{4 (\mathbf{N} \cdot \mathbf{V}) + 10^{-4}}$$
$$\mathbf{C}_{\text{linear}} = (1 - F) \cdot \mathbf{C}_{\text{diffuse}} \cdot \text{AO} + \mathbf{C}_{\text{specular}}$$

### 2.8 Chromatic Subsurface Scattering (SSS)
$$\tau(x,y) = \exp\left(-\frac{(\mathbf{N} \cdot \mathbf{L})^2}{2 \sigma_{\text{term}}^2}\right) \cdot \text{mask}(x,y)$$
$$\mathbf{C}_{\text{sss}} = \kappa_{\text{sss}} \cdot \tau(x,y) \cdot \text{GaussianBlur}(\mathbf{C}_{\text{lin}}, \sigma_{\text{sss}}) \odot \mathbf{W}_{\text{sss}}$$

---

## 3. ENGINE v5 COMPONENT STRUCTURE

```
engine/relighter_v5.py
├── class Light                  # Polar & Cartesian definitions, 7 emitter kinds + emission geometry
├── class Params                 # Universal parameters, materials, deband, micro-relief, HBAO, SSS
├── class Scene                  # Light-independent cache: sRGB, Lin, Y, Yb, Yd, Mask, Height, Normals, AO, Roughness
├── prepare_scene()              # Precomputes geometry, material maps, HBAO, and inverse light
├── estimate_original_light()    # Photometric gradient solver for L_orig and ambient floor
├── compute_hbao()               # Screen-space horizon ambient occlusion
├── infer_material_maps()        # Spatially-varying roughness and specular reflectance
├── contact_shadow()             # Screen-space raymarching with penumbra softening
├── ggx_specular()               # Microfacet GGX evaluation
├── subsurface_scattering()      # Chromatic terminator diffusion
├── shade()                      # Evaluates all lights: diffuse + SSS + contact shadows + GGX specular
├── relight_scene()              # Masked guided filtering, micro-relief coupling, energy conservation, tonemap
├── Result                       # Dataclass holding all output buffers and diagnostic passes
├── compute_metrics()            # Quantitative detail lock, banding, range, chroma shift
├── quality_gate()               # Auto-fallback validation
├── Visual Suite                 # make_board, sweep_wheel, sweep_elevation, sweep_types, sweep_materials
└── CLI                          # Full argument parser and batch processor
```

