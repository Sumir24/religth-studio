"""
Material Data Model & Profiles
Relight Studio — RS-SPIKE-3C.2
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import numpy as np


@dataclass
class MaterialData:
    """
    Physical material properties for microfacet BRDF shading.
    
    Attributes:
      id: Unique identifier for material
      name: Human-readable label
      base_color: Linear sRGB reflectance [r, g, b] in [0, 1]
      roughness: Linear perceptual roughness in [0, 1] (alpha = roughness^2)
      metallic: Conductor factor in [0, 1] (0 = dielectric, 1 = conductor)
      specular_f0: Normal-incidence reflectance for dielectrics (typically ~0.04)
      specular_intensity: Artistic multiplier on specular reflectance (default 1.0)
    """
    id: str = "mat_default"
    name: str = "Default Studio Dielectric"
    base_color: List[float] = field(default_factory=lambda: [0.80, 0.80, 0.80])
    roughness: float = 0.50
    metallic: float = 0.0
    specular_f0: float = 0.04
    specular_intensity: float = 1.0

    def validate(self) -> None:
        """Enforces physical parameter bounds and numerical sanity."""
        if not self.id:
            raise ValueError("Material ID cannot be empty.")
        if not (0.0 <= self.roughness <= 1.0):
            raise ValueError(f"Roughness must be in [0, 1], got {self.roughness}")
        if not (0.0 <= self.metallic <= 1.0):
            raise ValueError(f"Metallic factor must be in [0, 1], got {self.metallic}")
        if not (0.0 <= self.specular_f0 <= 1.0):
            raise ValueError(f"Specular F0 must be in [0, 1], got {self.specular_f0}")
        if self.specular_intensity < 0.0:
            raise ValueError(f"Specular intensity cannot be negative, got {self.specular_intensity}")
        if len(self.base_color) != 3:
            raise ValueError(f"Base color must be a 3-channel RGB vector, got {self.base_color}")
        for c in self.base_color:
            if not (0.0 <= c <= 2.0):  # Allow mild high-dynamic range or exposure headroom up to 2.0
                raise ValueError(f"Base color channel out of expected range [0, 2]: {self.base_color}")

    def get_effective_f0(self) -> np.ndarray:
        """
        Computes the effective normal-incidence specular reflectance vector:
          F0 = mix(specular_f0 * specular_intensity, base_color, metallic)
        """
        base = np.array(self.base_color, dtype=np.float32)
        dielectric_f0 = np.full(3, self.specular_f0 * self.specular_intensity, dtype=np.float32)
        return (1.0 - self.metallic) * dielectric_f0 + self.metallic * base

    def get_effective_diffuse_albedo(self) -> np.ndarray:
        """
        Computes the effective diffuse albedo:
          albedo_diffuse = base_color * (1.0 - metallic)
        Conductors have 0 diffuse reflection.
        """
        base = np.array(self.base_color, dtype=np.float32)
        return base * (1.0 - self.metallic)

    # --------------------------------------------------------------------------
    # Material Profile Factories
    # --------------------------------------------------------------------------
    @classmethod
    def fabric(
        cls,
        mat_id: str = "mat_fabric",
        name: str = "Woven Fabric",
        base_color: Optional[List[float]] = None
    ) -> "MaterialData":
        """Fabric / Canvas: High roughness, zero metallic, low specular sheen."""
        return cls(
            id=mat_id,
            name=name,
            base_color=base_color or [0.75, 0.75, 0.78],
            roughness=0.85,
            metallic=0.0,
            specular_f0=0.03,
            specular_intensity=0.5
        )

    @classmethod
    def marble(
        cls,
        mat_id: str = "mat_marble",
        name: str = "Honed Marble",
        base_color: Optional[List[float]] = None
    ) -> "MaterialData":
        """Marble / Polished Stone: Medium roughness, subtle specular highlights."""
        return cls(
            id=mat_id,
            name=name,
            base_color=base_color or [0.85, 0.84, 0.82],
            roughness=0.35,
            metallic=0.0,
            specular_f0=0.045,
            specular_intensity=1.0
        )

    @classmethod
    def plastic(
        cls,
        mat_id: str = "mat_plastic",
        name: str = "Molded Polymer / Plastic",
        base_color: Optional[List[float]] = None
    ) -> "MaterialData":
        """Smooth Plastic / Rubber: Smooth glossy highlights, achromatic dielectric reflection."""
        return cls(
            id=mat_id,
            name=name,
            base_color=base_color or [0.80, 0.20, 0.20],
            roughness=0.22,
            metallic=0.0,
            specular_f0=0.04,
            specular_intensity=1.0
        )

    @classmethod
    def rough_metal(
        cls,
        mat_id: str = "mat_rough_metal",
        name: str = "Brushed Metal",
        base_color: Optional[List[float]] = None
    ) -> "MaterialData":
        """Brushed Aluminum / Steel: Metallic=1.0, broad tinted specular lobes."""
        return cls(
            id=mat_id,
            name=name,
            base_color=base_color or [0.91, 0.92, 0.92],
            roughness=0.45,
            metallic=1.0,
            specular_f0=0.04,
            specular_intensity=1.0
        )

    @classmethod
    def polished_metal(
        cls,
        mat_id: str = "mat_polished_metal",
        name: str = "Polished Chrome / Gold",
        base_color: Optional[List[float]] = None
    ) -> "MaterialData":
        """Mirror / Polished Metal: Very low roughness, 100% specular reflectance."""
        return cls(
            id=mat_id,
            name=name,
            base_color=base_color or [1.00, 0.76, 0.33],  # Gold tint default
            roughness=0.08,
            metallic=1.0,
            specular_f0=0.04,
            specular_intensity=1.0
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MaterialData":
        return cls(
            id=data.get("id", "mat_default"),
            name=data.get("name", "Default Material"),
            base_color=list(data.get("base_color", [0.80, 0.80, 0.80])),
            roughness=float(data.get("roughness", 0.50)),
            metallic=float(data.get("metallic", 0.0)),
            specular_f0=float(data.get("specular_f0", 0.04)),
            specular_intensity=float(data.get("specular_intensity", 1.0))
        )
