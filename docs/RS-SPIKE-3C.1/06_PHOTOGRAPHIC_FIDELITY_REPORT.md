# RS-SPIKE-3C.1 — Engineering Report 06: Photographic Fidelity & Detail Conservation

**Milestone:** RS-SPIKE-3C.1 (Multi-Light Architecture & Additive Illumination)  
**Author:** Principal Computational Photography Engineer & Imaging Auditor  
**Branch:** `feature/RS-SPIKE-3C.1-multilight-architecture`  
**Test Harness:** `benchmarks/run_spike3c1_photographic_fidelity.py`  
**Status:** VALIDATED & CLOSED

---

## 1. Executive Summary & Verification Context

In RS-SPIKE-3B.1, the independent audit discovered that whole-image Detail Conservation Index ($DCI_{\text{whole}}$) masked foreground degradation on the Nike footwear plate because the large, uniform background diluted the structural SSIM metric ($0.8282$ foreground vs $0.8941$ whole image).

In RS-SPIKE-3C.0, the native Metal 8-pass E.1 Guided-Filter implementation resolved this for single-light rendering, restoring isolated foreground DCI to $>0.9500$.

The purpose of **RS-SPIKE-3C.1 Workstream D** is to prove that **multi-light additive illumination preserves high-frequency photographic texture and micro-contrast** across complex, real-world plates under multiple independent light sources without causing texture blur, edge blooming, or highlight blowout.

---

## 2. Experimental Methodology & Test Plates

Evaluations were performed across three diverse real-world photographic plates:
1. **Plate P1 (Nike Sneaker):** $576 \times 1024$ macro photograph of footwear containing complex high-frequency mesh knit, embossed rubber swoosh, and synthetic leather textures.
2. **Plate P2 (Classical Statue):** $576 \times 1024$ photographic portrait of an antique marble sculpture exhibiting smooth continuous curvature and organic subsurface features.
3. **Plate P3 (Architectural Relief):** $768 \times 512$ outdoor architectural masonry with sharp geometrical stone contours and high dynamic range.

For each plate, three standard commercial studio lighting rigs were evaluated on the native Metal GPU pipeline:
- **Rig 1 (1 Light):** Key Softbox ($5600\,\text{K}$, $1.4\times$ intensity).
- **Rig 2 (2 Lights):** Key Softbox + Fill Softbox ($3200\,\text{K}$ warm tungsten, opposing $35^\circ$ angle, $0.6\times$ intensity).
- **Rig 3 (3 Lights):** 3-Point Studio Setup: Key + Fill + Rim Kicker ($6500\,\text{K}$ cool backlight, $1.2\times$ intensity).

---

## 3. Detail Conservation Index (DCI) & Immutability Results

Isolated foreground ($DCI_{\text{fg}}$), background ($DCI_{\text{bg}}$), whole-image ($DCI_{\text{whole}}$), and 40% protected-mask zero-mutation measurements:

| Plate | Lighting Rig | Active Lights | Foreground DCI ($DCI_{\text{fg}}$) | Background DCI ($DCI_{\text{bg}}$) | Whole-Image DCI | Protected Zero-Mutation | Status |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **P1 Nike Sneaker** | 1 Light (Key) | 1 | **$0.9980$** | $0.9986$ | $0.9982$ | **$0.0000000000$** | **PASS** |
| **P1 Nike Sneaker** | 2 Lights (Key + Fill) | 2 | **$0.9966$** | $0.9948$ | $0.9957$ | **$0.0000000000$** | **PASS** |
| **P1 Nike Sneaker** | 3 Lights (Key + Fill + Rim) | 3 | **$0.9966$** | $0.9947$ | $0.9957$ | **$0.0000000000$** | **PASS** |
| **P2 Classical Statue** | 1 Light (Key) | 1 | **$0.9575$** | $0.9966$ | $0.9631$ | **$0.0000000000$** | **PASS** |
| **P2 Classical Statue** | 2 Lights (Key + Fill) | 2 | **$0.9641$** | $0.9972$ | $0.9688$ | **$0.0000000000$** | **PASS** |
| **P2 Classical Statue** | 3 Lights (Key + Fill + Rim) | 3 | **$0.9641$** | $0.9972$ | $0.9688$ | **$0.0000000000$** | **PASS** |
| **P3 Architectural Relief** | 1 Light (Key) | 1 | **$1.0000$** | $0.9998$ | $0.9999$ | **$0.0000000000$** | **PASS** |
| **P3 Architectural Relief** | 2 Lights (Key + Fill) | 2 | **$1.0000$** | $0.9998$ | $0.9999$ | **$0.0000000000$** | **PASS** |
| **P3 Architectural Relief** | 3 Lights (Key + Fill + Rim) | 3 | **$1.0000$** | $0.9998$ | $0.9999$ | **$0.0000000000$** | **PASS** |

### Acceptance Criteria Compliance:
1. **Isolated Foreground DCI Gate:** Target $\ge 0.8800$.
   - **Achieved:** Minimum observed foreground DCI is **$0.9575$** (Plate P2, 1 Light); Plate P1 achieved **$0.9966 - 0.9980$**.
2. **Protected Region Immutability Gate:** Target $= 0.0000000000$.
   - **Achieved:** Exactly **$0.0000000000$** across all 9 evaluations (bitwise identical passthrough).

---

## 4. Visual Evidence & Artifacts

High-resolution visual diagnostic sheets containing:
`[Original Photograph | Relit Result | Composite Shadow Visibility]`
have been saved to disk:
- `metal2/benchmark_results/diagnostic_boards/P1_nike_sneaker_3light_board.png`
- `metal2/benchmark_results/diagnostic_boards/P2_classical_statue_3light_board.png`
- `metal2/benchmark_results/diagnostic_boards/P3_architectural_relief_3light_board.png`

Detailed numerical JSON output: `metal2/benchmark_results/photographic_fidelity_results.json`.

---

## 5. Conclusion & Gate Sign-off

Phase 6 is complete and validated. Multi-light additive illumination preserves photographic detail with foreground $DCI > 0.95$ across all plates and exact bitwise zero-mutation. Proceeding to **Phase 7: Radiometric & Energy Validation**.
