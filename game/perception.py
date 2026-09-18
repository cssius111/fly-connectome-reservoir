"""World -> retina -> neuron drive.

Two stages, deliberately separated:

1. `RetinaProjector` looks at the world (it may see the swatter and the fly)
   and reduces it to a frozen `Retina`: three scalars an eye could actually
   extract. This is the bottleneck. `Retina` carries no position, no mouse, no
   swatter phase, no velocity -- so raw coordinates *cannot* travel downstream,
   rather than merely being left unused by convention.

2. `RetinalEncoder` turns a `Retina` into `brain.step(inject=...)` pairs via
   `flybrain.FeatureDetectors`, driving LPLC2 (looming) and LC4 (fast looming
   at close range). The mapping is a pure function of the `Retina`: the encoder
   keeps no cross-call state that can influence the result, which is what makes
   "equal retina -> identical injection" testable.

Both LC4 and LPLC2 are asymmetric in MaleCNS (LC4: 71 left vs 55 right; LPLC2:
94 vs 91). Left as-is that would bias which way the fly escapes, so each
channel is subsampled to min(left, right) using a fixed encoder seed -- the
same balancing rule PROTOCOL.md uses for the reservoir experiment.

Photoreceptor caveat: this shortcuts the lamina and drives visual projection
neurons directly, exactly as upstream's own `flybrain/eyes.py` docstring
describes. There is no eye model here. Everything downstream of LC4/LPLC2 is
the connectome.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from flybrain import FeatureDetectors

if TYPE_CHECKING:  # pragma: no cover
    from .world import World

# Channels the swatter game drives, and the cell types behind them.
LOOM_TYPES = ["LPLC2"]
THREAT_TYPES = ["LC4"]


@dataclass(frozen=True, slots=True)
class Retina:
    """Everything the fly is ever told about the outside world.

    theta      angular subtense of the swatter, radians
    theta_dot  rate of change of theta, radians/second (>0 = looming)
    azimuth    bearing relative to the fly's own heading, -1 = hard left,
               0 = straight ahead, +1 = hard right (i.e. bearing / pi)

    Frozen and slotted on purpose: no caller can staple a mouse coordinate on.
    """
    theta: float
    theta_dot: float
    azimuth: float

    @property
    def side(self) -> str:
        return "R" if self.azimuth >= 0.0 else "L"


class RetinaProjector:
    """World -> Retina. The last place in the fly's input path that may look at
    positions."""

    def __init__(self, tick_seconds: float):
        self.tick_seconds = float(tick_seconds)
        self._previous_theta: float | None = None

    def reset(self) -> None:
        self._previous_theta = None

    def project(self, world: "World") -> Retina:
        fly, sw = world.fly, world.swatter
        dx, dy = sw.x - fly.x, sw.y - fly.y
        distance = math.sqrt(dx * dx + dy * dy + sw.height * sw.height)
        theta = 2.0 * math.atan(world.visual_half_size / max(distance, 1e-6))
        previous = theta if self._previous_theta is None else self._previous_theta
        self._previous_theta = theta
        theta_dot = (theta - previous) / self.tick_seconds

        # Bearing in the fly's own frame: +x_body is its heading, +y_body its right.
        hx, hy = math.cos(fly.heading), math.sin(fly.heading)
        forward = dx * hx + dy * hy
        rightward = dx * -hy + dy * hx
        azimuth = math.atan2(rightward, forward) / math.pi
        return Retina(theta=theta, theta_dot=theta_dot, azimuth=azimuth)


class RetinalEncoder:
    """Retina -> (neuron indices, voltage) pairs for `brain.step(inject=...)`."""

    def __init__(self, brain, config: dict):
        enc = config["encoder"]
        self.tick_seconds = float(config["sim"]["tick_seconds"])
        self.virtual_distance = float(enc["virtual_distance"])
        self.threat_theta_reference = float(enc["threat_theta_reference"])
        self.threat_theta_dot_reference = float(enc["threat_theta_dot_reference"])
        # chase (LC10a) is off: the fly is not courting the swatter, and the
        # 'shot' channel has nothing to fire at.
        self._fd = FeatureDetectors(brain,
                                    loom_gain=enc["loom_gain"],
                                    loom_size=enc["loom_size"],
                                    threat_max=enc["threat_max"],
                                    chase_base=0.0,
                                    chase_gain=0.0,
                                    cap=enc["cap"])
        self._balance_populations(brain, int(enc["encoder_seed"]))

    def _balance_populations(self, brain, encoder_seed: int) -> None:
        """Subsample each driven channel to min(left, right) so neither side of
        the brain gets more input current than the other."""
        rng = np.random.default_rng(encoder_seed)
        self.population = {}
        for channel, types in (("loom", LOOM_TYPES), ("threat", THREAT_TYPES)):
            pools = [brain.cells(types, side) for side in ("L", "R")]
            n = min(len(pools[0]), len(pools[1]))
            if n == 0:
                raise RuntimeError(f"no {types} cells on one side; cannot balance {channel}")
            chosen = {}
            for i, side in enumerate(("L", "R")):
                chosen[side] = np.sort(rng.choice(pools[i], n, replace=False)).astype(np.int64)
            self._fd.cells[channel] = chosen
            self.population[channel] = {"types": list(types), "available_L": len(pools[0]),
                                        "available_R": len(pools[1]), "used_per_side": n}

    def threat_level(self, retina: Retina) -> float:
        """LC4 drive: fast looming *at close range*, so the product of a size
        term and an expansion term. Derived from the retina alone -- the strike
        phase is never passed in."""
        size = min(1.0, max(0.0, retina.theta / self.threat_theta_reference))
        growth = min(1.0, max(0.0, retina.theta_dot / self.threat_theta_dot_reference))
        return size * growth

    def inject(self, retina: Retina) -> list:
        if type(retina) is not Retina:
            raise TypeError(f"RetinalEncoder.inject accepts only Retina, got {type(retina).__name__}")
        growth = max(0.0, retina.theta_dot) * self.tick_seconds
        # FeatureDetectors differences successive calls to get angular growth.
        # Seeding its memory from this retina makes inject() a pure function of
        # the retina instead of depending on call history.
        self._fd.previous = {"opp": retina.theta - growth}
        signed_distance = self.virtual_distance if retina.side == "R" else -self.virtual_distance
        return self._fd.inject(opp=(signed_distance, retina.theta * self.virtual_distance),
                               threat=self.threat_level(retina))

    @property
    def last_drive(self) -> dict:
        """Per-channel voltage from the most recent `inject`, for the HUD."""
        return dict(self._fd.last)
