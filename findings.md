# Findings & Discoveries: Relight Studio Architecture

## Key Discoveries from v4
1. **Polar Placement is Ergonomically Superior:**
   Photographers think in clock dial (azimuth $0^\circ = \text{top}$, $90^\circ = \text{right}$) and elevation ($-90^\circ$ back to $+90^\circ$ front).
2. **Silhouette Normal Bending Works:**
   Distance-transform gradient $\nabla d$ points inward; outward vector $-\nabla d$ successfully bends $N_z \to 0$ at the silhouette, making rim lighting possible.
3. **Masked Guided Filter Prevents Halos:**
   Normalizing partitions $m$ and $1 - m$ independently prevents ratio bleeding.
4. **V4 Remaining Bottlenecks (Opportunities for v5):**
   - **Static Assumption of $S_{\text{old}}$:** v4 assumes original light was flat directional or uniform ambient. In real photos with baked directional light (e.g. sunlight from upper-left), changing light to upper-right fights the existing shadows. Estimating the original light vector enables shadow neutralization.
   - **Uniform Material Gloss:** In v4, gloss is a single scalar per image unless an external map is provided. Natural objects have mixed materials (e.g., shoe has matte mesh, satin leather, glossy plastic swoosh, rubber sole). We can infer spatially-varying roughness and specular reflectance directly from high-frequency texture variance and chromatic saturation.
   - **Micro-Relief Angle Invariance:** In v4, micro-detail $Y_d$ is scaled only by $R^\lambda$. Real physical micro-relief casts raking micro-shadows when light is grazing ($N \cdot L \to 0$).
   - **Crevice Ambient Occlusion:** Deep recesses (grooves in soles, eye sockets in statues) should be dark even when soft diffuse fill is applied.

