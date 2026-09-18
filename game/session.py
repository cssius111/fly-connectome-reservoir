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
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .action import Action, FixedEscapePolicy, Policy
from .fly import ROOT, FlyLoop, build_brain
from .perception import Retina, RetinaProjector, RetinalEncoder
from .world import TickEvents, World

CONFIG_PATH = ROOT / "game_config.json"


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ThresholdSource:
    threshold: float
    origin: str


def resolve_escape_threshold(config: dict, root: Path = ROOT) -> ThresholdSource:
    """The escape threshold must be traceable to a recorded calibration run.

    An explicit `policy.escape_threshold` in game_config.json wins (handy for
    tests), otherwise the first existing file in `policy.calibration_paths` is
    used. If none exists we refuse to guess.
    """
    policy = config["policy"]
    explicit = policy.get("escape_threshold")
    if explicit is not None:
        return ThresholdSource(float(explicit), "game_config.json:policy.escape_threshold")
    tried = []
    for rel in policy["calibration_paths"]:
        path = root / rel
        tried.append(str(rel))
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return ThresholdSource(float(data["escape_threshold"]), str(rel))
    raise FileNotFoundError(
        "No escape-threshold calibration found (looked in: " + ", ".join(tried) + "). "
        "Run:  python tools/calibrate_escape.py")


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
        self.brain = brain if brain is not None else build_brain(config, root)
        self.encoder = RetinalEncoder(self.brain, config)
        if policy is None:
            policy, self.threshold_source = build_policy(config, root)
        else:
            self.threshold_source = ThresholdSource(getattr(policy, "threshold", float("nan")),
                                                    "caller-supplied policy")
        self.policy = policy
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
