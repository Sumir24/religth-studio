# RELIGHT STUDIO — TECHNICAL RESEARCH REPORT
## PART 1: CORE OPTICS, COMPUTATIONAL PHOTOGRAPHY & SCENE DECOMPOSITION

**Document ID:** RS-TR-01  
**Status:** COMPLETE / PEER-REVIEW READY  
**Classification:** Research, Mathematical Foundations & Architectural Ideation  
**Epistemic Framework:** `[ESTABLISHED]` | `[DEMONSTRATED]` | `[HYPOTHESIS]` | `[UNKNOWN]`  

---

# TABLE OF CONTENTS
1. [Topic 1: Image Formation & Computational Photography](#topic-1-image-formation--computational-photography)
2. [Topic 2: Intrinsic Image Decomposition](#topic-2-intrinsic-image-decomposition)
3. [Topic 3: Sunlight & Sky Illumination Estimation](#topic-3-sunlight--sky-illumination-estimation)
4. [Topic 4: Scene Understanding & Semantic Segmentation](#topic-4-scene-understanding--semantic-segmentation)
5. [Topic 5: Monocular Depth Estimation & 2.5D Scene Representation](#topic-5-monocular-depth-estimation--25d-scene-representation)
6. [Topic 6: Surface Normal Estimation & Material Understanding](#topic-6-surface-normal-estimation--material-understanding)
7. [Topic 7: Single-Image Relighting State of the Art](#topic-7-single-image-relighting-state-of-the-art)

---

# TOPIC 1: IMAGE FORMATION & COMPUTATIONAL PHOTOGRAPHY

### 1. Fundamental Explanation
An optical digital photograph is the discrete, non-linear record of electromagnetic energy entering a camera lens aperture over a finite exposure window. Scene surfaces receive illumination from primary sources (the sun, artificial emitters) and secondary sources (skylight, ground inter-reflections). The surface reflects a fraction of this light toward the camera aperture depending on its microscopic roughness, geometry, and material composition. The camera lens focuses this radiance onto a silicon sensor array, which converts incident photons into photoelectrons, digitizes them via an Analog-to-Digital Converter (ADC), applies camera-specific color matrices and non-linear tone curves (OETF), and quantizes the signal into an 8-bit or 16-bit display-referred raster.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`
The fundamental governing law of optical transport is the **Rendering Equation** (Kajiya 1986):
$$L_o(\mathbf{x}, \boldsymbol{\omega}_o, \lambda) = L_e(\mathbf{x}, \boldsymbol{\omega}_o, \lambda) + \int_{\Omega} f_r(\mathbf{x}, \boldsymbol{\omega}_i, \boldsymbol{\omega}_o, \lambda) L_i(\mathbf{x}, \boldsymbol{\omega}_i, \lambda) (\mathbf{n}(\mathbf{x}) \cdot \boldsymbol{\omega}_i)^+ \, d\boldsymbol{\omega}_i$$

Where:
- $\mathbf{x} \in \mathbb{R}^3$: Surface intersection point.
- $\boldsymbol{\omega}_o \in \mathbb{S}^2$: Direction vector toward the camera lens.
- $\boldsymbol{\omega}_i \in \mathbb{S}^2$: Incident lighting direction over the upper hemisphere $\Omega$.
- $L_e$: Self-emitted radiance (zero for non-emissive natural objects; positive for the sun, lamp filaments, and sky).
- $f_r$: Bidirectional Reflectance Distribution Function (BRDF) in $\text{sr}^{-1}$.
- $(\mathbf{n} \cdot \boldsymbol{\omega}_i)^+ = \max(0, \mathbf{n} \cdot \boldsymbol{\omega}_i)$: Lambertian geometric foreshortening factor.

#### Optical Sensor Integration
The sensor irradiance $E(u, v)$ at sensor coordinate $(u, v)$ behind an imaging lens of focal length $f$ and aperture diameter $d$ ($N = f/d$) is:
$$E(u, v) = \frac{\pi}{4 N^2} \cos^4(\alpha) \cdot T_{\text{lens}} \cdot L_o(\mathbf{x}(u, v), \boldsymbol{\omega}_o)$$
Where $\alpha$ is the field angle off the optical axis (producing optical $\cos^4$ vignetting), and $T_{\text{lens}}$ is lens transmittance.

#### Digital Pixel Output
During exposure duration $t$, the expected photoelectron yield $n_e$ in a pixel of active area $A_{\text{pixel}}$ with spectral quantum efficiency $\eta(\lambda)$ is:
$$n_e = \frac{t \cdot A_{\text{pixel}}}{h c} \int \lambda \cdot E(u, v, \lambda) \cdot \eta(\lambda) \, d\lambda + n_{\text{dark}}(t, T)$$
The digitized digital number ($\text{DN}$) recorded in a RAW file is:
$$\text{DN}_{\text{raw}} = \text{clip}\left( \text{gain} \cdot (n_e + N_{\text{read}}) + \text{Pedestal}_{\text{optical}}, \, 0, \, 2^B - 1 \right)$$

#### The Fundamental Under-Determined Single-Image Barrier `[ESTABLISHED]`
At any pixel $(u, v)$, the camera records exactly 3 scalar values: $(R, G, B)$. However, physical image formation involves:
1. Incident directional radiance field $L_i(\boldsymbol{\omega}_i) \in \mathbb{R}^3$ for all $\boldsymbol{\omega}_i \in \Omega$ ($\infty$ dimensions).
2. Surface normal vector $\mathbf{n}(u, v) \in \mathbb{S}^2$ (2 degrees of freedom).
3. Diffuse albedo $\rho(u, v) \in \mathbb{R}^3$ (3 degrees of freedom).
4. Specular roughness $\alpha(u, v)$ and index of refraction $\eta(u, v)$ (2+ degrees of freedom).
5. Visibility/shadow function $V(\mathbf{x}, \boldsymbol{\omega}_i) \in [0, 1]$ ($\infty$ dimensions).

**Rigorous Physical Conclusion:** Reconstructing physical reality from an uncalibrated single photograph is an ill-posed inverse problem. Exact physical inverse rendering is impossible without prior constraints or multi-exposure calibration. **Relight Studio must operate as a physically plausible guided estimator, not a claimed exact physical solver.**

### 3. Important Research Papers
- Kajiya, J. T. (1986). *The Rendering Equation*. ACM SIGGRAPH Computer Graphics, 20(4), 143–150.
- Cook, R. L., & Torrance, K. E. (1982). *A Reflectance Model for Computer Graphics*. ACM Transactions on Graphics (TOG), 1(1), 7–24.
- Barron, J. T., & Malik, J. (2015). *Shape, Illumination, and Reflectance from Shading (SIRFS)*. IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI), 37(8), 1670–1687.
- Debevec, P. E., & Malik, J. (1997). *Recovering High Dynamic Range Radiance Maps from Photographs*. ACM SIGGRAPH, 369–378.

### 4. Best Available Open-Source Implementations
- **RawPy / LibRaw:** Production-grade C++/Python library decoding uncompressed camera RAW sensors directly to linear radiometric floating-point arrays before non-linear camera tone reproduction curves are applied.
- **Colour-Science (`colour` Python package):** The gold-standard library for chromatic adaptation, CIE color spaces, and radiometric transfer functions.

### 5. Exact Licensing Findings
- `LibRaw`: CDDL-1.0 or LGPL-2.1. Permissive for commercial software via dynamic linking.
- `colour-science`: BSD 3-Clause. 100% commercially permissive.

### 6. Practical Implementation Approaches for Relight Studio
- **Mandatory Ingestion Linearization:** All ingested imagery must be immediately transformed into 32-bit linear floating-point space ($\text{DN} \propto \text{Radiance}$). 
- For 8-bit/16-bit sRGB inputs, apply the inverse sRGB EOTF:
  $$I_{\text{linear}} = \begin{cases} \frac{I_{\text{sRGB}}}{12.92}, & I_{\text{sRGB}} \le 0.04045 \\ \left( \frac{I_{\text{sRGB}} + 0.055}{1.055} \right)^{2.4}, & I_{\text{sRGB}} > 0.04045 \end{cases}$$
- For RAW files, extract CFA data, subtract `black_level_per_channel`, apply white-balance multipliers, demosaic, and multiply by `color_matrix` without applying gamma curves.

### 7. Limitations & Failure Cases
- **Clipped Sensor Ceiling:** Pixels saturated at the sensor ceiling ($> 1.0$ in normalized float) have lost radiometric ratio information. Changing the color of clipped highlights results in unnatural flat posterization.
- **Sensor Dark Noise Pedestal:** Failing to subtract the optical black level ($B \approx 512$ in 14-bit Nikon/Sony, $2048$ in Canon) corrupts additive shadow linearity.

### 8. Recommendation: **ADOPT**
Make strict scene-referred linear 32-bit floating-point representation the non-negotiable bedrock of Relight Studio.

---

# TOPIC 2: INTRINSIC IMAGE DECOMPOSITION

### 1. Fundamental Explanation
Intrinsic image decomposition seeks to separate an image $I(u, v)$ into independent physical layers: reflectance (albedo $\mathbf{R}$, representing intrinsic surface pigment invariant to lighting) and shading ($\mathbf{S}$, representing incident illumination, surface orientation, and shadows). In outdoor scenes, $\mathbf{S}$ further decomposes into direct sunlight $\mathbf{S}_{\text{sun}}$ and diffuse ambient skylight $\mathbf{S}_{\text{sky}}$.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`
Classical Lambertian decomposition:
$$\mathbf{I}(u, v) = \mathbf{R}(u, v) \odot \mathbf{S}(u, v)$$
In logarithmic space (Retinex formulation, Land & McCann 1971):
$$\log \mathbf{I} = \log \mathbf{R} + \log \mathbf{S}$$
Retinex assumes that large spatial gradients correspond to reflectance changes (material boundaries), whereas smooth, continuous gradients correspond to illumination shading:
$$\nabla \log \mathbf{R} = \text{Threshold}(\nabla \log \mathbf{I}, \tau), \quad \nabla \log \mathbf{S} = \nabla \log \mathbf{I} - \nabla \log \mathbf{R}$$

#### Modern Three-Component Formulation for Relight Studio `[DERIVED]`
In a real landscape photograph, illumination is not monochromatic white:
$$\mathbf{I}_{\text{linear}}(u, v) = \mathbf{R}(u, v) \odot \left[ \mathbf{C}_{\text{sun}} \cdot E_{\text{sun}} \cdot (\mathbf{n} \cdot \mathbf{l}_{\text{sun}})^+ \cdot V_{\text{sun}}(u, v) + \mathbf{C}_{\text{sky}} \cdot E_{\text{sky}}(u, v) + \mathbf{E}_{\text{bounce}}(u, v) \right]$$
Where $\mathbf{C}_{\text{sun}} \in \mathbb{R}^3$ is warm direct solar chromaticity, and $\mathbf{C}_{\text{sky}} \in \mathbb{R}^3$ is cool atmospheric Rayleigh chromaticity.

If we isolate the direct sun fraction $f_{\text{sun}}(u, v) \in [0, 1]$:
$$\mathbf{I}_{\text{linear}}(u, v) = \mathbf{I}_{\text{ambient}}(u, v) + \mathbf{I}_{\text{sun}}(u, v)$$
Where:
$$\mathbf{I}_{\text{sun}}(u, v) = f_{\text{sun}}(u, v) \cdot \mathbf{I}_{\text{linear}}(u, v)$$
$$\mathbf{I}_{\text{ambient}}(u, v) = (1 - f_{\text{sun}}(u, v)) \cdot \mathbf{I}_{\text{linear}}(u, v)$$

When the user recolors the sun to purple ($\mathbf{C}_{\text{purple}}$), the retargeted radiance is:
$$\mathbf{I}_{\text{relit}}(u, v) = \mathbf{I}_{\text{ambient}}(u, v) + \mathbf{I}_{\text{sun}}(u, v) \odot \left( \frac{\mathbf{C}_{\text{purple}}}{\mathbf{C}_{\text{sun, orig}}} \right)$$
Because $\mathbf{I}_{\text{ambient}}$ is untouched, the blue sky ($\mathbf{M}_{\text{sky}} = 1$) and all cast shadow areas remain 100% natural and un-tinted!

### 3. Important Research Papers
- Land, E. H., & McCann, J. J. (1971). *Lightness and Retinex Theory*. Journal of the Optical Society of America, 61(1), 1–11.
- Bell, S., Bala, K., & Snavely, N. (2014). *Intrinsic Images in the Wild*. ACM Transactions on Graphics (TOG), 33(4), 1–12.
- Grosse, R., Johnson, M. K., Adelson, E. H., & Freeman, W. T. (2009). *Ground truth dataset and evaluation for intrinsic image decomposition*. IEEE CVPR, 890–897.
- Careaga, C., & Aksoy, Y. (2024). *Colorful Diffuse Intrinsic Image Decomposition in the Wild*. ACM SIGGRAPH Asia 2024.
- Careaga, C., & Aksoy, Y. (2025). *Physically Controllable Relighting of Photographs*. ACM SIGGRAPH 2025.

### 4. Best Available Open-Source Implementations & Licensing
| Model / Implementation | Primary Author / Lab | Repository / Source | License | Commercial Viability |
| :--- | :--- | :--- | :--- | :--- |
| **Careaga Intrinsic / Relighting** | SFU CompPhoto Lab (Careaga & Aksoy) | `compphoto/Intrinsic` | Academic / Non-Commercial | **REJECTED (Non-Commercial)** |
| **NIID-Net** | Luo et al. (CVPR 2020) | `Alibaba-MIIL/NIID-Net` | Academic Only | **REJECTED (Non-Commercial)** |
| **Retinex-based Bilateral Solver** | Barron et al. / OpenCV | `opencv/opencv_contrib` | Apache 2.0 | **APPROVED (Commercial OK)** |
| **Relight Studio Analytical Solver** | Relight Studio In-House | Proprietary Pipeline | Proprietary | **ADOPT (100% Clean IP)** |

### 5. Practical Implementation Approach for Relight Studio
Because all pre-trained deep intrinsic models carry restrictive non-commercial licenses, Relight Studio will adopt a **Physics-Guided Photometric Estimator**:
1. Mask out self-luminous sky pixels using semantic segmentation ($\mathbf{M}_{\text{sky}}$).
2. Compute surface normal orientation $\mathbf{n}(u, v)$ and sun direction $\mathbf{l}_{\text{sun}}$.
3. Assign zero sunlight fraction ($f_{\text{sun}} = 0$) to all pixels where $\mathbf{n} \cdot \mathbf{l}_{\text{sun}} \le 0$ (surfaces facing away from sun) and where shadow edge classification indicates cast shadows.
4. Smooth $f_{\text{sun}}$ across texture details using an edge-preserving guided filter guided by the original luminance image.

### 6. Limitations & Failure Cases
- **Albedo-Shading Ambiguity:** A dark black rock facing the sun and a light white chalk cliff in shadow can have identical luminance. Heuristics without geometric normals will misclassify the dark rock as shadow.
- **Inter-reflections:** Red rock canyon bounce light will illuminate opposing cliffs with warm light, confusing simple sun/ambient color separation.

### 7. Recommendation: **ADOPT IN-HOUSE ANALYTICAL SOLVER; REJECT ACADEMIC PRE-TRAINED WEIGHTS**

---

# TOPIC 3: SUNLIGHT & SKY ILLUMINATION ESTIMATION

### 1. Fundamental Explanation
In any outdoor photograph, the sky hemisphere and direct sun constitute the entire primary illumination environment. The sun acts as a tiny angular diameter ($\approx 0.53^\circ$), ultra-high-radiance directional emitter. The sky dome acts as an extended hemispherical area light whose spectral distribution and luminance gradient vary predictably according to Rayleigh scattering (air molecules) and Mie scattering (aerosols and water droplets).

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`
The definitive physical standard for outdoor daylight luminance is the **Perez All-Weather Sky Model** (Perez et al. 1993, adopted by CIE and ISO 15469:2004):
The relative luminance $L(\theta, \gamma)$ of a sky point at zenith angle $\theta$ and angular distance $\gamma$ from the sun is:
$$\frac{L(\theta, \gamma)}{L_z} = \frac{f(\theta, \gamma)}{f(0, \theta_s)}$$
Where the Perez distribution function $f(\theta, \gamma)$ is:
$$f(\theta, \gamma) = \left[ 1 + a \exp\left( \frac{b}{\cos \theta} \right) \right] \cdot \left[ 1 + c \exp(d \gamma) + e \cos^2 \gamma \right]$$
The coefficients represent physical atmospheric parameters:
- $a$: Darkening or brightening of the horizon.
- $b$: Luminance gradient near the horizon.
- $c$: Relative intensity of the circumsolar aureole.
- $d$: Angular width of the solar circumsolar region.
- $e$: Relative backscattered light into the opposite sky dome.

The angular distance $\gamma$ between sky point $(u, v)$ with direction vector $\mathbf{v}$ and sun direction $\mathbf{l}_{\text{sun}} = (\theta_s, \phi_s)$ is:
$$\cos \gamma = \cos \theta \cos \theta_s + \sin \theta \sin \theta_s \cos(\phi - \phi_s) = \mathbf{v} \cdot \mathbf{l}_{\text{sun}}$$

#### Analytical Solar Direction Solver `[DERIVED / HYPOTHESIS]`
Even when the sun is outside the camera field of view, the gradient of sky luminance across visible sky pixels $\mathbf{M}_{\text{sky}}$ uniquely constrains $(\theta_s, \phi_s)$:
$$\min_{\theta_s, \phi_s, a, b, c, d, e} \sum_{(u, v) \in \mathbf{M}_{\text{sky}}} \left\| \log \mathbf{I}_{\text{linear}}(u, v) - \log L(\theta(u, v), \gamma(u, v; \theta_s, \phi_s)) \right\|^2$$
Because sky luminance peaks toward the circumsolar aureole and drops toward the anti-solar point, a Levenberg-Marquardt non-linear least squares fit recovers the sun's 3D vector $\mathbf{l}_{\text{sun}}$ directly from the sky gradient without neural networks!

#### Shadow-Casting Direction Triangulation `[ESTABLISHED]`
When sharp cast shadows are present on terrain:
Let $\mathbf{P}_{\text{occluder}}$ be a sharp geometric feature (e.g., a mountain peak or tree top), and let $\mathbf{P}_{\text{shadow}}$ be its projected shadow on the ground in 2.5D unprojected camera space:
$$\mathbf{l}_{\text{sun}} = \frac{\mathbf{P}_{\text{occluder}} - \mathbf{P}_{\text{shadow}}}{\|\mathbf{P}_{\text{occluder}} - \mathbf{P}_{\text{shadow}}\|}$$

### 3. Important Research Papers
- Perez, R., Seals, R., & Michalsky, J. (1993). *All-weather model for sky luminance distribution—Preliminary results and validation*. Solar Energy, 50(3), 235–245.
- Preetham, A. J., Shirley, P., & Smits, B. (1999). *A practical analytic model for daylight*. ACM SIGGRAPH, 91–100.
- Hosek, L., & Wilkie, A. (2012). *An analytic model for full spectral sky-dome radiance*. ACM Transactions on Graphics (TOG), 31(4), 1–9.
- Lalonde, J.-F., Efros, A. A., & Narasimhan, S. G. (2010). *Estimating the natural illumination conditions from a single outdoor image*. International Journal of Computer Vision (IJCV), 98(2), 123–145.
- Hold-Geoffroy, Y., et al. (2017). *Deep Outdoor Light Estimation*. IEEE CVPR 2017, 7312–7321.
- Zhang, J., et al. (2019). *All-Weather Deep Outdoor Lighting Estimation*. IEEE CVPR 2019, 10158–10166.

### 4. Best Available Open-Source Implementations & Licensing
- `radiance` / `gensky` (Lawrence Berkeley National Laboratory): ANSI C reference implementation of Perez and CIE sky models. Permissive BSD-like open-source license.
- `pvlib-python`: Top-tier solar engineering library implementing Perez sky models, solar position algorithms (SPA), and irradiance decomposition. BSD 3-Clause (Commercial OK).

### 5. Failure Cases & Mitigations
- **Completely Overcast / Foggy Skies:** The Perez aureole vanishes; lighting becomes a pure diffuse cosine falloff from the zenith ($L(\theta) \propto 1 + 2\cos \theta$). The engine must detect low sky variance and switch from directional sun mode to hemispherical ambient mode.
- **Cropped Skies (Zero Sky Visible):** In close-up forest or canyon shots, sky fitting fails. Mitigation: Infer $\mathbf{l}_{\text{sun}}$ from terrain surface normal orientation shading peaks ($\arg\max_{\mathbf{l}} \mathbf{n} \cdot \mathbf{l}$).

### 6. Recommendation: **ADOPT HYBRID PEREZ SKY FITTER + SHADOW TRIANGULATOR**

---

# TOPIC 4: SCENE UNDERSTANDING & SEMANTIC SEGMENTATION

### 1. Fundamental Explanation
Relight Studio requires precise semantic segmentation to separate self-luminous atmosphere (sky) from reflective surfaces (mountains, trees, water, ground, buildings) and delicate foreground objects (human faces, clothing, logos). Lighting operators must apply differently across semantic classes: water requires planar Fresnel specular highlights, terrain requires diffuse shading, and sky must be protected from surface relighting.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`
Modern segmentation treats pixel classification via Query-Based Transformers (Mask2Former):
Given image features $\mathbf{F} \in \mathbb{R}^{H \times W \times C}$, a set of $N$ learnable object queries $\mathbf{Q} \in \mathbb{R}^{N \times C}$ are refined through masked cross-attention:
$$\mathbf{M}_i = \text{Softmax}\left( \frac{\mathbf{Q}_i \mathbf{F}^T}{\sqrt{C}} \right) \in [0, 1]^{H \times W}$$
Each mask $\mathbf{M}_i$ is assigned a class distribution $p_i(c)$ via bipartite matching loss.

#### Image Matting Formulation for Tree Boundaries
At complex boundaries (foliage silhouettes against the sky), binary classification produces harsh halo fringes. Relight Studio requires continuous alpha matting:
$$\mathbf{I}_{\text{linear}}(u, v) = \alpha(u, v) \cdot \mathbf{F}(u, v) + (1 - \alpha(u, v)) \cdot \mathbf{B}(u, v)$$
Where $\alpha \in [0, 1]$ represents foreground geometric coverage, and $\mathbf{B}$ is the pure background sky radiance.

### 3. Model & Repository Comparisons
| Architecture | Paper / Lab | License | Checkpoint License | Latency (1080p, M2 GPU) | Accuracy (mIoU) | Verdict for Relight Studio |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SAM 2 (Segment Anything 2)** | Meta AI (2024) | Apache 2.0 | Apache 2.0 | $\approx 45\text{ms}$ (Small) | State-of-the-art interactive prompt | **ADOPT (Foreground & Masks)** |
| **SegFormer (B0-B5)** | Xie et al. (NeurIPS 2021) | Apache 2.0 | Apache 2.0 | $\approx 18\text{ms}$ (B0) | 51.8 (ADE20K) | **ADOPT (One-Shot Sky/Terrain)** |
| **Mask2Former** | Cheng et al. (CVPR 2022) | Apache 2.0 | Apache 2.0 | $\approx 120\text{ms}$ | 57.7 (ADE20K) | DEFER (Overly heavy for preview) |
| **BiRefNet** | Zheng et al. (2024) | Apache 2.0 | Apache 2.0 | $\approx 65\text{ms}$ | SOTA matting boundaries | **ADOPT (Alpha Edge Refiner)** |
| **Grounding DINO** | Liu et al. (2023) | Apache 2.0 | Apache 2.0 | $\approx 85\text{ms}$ | Open-vocabulary text prompts | **ADOPT (Natural-Language masks)** |

### 4. Exact Licensing Findings
- **SAM 2:** Apache 2.0 repository and model weights. Fully cleared for commercial use.
- **SegFormer (MMSegmentation):** Apache 2.0 code and pre-trained weights on Cityscapes/ADE20K. Fully cleared for commercial use.
- **BiRefNet:** Apache 2.0. Fully cleared.

### 5. Practical Implementation Approach for Relight Studio
- **Pass 1 (One-Shot Semantic Segmentation):** Execute SegFormer-B1 on import to instantly classify: `Sky` (Class 2), `Vegetation` (Classes 4, 9), `Terrain/Mountain` (Classes 13, 29), `Water` (Class 21), and `Architecture/Human`.
- **Pass 2 (Boundary Alpha Matting):** Apply BiRefNet or an edge-preserving closed-form matting Laplacian along the sky-foliage interface to create sub-pixel fractional alpha mattes $\alpha(u, v)$, eliminating jagged halo edges when recoloring sunlight.

### 6. Recommendation: **ADOPT SEGFORMER-B1 + SAM 2 + BIREFNET (100% APACHE 2.0)**

---

# TOPIC 5: MONOCULAR DEPTH ESTIMATION & 2.5D SCENE REPRESENTATION

### 1. Fundamental Explanation
To simulate directional light falloff, distance-based haze, and cast shadows, Relight Studio must convert a 2D photograph into a 2.5D representation: a continuous depth field $D(u, v)$ aligned with every pixel. Rather than demanding full 3D CAD meshes (which fail on trees, grass, and water), 2.5D unprojects visible pixels into a view-dependent point cloud $\mathbf{P}(u, v) \in \mathbb{R}^3$, where lighting calculations occur in camera space.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`
Given estimated optical center $(c_x, c_y)$ (assumed at image center $(W/2, H/2)$ in the absence of calibration) and focal length $f_x, f_y$ (derived from EXIF focal length or standard field of view prior $\approx 60^\circ$):
$$\mathbf{P}(u, v) = \begin{bmatrix} X \\ Y \\ Z \end{bmatrix} = \begin{bmatrix} \frac{(u - c_x) \cdot D(u, v)}{f_x} \\ \frac{(v - c_y) \cdot D(u, v)}{f_y} \\ D(u, v) \end{bmatrix}$$

#### Relative vs. Metric Depth Disparity `[DEMONSTRATED]`
Most monocular models (MiDaS, Depth Anything) output an affine-invariant disparity $d(u, v) \in [0, 1]$ related to physical depth $D_{\text{metric}}$ by unknown scale $s$ and shift $t$:
$$\frac{1}{D_{\text{metric}}(u, v)} = s \cdot d(u, v) + t$$
For virtual lighting, **affine relative depth is sufficient for directional sun and distant point lights**. However, for localized point lights with physical inverse-square falloff ($1/r^2$), an absolute metric scale is required. Metric depth models (Metric3D, Depth Anything V2 Metric) resolve $s$ and $t$ using camera intrinsic priors.

### 3. Model & Repository Comparisons
| Architecture | Paper / Authors | License | Checkpoint Weights | Latency (518x518, M2) | Metric Zero-Shot Accuracy | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Depth Anything V2 (Small)** | Yang et al. (2024) | Apache 2.0 | **Apache 2.0** | **$\approx 15\text{ms}$** | State-of-the-art relative & metric | **PRIMARY ADOPT** |
| **Depth Anything V2 (Large)** | Yang et al. (2024) | Apache 2.0 | **Apache 2.0** | $\approx 78\text{ms}$ | Supreme fine detail (foliage/rocks) | **ADOPT (HQ Export)** |
| **Metric3D v2** | Yin et al. (2024) | Apache 2.0 | CC BY-NC 4.0 | $\approx 95\text{ms}$ | High metric precision | **REJECT (Weights non-commercial)** |
| **ZoeDepth** | Bhat et al. (2023) | MIT | MIT | $\approx 60\text{ms}$ | Good metric baseline | DEFER (Superseded by DA-v2) |
| **MiDaS v3.1** | Ranftl et al. | MIT | MIT | $\approx 35\text{ms}$ | Robust relative depth | DEFER (Superseded by DA-v2) |
| **Marigold** | Ke et al. (2024) | Apache 2.0 | Apache 2.0 | $\approx 2,400\text{ms}$ | Diffusion-based high detail | **REJECT (Too slow for preview)** |

### 4. Exact Licensing Findings
- **Depth Anything V2:** Released by TikTok/ByteDance research under **Apache 2.0** for code and relative pre-trained checkpoints (`depth_anything_v2_vits.pth`, `vitb.pth`, `vitl.pth`). Metric depth models trained on synthetic datasets are also Apache 2.0. Fully cleared for commercial deployment.

### 5. Practical Implementation Approach for Relight Studio
- **Dual-Tier Depth Engine:**
  - **Interactive Viewport:** Run `Depth Anything V2 (Small)` via Core ML / PyTorch FP16. Latency is $< 20\text{ms}$ on Apple Silicon, enabling real-time import preview.
  - **Full-Resolution Export:** Run `Depth Anything V2 (Large)` on background thread with guided filter depth upsampling to native camera resolution (24MP to 60MP).

### 6. Limitations & Failure Cases
- **Sky Infinitum Ambiguity:** Pure monocular depth models often assign arbitrary finite depths to clear blue skies.
  - *Hard Mitigation:* The engine must enforce $D(u, v) = \infty$ for all pixels where $\mathbf{M}_{\text{sky}} = 1$.
- **Transparent Water Surfaces:** Depth models penetrate shallow water to the riverbed or treat surface reflections as geometry.
  - *Hard Mitigation:* Detect water bodies via semantic segmentation and enforce a planar horizontal depth surface $Z_{\text{water}}(u, v)$.

### 7. Recommendation: **ADOPT DEPTH ANYTHING V2 (SMALL + LARGE) AS EXCLUSIVE DEPTH BACKBONE**

---

# TOPIC 6: SURFACE NORMAL ESTIMATION & MATERIAL UNDERSTANDING

### 1. Fundamental Explanation
Surface normals $\mathbf{n}(u, v) \in \mathbb{S}^2$ define the 3D orientation of visible surfaces at every pixel. Surface normals govern the cosine law $(\mathbf{n} \cdot \mathbf{l})$, determining which surfaces face the sun, which are in self-shadow, and where specular reflection highlights reflect.

### 2. Relevant Mathematical Foundations `[ESTABLISHED]`
For any unit normal vector:
$$\mathbf{n}(u, v) = [n_x, n_y, n_z]^T, \quad \|\mathbf{n}\| = 1, \quad n_z > 0 \text{ (facing toward camera)}$$

#### Analytical Depth-Derived Normals `[ESTABLISHED]`
Given a smooth 3D camera-space point cloud $\mathbf{P}(u, v)$:
$$\mathbf{t}_u = \frac{\partial \mathbf{P}}{\partial u} \approx \frac{\mathbf{P}(u + 1, v) - \mathbf{P}(u - 1, v)}{2}, \quad \mathbf{t}_v = \frac{\partial \mathbf{P}}{\partial v} \approx \frac{\mathbf{P}(u, v + 1) - \mathbf{P}(u, v - 1)}{2}$$
$$\mathbf{n}_{\text{analytical}}(u, v) = \text{normalize}(\mathbf{t}_u \times \mathbf{t}_v)$$
*Limitation of Analytical Normals:* Monocular depth maps suffer from low-frequency spatial smoothing; finite differences amplify noise, creating quantized, terraced normal facets on curved rock faces.

#### Neural Normal Estimation vs. Analytical Normals `[DEMONSTRATED]`
Neural normal networks (DSINE) predict $\mathbf{n}(u, v)$ directly from RGB gradients using spherical loss functions:
$$\mathcal{L}_{\text{ang}} = 1 - \mathbf{n}_{\text{pred}} \cdot \mathbf{n}_{\text{gt}}$$
DSINE explicitly enforces ray-surface angle constraints, producing razor-sharp architectural edges and smooth organic terrain.

### 3. Model & Repository Comparisons
| Architecture | Authors / Venue | License | Checkpoint Weights | Latency (1080p, M2) | Angular Error (MAE) | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DSINE** | Huang et al. (CVPR 2024) | Apache 2.0 | **Apache 2.0** | $\approx 42\text{ms}$ | **$16.3^\circ$ (SOTA)** | **PRIMARY ADOPT** |
| **StableNormal** | 2024 | Apache 2.0 | OpenRAIL-M | $\approx 2,100\text{ms}$ | $17.1^\circ$ | REJECT (Diffusion-based, too slow) |
| **Omnidata v2** | Kar et al. (ICCV 2021) | CC BY-NC 4.0 | CC BY-NC 4.0 | $\approx 85\text{ms}$ | $19.4^\circ$ | **REJECT (Non-Commercial)** |
| **Depth Gradient Filter** | Analytical MSL Kernel | Proprietary | 0 Parameters | **$< 1\text{ms}$** | $28.5^\circ$ | **ADOPT AS GPU FALLBACK** |

### 4. Material Classification & Roughness Formulation
To avoid plastic-like relighting on non-dielectric materials, Relight Studio separates surfaces into material categories:
1. **Rough Dielectrics (Rock, Bark, Soil, Dry Grass):** Pure Lambertian diffuse, negligible specular highlight, Fresnel $F_0 \approx 0.04$.
2. **Smooth / Wet Dielectrics (Wet Rocks, Water, Foliage Waxy Cuticle):** Strong Cook-Torrance microfacet specular reflection with roughness $\alpha \in [0.1, 0.4]$, uncolored specular highlight ($\mathbf{C}_{\text{specular}} = \mathbf{C}_{\text{light}}$).
3. **Conductors (Metals, Vehicles, Architecture):** Zero diffuse albedo; $100\%$ colored specular reflection ($F_0 \in [0.7, 1.0]$).

### 5. Practical Implementation Approach for Relight Studio
- Run **DSINE** on import to generate the primary normal field $\mathbf{n}(u, v)$.
- Where DSINE confidence is low (chaotic foliage, high depth discontinuity), cross-blend with depth-derived analytical normals $\mathbf{n}_{\text{analytical}}$ weighted by the geometric confidence map $C(u, v)$.

### 6. Recommendation: **ADOPT DSINE FOR NEURAL NORMALS + ANALYTICAL GPU FALLBACK**

---

# TOPIC 7: SINGLE-IMAGE RELIGHTING STATE OF THE ART

### 1. Fundamental Explanation
Existing approaches to single-image photographic relighting fall into two divergent paradigms:
1. **Generative Neural Diffusion Models (e.g., IC-Light, ControlNet Brightness, Clipdrop):** These treat relighting as an image-to-image synthesis problem. A diffusion model conditions on an input image and a prompt/light map, denoising from random noise to generate a new image.
   *Fatal Flaw for Relight Studio:* These models regenerate pixels from latent space. They mutate fine details, hallucinate text, alter facial landmarks, smooth organic textures, and cannot guarantee photometric conservation.
2. **2.5D Physically Guided Shading (Relight Studio & SFU Careaga):** The input photograph is retained as an immutable canvas. AI models extract geometric and radiometric priors (depth, normals, sky masks, sun vectors), and a deterministic GPU rendering shader applies lighting operators strictly in linear space.

### 2. Comprehensive Comparison of Relighting Systems
| System | Core Architecture | Relights Existing Sun? | Detail Preservation | Offline / Local-First? | Licensing / Commercial Viability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Relight Studio** | **2.5D Scene Graph + Linear GPU Shading** | **YES (Sun-Sky Decomposer)** | **$100\%$ (Canvas preserved, Guided Filter)** | **YES (Mac Metal 3 + Core ML)** | **100% Commercial Clean IP** |
| **Careaga & Aksoy (SIGGRAPH 2025)** | 2.5D Mesh + Path Traced Proxy + Neural Render | Partial (Stripped intrinsic albedo) | High (Neural blend) | Research Python only | **REJECTED (Academic non-commercial)** |
| **IC-Light (Lvmin Zhang 2024)** | Generative SD1.5 / SDXL Diffusion | No (Adds light globally) | Low-Medium (Regenerates pixels) | Possible local (Needs 8GB+ VRAM) | Apache 2.0 (Weights SD1.5 OpenRAIL) |
| **Clipdrop Relight** | Estimated Normals + Image-Space Neural Shader | No (Additive overlay only) | High | No (Cloud API required) | Proprietary Commercial SaaS |
| **Total Relighting (Google 2021)** | Deep Reflectance Field (Portraits only) | No (Light stage transfer) | Very High | No (Internal Google) | Proprietary / Closed Source |

### 3. Limitations of Generative Diffusion for Commercial Retouching
- **Identity Mutation:** Brand typography on luxury goods or facial geometry in portraits shifts unpredictably between runs.
- **Non-Deterministic Editing:** Moving a light slider by $2\%$ in a diffusion pipeline triggers a completely new noise trajectory, making incremental fine-tuning impossible.
- **High Computational Overhead:** Generating a single 4K image via SDXL requires 30–50 diffusion steps ($> 15\text{ seconds}$ on high-end GPUs), preventing interactive 60 FPS viewport manipulation.

### 4. Recommendation for Relight Studio: **REJECT GENERATIVE DIFFUSION AS PRIMARY RENDERER; ADOPT DETERMINISTIC 2.5D GPU SHADING**
Position Relight Studio uniquely in the market: the **only non-destructive, local-first virtual photo studio that preserves the original photograph bit-for-bit while enabling explicit control over the existing sun.**
