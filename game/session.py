"""Fixed-timestep engine wiring world -> perception -> brain -> world.

Kept separate from `app.py` so the whole closed loop runs headless: the
determinism test and `tools/calibrate_escape.py` drive a `Session` with a
recorded input sequence and no pygame at all.

Tick order, once per fixed 20 ms step:

    pointer in  ->  world.set_pointer / request_strike   (mouse stops here)
                ->  RetinaProjector.project(world)       (world -> Retina)
                ->  FlyLoop.step(retina)                 (Retina -> Action)
                ->  world.tick(dt, action)               (physics, collision)

The fly therefore acts on what it saw at the start of the tick, a one-tick
sensorimotor delay.
"""
from __future__ import annotations

import json
import hashlib
import importlib.metadata
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .action import Action, FixedEscapePolicy, Policy
from .fly import ROOT, FlyLoop, build_brain
from .perception import LOOM_TYPES, THREAT_TYPES, Retina, RetinaProjector, RetinalEncoder
from .world import TickEvents, World

CONFIG_PATH = ROOT / "game_config.json"


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def calibration_provenance(config: dict) -> dict:
    """Fingerprint actual in-memory configuration, including custom mutations.

    Canonical JSON avoids OS newline/formatting differences. Calibration also
    retains its raw config file hash for auditing. Schema 2 rejects older
    measurements whose fly could wander.
    """
    serialized = json.dumps(config, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True, allow_nan=False).encode("utf-8")
    return {"schema_version": 2, "measurement_protocol": "fixed-fly-v2",
            "config_hash_format": "canonical-json-sort-keys-ascii-compact",
            "game_config_sha256": hashlib.sha256(serialized).hexdigest(),
            "flybrain_version": importlib.metadata.version("flybrain"),
            "encoder_population_rule": "min-per-type-per-side-v1",
            "encoder_seed": config["encoder"]["encoder_seed"],
            "encoder_types": {"loom": list(LOOM_TYPES), "threat": list(THREAT_TYPES)},
            "sensory_input": config["brain"]["sensory_input"],
            "tick_seconds": config["sim"]["tick_seconds"],
            "brain_dt_seconds": config["brain"]["dt_seconds"]}


@dataclass(frozen=True)
class ThresholdSource:
    threshold: float
    origin: str


def resolve_escape_threshold(config: dict, root: Path = ROOT) -> ThresholdSource:
    """Use the first matching record, never merely the first existing file."""
    policy = config["policy"]
    command = "python tools/calibrate_escape.py --trials 28"
    if policy.get("escape_threshold") is not None:
        raise ValueError("Manual escape_threshold is unsupported; set it to null. Run: " + command)
    expected = calibration_provenance(config)
    tried = []
    for rel in policy["calibration_paths"]:
        path = root / rel
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("calibration record must be a JSON object")
            if data.get("provenance") != expected:
                tried.append(f"{rel}: provenance mismatch")
                continue
            threshold = float(data["escape_threshold"])
            if not math.isfinite(threshold) or threshold <= 0.0:
                tried.append(f"{rel}: invalid threshold")
                continue
            return ThresholdSource(threshold, str(rel))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            tried.append(f"{rel}: {type(exc).__name__}")
    raise ValueError("No matching escape-threshold calibration. " + "; ".join(tried)
                     + ". Run: " + command
                     + " (add --config PATH when using a custom game config).")


def build_policy(config: dict, root: Path = ROOT) -> tuple[FixedEscapePolicy, ThresholdSource]:
    source = resolve_escape_threshold(config, root)
    p = config["policy"]
    policy = FixedEscapePolicy(threshold=source.threshold,
                               refractory_seconds=float(p["refractory_seconds"]),
                               tick_seconds=float(config["sim"]["tick_seconds"]),
                               forward_bias=float(config["fly"]["escape_forward_bias"]),
                               turn_gain=float(p["turn_gain"]))
    return policy, source


class Session:
    """One playable run. Deterministic for a fixed seed and input sequence."""

    def __init__(self, config: dict, brain=None, policy: Policy | None = None,
                 root: Path = ROOT, seed: int | None = None):
        self.config = config
        self.root = root
        self.tick_seconds = float(config["sim"]["tick_seconds"])
        self.seed = int(config["sim"]["seed"] if seed is None else seed)
        if not math.isclose(self.tick_seconds, float(config["brain"]["dt_seconds"]),
                            rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("sim.tick_seconds must equal brain.dt_seconds")
        # Validate before loading the graph. A caller-supplied policy, including
        # calibration's RecordingPolicy, consumes no escape calibration.
        if policy is None:
            policy, self.threshold_source = build_policy(config, root)
        else:
            self.threshold_source = None
        self.policy = policy
        self.brain = brain if brain is not None else build_brain(config, root)
        self.encoder = RetinalEncoder(self.brain, config)
        self.fly_loop = FlyLoop(self.brain, self.encoder, policy, config)
        self.projector = RetinaProjector(self.tick_seconds)
        self.world = World(config, self.seed)
        self.last_retina: Retina | None = None
        self.ticks = 0
        self.reset(self.seed)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = int(seed)
        self.world.reset(self.seed)
        self.projector.reset()
        # Offset so the neuronal noise stream is not the same stream as the
        # world's wander stream.
        self.fly_loop.reset(self.seed + 977)
        self.last_retina = None
        self.ticks = 0

    def tick(self, pointer: tuple[float, float] | None = None, strike: bool = False) -> TickEvents:
        if pointer is not None:
            self.world.set_pointer(pointer[0], pointer[1])
        started = self.world.request_strike() if strike else False
        retina = self.projector.project(self.world)
        self.last_retina = retina
        action = self.fly_loop.step(retina) if self.world.fly.alive else Action()
        events = self.world.tick(self.tick_seconds, action)
        self.ticks += 1
        return TickEvents(started, events.strike_resolved, events.hit, events.escaped)

    @property
    def stats(self):
        return self.world.stats

    @property
    def policy_diagnostics(self) -> dict[str, float]:
        """Optional display metadata; never part of policy decisions."""
        provider = getattr(self.policy, "diagnostics", None)
        return dict(provider()) if callable(provider) else {}

    def state_vector(self) -> np.ndarray:
        """World state plus the motor readout, for the determinism test."""
        motor = self.fly_loop.last_motor
        neural = np.array([0.0, 0.0, 0.0, 0.0] if motor is None else
                          [motor.dnp01_left, motor.dnp01_right,
                           motor.dna02_left, motor.dna02_right], dtype=np.float64)
        retina = self.last_retina
        r = np.array([0.0, 0.0, 0.0] if retina is None else
                     [retina.theta, retina.theta_dot, retina.azimuth], dtype=np.float64)
        return np.concatenate([self.world.state_vector(), neural, r])
