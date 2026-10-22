"""World -> retina -> neuron drive.

Two stages, deliberately separated:

1. `RetinaProjector` looks at the world (it may see the swatter and the fly)
   and reduces it to a frozen `Retina`: three scalars an eye could actually
   extract. This is the bottleneck. `Retina` carries no position, no mouse, no
   swatter phase, no velocity -- so raw coordinates *cannot* travel downstream,
   rather than merely being left unused by convention.

2. `RetinalEncoder` turns a `Retina` into `brain.step(inject=...)` pairs,
   driving LPLC2 and LC4. The mapping is a pure function of the `Retina`: the
   encoder keeps no cross-call state that can influence the result, which is
   what makes "equal retina -> identical injection" testable. Two feature
   models exist, selected by `encoder.feature_model`:
   - `legacy_v0` (the default when the key is absent), via
     `flybrain.FeatureDetectors`: LPLC2 by angular growth per tick, LC4 by the
     product of a size term and an expansion term.
   - `ache2019_v1` (M3.2, game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md): the
     giant-fiber input model of Ache et al. 2019 (Curr Biol 29:1073, STAR
     Methods eqs. 3, 4 and 7). LPLC2 carries a Gaussian of log angular size and
     LC4 a linear function of angular velocity, both only while the stimulus
     expands, scaled by one calibrated constant from GF millivolts to volts.

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

FEATURE_MODEL_LEGACY = "legacy_v0"
FEATURE_MODEL_ACHE2019 = "ache2019_v1"
# Ache et al. 2019, STAR Methods "GF Model". Angles in degrees, potentials in mV.
ACHE2019 = {
    "lc4_mv_per_deg_s": 0.0002567,     # eq. 3, C1
    "lplc2_peak_mv": 1.7,              # eq. 4, C2
    "lplc2_center_deg": 42.0,          # eq. 4, C3
    "lplc2_log_width": 0.52,           # eq. 4, C4
    "weight_lplc2": 1.45,              # eq. 7, W_LPLC2
    "weight_lc4": 1.62,                # eq. 7, W_LC4
}
ACHE2019_CONFIG_KEYS = ("scale_volts_per_mv",)


def ache2019_drive_mv(retina: "Retina") -> tuple[float, float]:
    """Weighted LPLC2 and LC4 inputs to the giant fiber in mV (eqs. 4 and 3, weights of eq. 7).

    Zero unless the stimulus expands: LPLC2 does not respond to receding or
    motion-free stimuli (Klapoetke et al. 2017), and the GF response to static
    disks does not depend on LPLC2 or LC4 (Ache et al. 2019). The paper's 19 ms
    sensory delays are carried by the network's own step from LPLC2/LC4 to DNp01.
    """
    if not retina.theta_dot > 0.0 or not retina.theta > 0.0:
        return 0.0, 0.0
    a = ACHE2019
    log_ratio = math.log(math.degrees(retina.theta) / a["lplc2_center_deg"])
    lplc2 = a["weight_lplc2"] * a["lplc2_peak_mv"] * math.exp(
        -log_ratio * log_ratio / (2.0 * a["lplc2_log_width"] ** 2))
    lc4 = a["weight_lc4"] * a["lc4_mv_per_deg_s"] * math.degrees(retina.theta_dot)
    return lplc2, lc4


def encoder_feature_model(config: dict) -> str:
    """The configured feature model, validated together with its parameter block."""
    enc = config["encoder"]
    mode = enc.get("feature_model", FEATURE_MODEL_LEGACY)
    if mode not in (FEATURE_MODEL_LEGACY, FEATURE_MODEL_ACHE2019):
        raise ValueError(f"unknown encoder.feature_model {mode!r}")
    block = enc.get("ache2019")
    if mode == FEATURE_MODEL_LEGACY:
        if block is not None:
            raise ValueError("encoder.ache2019 is used only by feature_model ache2019_v1")
        return mode
    if not isinstance(block, dict) or tuple(sorted(block)) != ACHE2019_CONFIG_KEYS:
        raise ValueError("encoder.ache2019 must hold exactly: " + ", ".join(ACHE2019_CONFIG_KEYS))
    scale = block["scale_volts_per_mv"]
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) \
            or not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("encoder.ache2019.scale_volts_per_mv must be a positive finite number")
    return mode


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
        self.feature_model = encoder_feature_model(config)
        self.ache2019_scale = (float(enc["ache2019"]["scale_volts_per_mv"])
                               if self.feature_model == FEATURE_MODEL_ACHE2019 else None)
        self.cap = float(enc["cap"])
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

    def sensory_spikes(self, fired) -> dict:
        """Analysis-only spike counts, distinct from injection-drive voltage."""
        return {label+suffix: int(np.isin(fired, self._fd.cells[channel][side]).sum())
                for channel,label in (("threat","LC4"),("loom","LPLC2"))
                for side,suffix in (("L","_left"),("R","_right"))}

    def threat_level(self, retina: Retina) -> float:
        """Legacy LC4 drive: fast looming *at close range*, so the product of a size
        term and an expansion term. Derived from the retina alone -- the strike
        phase is never passed in."""
        size = min(1.0, max(0.0, retina.theta / self.threat_theta_reference))
        growth = min(1.0, max(0.0, retina.theta_dot / self.threat_theta_dot_reference))
        return size * growth

    def inject(self, retina: Retina) -> list:
        if type(retina) is not Retina:
            raise TypeError(f"RetinalEncoder.inject accepts only Retina, got {type(retina).__name__}")
        if self.feature_model == FEATURE_MODEL_ACHE2019:
            return self._inject_ache2019(retina)
        growth = max(0.0, retina.theta_dot) * self.tick_seconds
        # FeatureDetectors differences successive calls to get angular growth.
        # Seeding its memory from this retina makes inject() a pure function of
        # the retina instead of depending on call history.
        self._fd.previous = {"opp": retina.theta - growth}
        signed_distance = self.virtual_distance if retina.side == "R" else -self.virtual_distance
        return self._fd.inject(opp=(signed_distance, retina.theta * self.virtual_distance),
                               threat=self.threat_level(retina))

    def _inject_ache2019(self, retina: Retina) -> list:
        """The M3.2 mapping. Same cells, side rule, key set and output form as legacy."""
        lplc2_mv, lc4_mv = ache2019_drive_mv(retina)
        drive = {key: np.float32(0.0) for key in self._fd.last}
        drive["loom" + retina.side] = np.float32(min(self.cap, self.ache2019_scale * lplc2_mv))
        drive["threat" + retina.side] = np.float32(min(self.cap, self.ache2019_scale * lc4_mv))
        self._fd.last = {key: float(amount) for key, amount in drive.items()}
        return [(self._fd.cells[key[:-1]][key[-1]], amount)
                for key, amount in drive.items() if amount > 0]

    @property
    def last_drive(self) -> dict:
        """Per-channel voltage from the most recent `inject`, for the HUD."""
        return dict(self._fd.last)
