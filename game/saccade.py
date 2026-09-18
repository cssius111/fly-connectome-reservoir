"""Bounded heading pulses, a game actuator inspired by flight saccades.

Spontaneous events are seeded tonic physics. ALERT/ESCAPE events require an
Action from the neural policy; this module has no retinal or threat geometry.
Timing and amplitudes are game conventions, not measured MaleCNS dynamics.
"""
from __future__ import annotations
import math
import numpy as np
from .action import Action


class Saccades:
    def __init__(self, config: dict, seed: int):
        self.config = config
        self.enabled = bool(config["enabled"])
        self.reset(seed)

    def reset(self, seed: int) -> None:
        # Independent stream: adding course changes never resamples tonic drift.
        self.rng = np.random.default_rng(seed + 3907)
        self.kind = "NONE"
        self.angle = self.elapsed = self.duration = 0.0
        self.wait = self._interval()
        self.last_delta = 0.0

    def _interval(self) -> float:
        return float(self.rng.uniform(self.config["interval_min_seconds"],
                                      self.config["interval_max_seconds"]))

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed) if self.kind != "NONE" else 0.0

    def _start(self, kind: str, angle: float, duration: float) -> None:
        self.kind, self.angle, self.duration, self.elapsed = kind, angle, duration, 0.0

    def step(self, dt: float, action: Action, near_wall: bool = False) -> float:
        self.last_delta = 0.0
        if not self.enabled:
            return 0.0
        if self.remaining <= 1e-12:
            self.kind = "NONE"
        if near_wall and self.kind == "SPONTANEOUS":
            self.kind = "NONE"  # arena safety owns spontaneous exploration
            self.wait = self._interval()
        c = self.config
        if (action.saccade and action.escape and action.strength > 0
                and self.kind != "ESCAPE"):
            # An emergency may pre-empt a weaker pulse. It never changes
            # position or instantly sets heading, even when its side changes.
            self._start("ESCAPE", math.radians(c["escape_max_degrees"]) * action.saccade,
                        c["escape_seconds"])
            self.wait = self._interval()
        elif action.saccade and not action.escape and self.kind == "NONE":
            self._start("ALERT", math.radians(c["alert_max_degrees"]) * action.saccade,
                        c["alert_seconds"])
            self.wait = self._interval()
        elif self.kind == "NONE":
            # Neural steering wins over a spontaneous turn. No threat-bearing
            # shortcut: the actuator sees only the action and arena-wall flag.
            calm = not action.escape and abs(action.turn) < 0.03
            if calm and not near_wall:
                self.wait -= dt
                if self.wait <= 0:
                    angle = math.radians(float(self.rng.uniform(c["spontaneous_min_degrees"],
                                                               c["spontaneous_max_degrees"])))
                    angle *= float(self.rng.choice((-1, 1)))
                    self._start("SPONTANEOUS", angle, c["spontaneous_seconds"])
                    self.wait = self._interval()
        if self.kind != "NONE":
            before = min(1.0, self.elapsed / self.duration)
            self.elapsed = min(self.duration, self.elapsed + dt)
            after = self.elapsed / self.duration
            # Integral of a half-sine angular-velocity pulse; zero yaw rate at
            # each endpoint, finite duration, exact bounded requested angle.
            self.last_delta = self.angle * (math.cos(math.pi * before) - math.cos(math.pi * after)) / 2
        return self.last_delta
