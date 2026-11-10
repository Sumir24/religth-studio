# RELIGHT STUDIO — RS-PRODUCT-1.1 INTERACTION SEQUENCE LOG

Evidence that 3D gizmo manipulation directly mutates scene state and produces immediate photographic response.

| Step | User Action | Target | World Coordinates / Values | Mean Photograph Luma | Status |
|---|---|---|---|---|---|
| 1 | Select Light 01 | light_01 | `[1.2, 1.8, 1.5]` | 0.2022 | **BASELINE** |
| 2 | Gizmo Drag along X axis (+80px screen) | light_01 | `[1.348, 1.8, 1.5]` | 0.2014 | **VERIFIED** |
| 3 | Gizmo Drag along Y axis (-70px screen upward) | light_01 | `[1.348, 1.909, 1.5]` | 0.2010 | **VERIFIED** |
| 4 | Gizmo Drag along Z axis (+60px screen) | light_01 | `[1.348, 1.909, 1.368]` | 0.2011 | **VERIFIED** |
| 5 | Rotate Light Pitch & Yaw | light_01 | `[-50.0, 5.0, 0.0]` | 0.2007 | **VERIFIED** |
| 6 | Resize Area Light Dimensions | light_01 | `w=1.0, h=1.0` | 0.2110 | **VERIFIED** |
