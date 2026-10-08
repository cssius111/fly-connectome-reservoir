"""Strict local ecological observations; no source, object identity or world pose."""
from dataclasses import dataclass, fields
import math


@dataclass(frozen=True, slots=True)
class EcologicalSense:
    odor: float = 0.0
    odor_rate: float = 0.0
    odor_bilateral: float = 0.0  # right minus left concentration
    wind_forward: float = 0.0  # ambient flow velocity resolved in body axes
    wind_lateral: float = 0.0
    visual_left: float = 0.0  # local obstacle angular occupancy, not a vector
    visual_right: float = 0.0
    visual_front: float = 0.0
    visual_contrast: float = 0.0
    landing_affordance: float = 0.0
    surface_expansion: float = 0.0

    def __post_init__(self):
        if not all(math.isfinite(getattr(self, f.name)) for f in fields(EcologicalSense)):
            raise ValueError('ecological observations must be finite')
        if self.odor < 0:
            raise ValueError('odor concentration must be nonnegative')
        for name in ('visual_left', 'visual_right', 'visual_front', 'visual_contrast', 'landing_affordance'):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(name + ' must be in [0,1]')
