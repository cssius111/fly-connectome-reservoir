"""World -> retina -> neuron drive.

Two stages, deliberately separated:

1. `RetinaProjector` looks at the world (it may see the swatter and the fly)
   and reduces it to a frozen `Retina`: four scalars an eye could actually
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
   - `retinotopic_v1` (M3.4, game/M3_4_RETINOTOPIC_DRIVE_DESIGN.md): the same
     Ache et al. 2019 terms, given to each LPLC2 and LC4 cell in proportion to
     the fraction of its MaleCNS receptive field the swatter's disk covers, seen
     through each column's Gaussian acceptance function. LPLC2 is driven only
     while the image edge expands at least as fast as the standard LPLC2 looming
     stimulus (Klapoetke et al. 2017). The receptive fields come from
     `data/receptive_fields_v1.npz`, built by tools/build_receptive_fields.py and
     verified by a content digest.

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

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
import re
from typing import TYPE_CHECKING

import numpy as np
from flybrain import FeatureDetectors

if TYPE_CHECKING:  # pragma: no cover
    from .world import World

# Channels the swatter game drives, and the cell types behind them.
LOOM_TYPES = ["LPLC2"]
THREAT_TYPES = ["LC4"]

ROOT = Path(__file__).resolve().parent.parent
FEATURE_MODEL_LEGACY = "legacy_v0"
FEATURE_MODEL_ACHE2019 = "ache2019_v1"
FEATURE_MODEL_RETINOTOPIC = "retinotopic_v1"
FEATURE_MODELS = (FEATURE_MODEL_LEGACY, FEATURE_MODEL_ACHE2019, FEATURE_MODEL_RETINOTOPIC)
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
RETINOTOPIC_CONFIG_KEYS = ("acceptance_fwhm_deg", "fields_file", "fields_sha256",
                           "lplc2_min_edge_speed_deg_s", "scale_volts_per_mv")
RETINOTOPIC_FIELD_KEYS = ("cell_body", "cell_index", "cell_side", "cell_type", "column_code",
                          "column_count", "column_direction", "column_offsets")
# Drives below this are numerically inert (the spike threshold is 1 V) and are not injected.
RETINOTOPIC_MIN_INJECTION_V = 1e-6


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


def _positive_number(value, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")


def encoder_feature_model(config: dict) -> str:
    """The configured feature model, validated together with its parameter block."""
    enc = config["encoder"]
    mode = enc.get("feature_model", FEATURE_MODEL_LEGACY)
    if mode not in FEATURE_MODELS:
        raise ValueError(f"unknown encoder.feature_model {mode!r}")
    block = enc.get("ache2019")
    retinotopic = enc.get("retinotopic")
    if mode != FEATURE_MODEL_ACHE2019 and block is not None:
        raise ValueError("encoder.ache2019 is used only by feature_model ache2019_v1")
    if mode != FEATURE_MODEL_RETINOTOPIC and retinotopic is not None:
        raise ValueError("encoder.retinotopic is used only by feature_model retinotopic_v1")
    if mode == FEATURE_MODEL_LEGACY:
        return mode
    if mode == FEATURE_MODEL_RETINOTOPIC:
        if not isinstance(retinotopic, dict) or tuple(sorted(retinotopic)) != RETINOTOPIC_CONFIG_KEYS:
            raise ValueError("encoder.retinotopic must hold exactly: " + ", ".join(RETINOTOPIC_CONFIG_KEYS))
        for key in ("scale_volts_per_mv", "acceptance_fwhm_deg", "lplc2_min_edge_speed_deg_s"):
            _positive_number(retinotopic[key], "encoder.retinotopic." + key)
        if not isinstance(retinotopic["fields_file"], str) or not retinotopic["fields_file"]:
            raise ValueError("encoder.retinotopic.fields_file must be a non-empty path")
        if not isinstance(retinotopic["fields_sha256"], str) \
                or not re.fullmatch(r"[0-9a-f]{64}", retinotopic["fields_sha256"]):
            raise ValueError("encoder.retinotopic.fields_sha256 must be a lowercase SHA256 hex digest")
        return mode
    if not isinstance(block, dict) or tuple(sorted(block)) != ACHE2019_CONFIG_KEYS:
        raise ValueError("encoder.ache2019 must hold exactly: " + ", ".join(ACHE2019_CONFIG_KEYS))
    _positive_number(block["scale_volts_per_mv"], "encoder.ache2019.scale_volts_per_mv")
    return mode


def fields_digest(fields) -> str:
    """Content SHA256 of a receptive-field table: key, dtype, shape and bytes of every array.

    Independent of the zip container's timestamps, so a rebuild from the same
    sources reproduces it exactly.
    """
    h = hashlib.sha256()
    for key in sorted(fields):
        a = np.ascontiguousarray(fields[key])
        h.update(key.encode("ascii") + b"\0" + a.dtype.str.encode("ascii") + b"\0"
                 + repr(a.shape).encode("ascii") + b"\0")
        h.update(a.tobytes())
    return h.hexdigest()


def load_receptive_fields(path: Path, expected_sha256: str) -> dict:
    """The receptive-field table, refused unless its content digest is the configured one."""
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; build it with tools/build_receptive_fields.py")
    with np.load(path, allow_pickle=False) as z:
        if tuple(sorted(z.files)) != RETINOTOPIC_FIELD_KEYS:
            raise ValueError(f"{path} must hold exactly: " + ", ".join(RETINOTOPIC_FIELD_KEYS))
        fields = {key: z[key] for key in z.files}
    digest = fields_digest(fields)
    if digest != expected_sha256:
        raise ValueError(f"{path} content digest {digest} differs from encoder.retinotopic.fields_sha256")
    return fields


def view_direction(azimuth_rad: float, elevation_rad: float) -> np.ndarray:
    """Unit vector in the head frame of the eye map: +x forward, +y right, +z up."""
    ce = math.cos(elevation_rad)
    return np.array([ce * math.cos(azimuth_rad), ce * math.sin(azimuth_rad), math.sin(elevation_rad)])


@dataclass(frozen=True, slots=True)
class Retina:
    """Everything the fly is ever told about the outside world.

    theta      angular subtense of the swatter, radians
    theta_dot  rate of change of theta, radians/second (>0 = looming)
    azimuth    bearing relative to the fly's own heading, -1 = hard left,
               0 = straight ahead, +1 = hard right (i.e. bearing / pi)
    elevation  angle of the swatter's centre above the fly's horizontal plane,
               radians (M3.4; 0.0 = on the horizon, the default for synthetic
               stimuli). Only `retinotopic_v1` reads it.

    Frozen and slotted on purpose: no caller can staple a mouse coordinate on.
    """
    theta: float
    theta_dot: float
    azimuth: float
    elevation: float = 0.0

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
        elevation = math.atan2(sw.height, math.sqrt(dx * dx + dy * dy))
        return Retina(theta=theta, theta_dot=theta_dot, azimuth=azimuth, elevation=elevation)


class RetinalEncoder:
    """Retina -> (neuron indices, voltage) pairs for `brain.step(inject=...)`."""

    def __init__(self, brain, config: dict, root: Path = ROOT):
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
        self._retinotopic = None
        if self.feature_model == FEATURE_MODEL_RETINOTOPIC:
            with np.load(Path(root) / config["brain"]["data"] / "brain.npz") as meta:
                body_ids = meta["ids"]
            self._retinotopic = RetinotopicDrive(brain, body_ids, self._fd.cells, enc["retinotopic"],
                                                 self.cap, root)

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
        if self.feature_model == FEATURE_MODEL_RETINOTOPIC:
            inject, self._fd.last = self._retinotopic.inject(retina)
            return inject
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
        """Per-channel voltage from the most recent `inject`, for the HUD. Under
        `retinotopic_v1` it is the largest per-cell voltage of each channel and side."""
        return dict(self._fd.last)


class RetinotopicDrive:
    """The M3.4 `retinotopic_v1` mapping (game/M3_4_RETINOTOPIC_DRIVE_DESIGN.md, section 2.3).

    Each driven cell i gets min(cap, scale * F(Retina) * c_i), where F is the Ache
    et al. 2019 term of its type in mV and c_i the fraction of its column-weighted
    receptive field inside the swatter's disk. Column c contributes
    w_ic * Phi((theta/2 - alpha_c) / sigma): alpha_c is the angle between the
    column's viewing direction and the disk centre, and sigma follows from the
    columns' Gaussian acceptance angle. LPLC2 is driven only while the image edge
    expands at theta_dot / 2 >= lplc2_min_edge_speed_deg_s. A disk drives the
    cells of whichever eye it covers; the Retina.side rule is not used.
    """

    def __init__(self, brain, body_ids, cells: dict, block: dict, cap: float, root: Path):
        from scipy.special import ndtr
        self._ndtr = ndtr
        fields = load_receptive_fields(Path(root) / block["fields_file"], block["fields_sha256"])
        self.scale = float(block["scale_volts_per_mv"])
        self.sigma_deg = float(block["acceptance_fwhm_deg"]) / (2.0 * math.sqrt(2.0 * math.log(2.0)))
        self.min_edge_speed_deg_s = float(block["lplc2_min_edge_speed_deg_s"])
        self.cap = float(cap)
        position = {int(i): k for k, i in enumerate(fields["cell_index"])}
        self.channels = {}
        for channel, types in (("loom", LOOM_TYPES), ("threat", THREAT_TYPES)):
            index, side, dirs, weights, owner = [], [], [], [], []
            for s in ("L", "R"):
                for cell in cells[channel][s]:
                    k = position.get(int(cell))
                    if k is None:
                        raise ValueError(f"receptive-field table has no {channel} cell {int(cell)}")
                    if int(fields["cell_body"][k]) != int(body_ids[int(cell)]) \
                            or str(fields["cell_type"][k]) not in types or str(fields["cell_side"][k]) != s \
                            or str(brain.cell_type[int(cell)]) not in types or str(brain.side[int(cell)]) != s:
                        raise ValueError(f"receptive-field table does not match brain cell {int(cell)}")
                    lo, hi = int(fields["column_offsets"][k]), int(fields["column_offsets"][k + 1])
                    counts = fields["column_count"][lo:hi].astype(np.float64)
                    if hi <= lo or counts.sum() <= 0:
                        raise ValueError(f"receptive-field table has no columns for cell {int(cell)}")
                    dirs.append(fields["column_direction"][lo:hi].astype(np.float64))
                    weights.append(counts / counts.sum())
                    owner.append(np.full(hi - lo, len(index)))
                    index.append(int(cell))
                    side.append(s)
            self.channels[channel] = {
                "index": np.array(index, np.int64), "side": np.array(side),
                "directions": np.concatenate(dirs), "weights": np.concatenate(weights),
                "owner": np.concatenate(owner).astype(np.int64)}

    def coverage(self, channel: str, centre: np.ndarray, theta_deg: float) -> np.ndarray:
        """c_i for every driven cell of the channel, in the order of `channels[channel]['index']`."""
        ch = self.channels[channel]
        alpha = np.degrees(np.arccos(np.clip(ch["directions"] @ centre, -1.0, 1.0)))
        share = ch["weights"] * self._ndtr((0.5 * theta_deg - alpha) / self.sigma_deg)
        return np.bincount(ch["owner"], weights=share, minlength=len(ch["index"]))

    def inject(self, retina: Retina) -> tuple[list, dict]:
        last = {key: 0.0 for key in ("loomL", "loomR", "threatL", "threatR")}
        lplc2_mv, lc4_mv = ache2019_drive_mv(retina)
        if 0.5 * math.degrees(retina.theta_dot) < self.min_edge_speed_deg_s:
            lplc2_mv = 0.0
        inject = []
        if lplc2_mv <= 0.0 and lc4_mv <= 0.0:
            return inject, last
        centre = view_direction(math.pi * retina.azimuth, retina.elevation)
        theta_deg = math.degrees(retina.theta)
        for channel, mv in (("loom", lplc2_mv), ("threat", lc4_mv)):
            if mv <= 0.0:
                continue
            ch = self.channels[channel]
            amount = np.minimum(self.cap, self.scale * mv * self.coverage(channel, centre, theta_deg))
            amount = amount.astype(np.float32)
            live = amount >= RETINOTOPIC_MIN_INJECTION_V
            for value in np.unique(amount[live]):
                inject.append((ch["index"][live & (amount == value)], np.float32(value)))
            for s in ("L", "R"):
                on_side = live & (ch["side"] == s)
                last[channel + s] = float(amount[on_side].max()) if on_side.any() else 0.0
        return inject, last
