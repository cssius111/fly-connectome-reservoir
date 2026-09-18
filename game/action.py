"""Descending-neuron activity -> body-frame motor command.

The boundary that keeps Milestone 2 cheap: everything upstream produces a
`MotorState`, everything downstream consumes an `Action`. A trained policy is a
drop-in replacement for `FixedEscapePolicy` -- same `Policy` protocol, same two
dataclasses, no changes to world/perception/app.

Milestone 1 deliberately trains nothing. `FixedEscapePolicy` is a threshold on
DNp01 (the looming-escape descending neuron, `brain.groups["escape_L"/"escape_R"]`)
whose value comes from a recorded calibration run, never from hand-picking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping, Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True, slots=True)
class MotorState:
    """What the readout sees. `trace` is the full decaying descending-neuron
    trace, carried so a Milestone-2 trained policy has something to fit without
    changing this interface."""
    dnp01_left: float
    dnp01_right: float
    dna02_left: float
    dna02_right: float
    trace: np.ndarray = field(repr=False)

    @property
    def dnp01_total(self) -> float:
        return self.dnp01_left + self.dnp01_right


@dataclass(frozen=True, slots=True)
class Action:
    """Body-frame command: lateral/forward specify direction, not magnitude.

    +lateral is the fly's right; +forward follows its heading. The world
    normalizes this direction and applies escape_impulse * strength, before
    damping/speed limits. A zero direction or strength produces no impulse.
    strength is finite and in [0, 1]; invalid commands raise ValueError.
    turn is separate, scaled by the world's turn_rate (radians/second).
    strength defaults to 1 for existing full-escape callers and is ignored
    when escape=False.
    """
    escape: bool = False
    lateral: float = 0.0
    forward: float = 0.0
    turn: float = 0.0
    strength: float = 1.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
            raise ValueError("Action.strength must be finite and in [0, 1]")


NO_ACTION = Action()


@runtime_checkable
class Policy(Protocol):
    def reset(self) -> None: ...
    def decide(self, motor: MotorState) -> Action: ...


class DiagnosticPolicy(Protocol):
    """Optional presentation interface, separate from behavioral Policy.

    Known optional keys: escape_threshold (summed DNp01 trace units) and
    refractory_seconds. A policy need not implement this interface.
    """
    def diagnostics(self) -> Mapping[str, float]: ...


class FixedEscapePolicy:
    """Untrained escape decoder.

    * Trigger: summed DNp01 trace crosses `threshold` and the fly is not in its
      post-escape refractory period.
    * Threat side: the DNp01 side with more activity (measured ipsilateral to
      the looming stimulus: left loom -> escape_L 23.7 vs escape_R 0.3).
    * Direction: away from the threat side, plus a small forward bias.
    * Steering: DNa02 left/right asymmetry. The sign is chosen so the asymmetry
      turns the fly away from the looming side. Real DNa02 activation drives
      *ipsilateral* turns, so this sign is a gameplay convention, not a claim
      about DNa02 polarity.
    """

    def __init__(self, threshold: float, refractory_seconds: float, tick_seconds: float,
                 forward_bias: float = 0.35, turn_gain: float = 0.8):
        if not (threshold > 0.0):
            raise ValueError(f"escape threshold must be positive, got {threshold!r}")
        self.threshold = float(threshold)
        self.refractory_ticks = int(round(refractory_seconds / tick_seconds))
        self.tick_seconds = float(tick_seconds)
        self.forward_bias = float(forward_bias)
        self.turn_gain = float(turn_gain)
        self._cooldown = 0

    def reset(self) -> None:
        self._cooldown = 0

    @property
    def refractory_remaining(self) -> int:
        return self._cooldown

    def diagnostics(self) -> dict[str, float]:
        return {"escape_threshold": self.threshold,
                "refractory_seconds": self._cooldown * self.tick_seconds}

    def decide(self, motor: MotorState) -> Action:
        # DNa02 asymmetry steers continuously, whether or not an escape fires.
        turn = float(np.clip(self.turn_gain * (motor.dna02_left - motor.dna02_right), -1.0, 1.0))
        if self._cooldown > 0:
            self._cooldown -= 1
            return Action(turn=turn)
        if motor.dnp01_total < self.threshold:
            return Action(turn=turn)
        # Ties break to "threat on the left" so the decision stays deterministic.
        threat_left = motor.dnp01_left >= motor.dnp01_right
        strength = float(min(1.0, motor.dnp01_total / (2.0 * self.threshold)))
        self._cooldown = self.refractory_ticks
        return Action(escape=True,
                      lateral=(1.0 if threat_left else -1.0),
                      forward=self.forward_bias,
                      turn=turn, strength=strength)
