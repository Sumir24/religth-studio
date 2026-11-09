# Relight Studio

**Relight Studio** is a high-precision physically-based relighting engine designed for commercial product photography and computational imagery.

> *"Change the lighting. Preserve the product."*

Unlike unconstrained inverse rendering or generative diffusion models that hallucinate textures and distort geometry, Relight Studio utilizes physically based rendering (PBR), deterministic geometry guidance, and photometric de-lighting to achieve studio-grade relighting with 100% identity and texture preservation.

---

## Key Features

- **Photometric De-Lighting:** Solves for original incident radiance vectors $L_{\text{orig}}$ to neutralize baked shadows and prevent lighting conflict.
- **Micro-Relief Texture Shading:** Dynamic micro-shadowing that sharpens under raking incident light and softens under frontal fill.
- **Spatially-Varying Material Inference:** Derives localized roughness ($\alpha$) and specular Fresnel reflectance ($F_0$) directly from high-frequency texture variance and chroma saturation.
- **Screen-Space Horizon Ambient Occlusion (HBAO):** Deep crevices, seams, and sole grooves darken naturally without flat ambient washouts.
- **Chromatic Subsurface Scattering (SSS):** Simulates spectral light diffusion across shadow terminators to eliminate chalky boundaries on skin, marble, and organic materials.
- **Halo-Free Guided Filtering:** Multi-scale guided bilateral filtering separates base lighting from fine micro-detail without haloing or ringing artifacts.
- **Intuitive Studio Light Placement:** Polar coordinate controls (clock-face azimuth $0^\circ \text{--} 360^\circ$, elevation $-90^\circ \text{--} +90^\circ$) mapped to classic studio techniques (Rembrandt, Split, Rim, Softbox, Uplight).

---

## Architecture & Directory Structure

```text
├── engine/                # Core relighting engines and shaders
│   ├── relighter_v4.py    # Polar GGX microfacet PBR engine
│   ├── relighter_v5.py    # v5 engine with de-lighting, HBAO, and SSS
│   ├── preprocessor.py    # Surface normal & depth preprocessing
│   └── shaders/           # Metal and WGSL compute shaders
├── benchmarks/            # Benchmark suites and profiling scripts
├── demo_output/           # Test assets, comparison boards, and evaluation reports
├── docs/                  # Architectural blueprints and engineering decision logs
└── tests/                 # Unit and regression test suites
```

---

## Quick Start

### Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install numpy scipy pillow opencv-python pytest
```

### Running Tests

```bash
pytest tests/
```

### Running Benchmarks

```bash
python3 benchmark_v5.py
```

