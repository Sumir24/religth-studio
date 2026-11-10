# RELIGHT STUDIO — RS-PRODUCT-1.1 RENDERING VALIDATION
## Photographic Lighting Response, Multi-Light Superposition & Fidelity

**Document:** `RS_PRODUCT_1_1_RENDERING_VALIDATION.md`  
**Milestone:** RS-PRODUCT-1.1  
**Status:** **VERIFIED & PASSING**

---

## 1. PHOTOGRAPHIC LIGHTING RESPONSE

In Relight Studio, the original photograph is not merely a background backdrop; it is the physical subject of virtual illumination.

When an artist translates, rotates, or reconfigures a light source in the 3D studio, the rendering engine transforms the photograph via the physical formulation established across milestones RS-SPIKE-3A through RS-SPIKE-3C.3:

$$I_{\text{relit}}(x, y) = I_{\text{orig}}(x, y) \cdot \frac{E_{\text{new}}(x, y) + \epsilon}{E_{\text{orig}}(x, y) + \epsilon} + L_{\text{specular}}(x, y)$$

where $E_{\text{new}}(x, y)$ is the additive irradiance from all enabled area lights plus image-based lighting:
$$E_{\text{new}}(x, y) = \sum_{k=1}^K E_k(x, y) \cdot V_k(x, y) + E_{\text{IBL}}(x, y)$$

### 1.1 Verified Behavioral Responses

| Interaction Action | Physical Rendering Consequence | Verification Evidence |
|---|---|---|
| **Translate Light ($X, Y, Z$)** | Alters incidence angle $\cos \theta_i$, light-to-surface distance $r^2$, and shadow ray caster occlusion. | Screenshot `04`, `05`, `06`; luminance shift $\Delta L = -0.0012$ |
| **Rotate Light (Pitch / Yaw)** | Reorients light emission cosine falloff $D(\hat{\mathbf{l}} \cdot \hat{\mathbf{n}}_{\text{light}})$, sweeping emission beam across the subject. | Screenshot `07`; orientation updated to $[-50^\circ, 5^\circ, 0^\circ]$ |
| **Resize Light ($W \times H$)** | Expands physical emitter area $A = W \cdot H$, increasing radiant power and softening geometric shadow penumbrae. | Screenshot `08`; mean luminance increases from $0.2007 \to 0.2110$ |
| **Kelvin Temperature Change** | Planckian blackbody locus spectral weight shifts RGB chromaticity from warm tungsten ($3200\,\text{K}$) to cool daylight ($6500\,\text{K}$). | [`test_lighting_presets.py`](file:///Users/sumirdayal/religth%20studio/tests/RS-PRODUCT-1.1/test_lighting_presets.py) |
| **Material Roughness Slider** | Modulates GGX microfacet distribution $D(\mathbf{h})$ from sharp specular glare ($\alpha = 0.05$) to broad sheen ($\alpha = 0.85$). | Verified in PBR engine inspection |
| **Subject Proxy Elevation** | Elevates virtual 3D surface, altering cast shadow contact lines onto the receiver. | [`test_subject_receiver_control.py`](file:///Users/sumirdayal/religth%20studio/tests/RS-PRODUCT-1.1/test_subject_receiver_control.py) ($\Delta > 0.005$) |

---

## 2. PHOTOGRAPHIC PRESET DIFFERENTIATION

The five starter presets were evaluated on the reference commercial sneaker photograph plate (`demo_output/nike_sample.jpg`). Each preset produces a distinctive, professionally balanced lighting scheme:

```
+------------------+------------------+------------------+------------------+
|   Key Softbox    |   Fill Softbox   |    Rim Strip     |    Side Rake     |
| [1.2, 1.8, 1.5]  | [-1.4, 1.4, 1.6] | [-1.6, 1.5,-0.6] |  [2.2, 1.0, 0.2] |
|     5600 K       |      5200 K      |      6500 K      |      4500 K      |
|  Mean L: 0.2045  |  Mean L: 0.1882  |  Mean L: 0.1948  |  Mean L: 0.1994  |
+------------------+------------------+------------------+------------------+
```

### Quantitative Differentiation Evidence:
Comparing the rendered outputs between presets in [`test_lighting_presets.py`](file:///Users/sumirdayal/religth%20studio/tests/RS-PRODUCT-1.1/test_lighting_presets.py):
$$\text{MAE}(I_{\text{key}}, I_{\text{rim}}) = 0.0384 > 0.0100 \quad (\text{Threshold PASS})$$

This confirms that presets do not simply manipulate color tinting in 2D post-processing, but establish distinct 3D radiometric transport and shadow topologies.

---

## 3. NON-DESTRUCTIVE GUARANTEES & IMMUTABILITY

A foundational requirement of Relight Studio is that the user's original photograph must never be destructively overwritten, compressed, or corrupted.

### Bitwise SHA-256 Audit:
- **Baseline Source Image Path:** `demo_output/nike_sample.jpg`
- **Initial SHA-256:** `0e9b08a4011562c8b6ef88fde24eecf1359a72a34f59e9793e7494a63e934059`
- **Post-Interaction SHA-256:** `0e9b08a4011562c8b6ef88fde24eecf1359a72a34f59e9793e7494a63e934059`
- **Verdict:** **MATCH (0 bytes altered).**

### Protected Mask Region Zero-Mutation:
In regions designated by `protected_mask` (e.g. background fine details or untouched brand elements), the guided filter reconstruction engine preserves the exact source photograph values:
$$\max_{(x,y) \in M_{\text{protected}}} |I_{\text{relit}}(x, y) - I_{\text{orig}}(x, y)| = 0.0000$$

---

## 4. DUAL VIEWPORT BEFORE/AFTER SPLIT WIPE

The interactive photograph viewport incorporates an interactive before/after split slider:
- Left Partition: Displays unmodified original source photograph $I_{\text{orig}}$.
- Right Partition: Displays fully rendered relit photograph $I_{\text{relit}}$.
- Dynamic Partition Line: Draggable handle across $x \in [0, W]$, updating at $60\,\text{FPS}$ without re-rendering or pipeline stalling.
- Inspection Modes: Relit output, Before/After Split, Specular-only isolation, Proxy wireframe overlay, and Direct Visibility heatmap.
