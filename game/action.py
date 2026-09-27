"""Descending-neuron activity -> body-frame motor command.

The boundary that keeps Milestone 2 cheap: everything upstream produces a
`MotorState`, everything downstream consumes an `Action`. A trained policy is a
drop-in replacement for `FixedEscapePolicy` -- same `Policy` protocol and explicit motor/action
data, no changes to world/perception/app. The fixed untrained policy remains
available for future comparisons; no learned policy is implemented here.

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
class MotionState:
    """Internal body-frame proprioception only; no position or threat bearing.

    The brain still receives Retina alone. Policies may use these measured
    velocities and their own resettable history, without access to World.
    """
    forward_speed: float = 0.0
    lateral_speed: float = 0.0
    yaw_rate: float = 0.0
    saccade_remaining: float = 0.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(getattr(self, name)) for name in self.__slots__):
            raise ValueError("MotionState values must be finite")
        if self.saccade_remaining < 0:
            raise ValueError("saccade_remaining must be nonnegative")


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
    motion: MotionState = field(default_factory=MotionState)

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
    when escape=False. saccade is a signed [-1, 1] request for a bounded
    heading pulse (+right). The world executes it over time, never as a snap.
    With escape=True it requests an emergency pulse; otherwise an alert pulse.
    """
    escape: bool = False
    lateral: float = 0.0
    forward: float = 0.0
    turn: float = 0.0
    strength: float = 1.0
    saccade: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.saccade) or not -1.0 <= self.saccade <= 1.0:
            raise ValueError("Action.saccade must be finite and in [-1, 1]")
        if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
            raise ValueError("Action.strength must be finite and in [0, 1]")


NO_ACTION = Action()


@runtime_checkable
class Policy(Protocol):
    def reset(self) -> None: ...
    def decide(self, motor: MotorState) -> Action: ...


class DiagnosticPolicy(Protocol):
    """Optional presentation interface, separate from behavioral Policy.

    Known optional keys: escape_threshold (summed DNp01 trace units),
    refractory_seconds, behavior_state (CALM/ALERT/ESCAPE), escape_strength
    (last impulse during the escape/refractory bout; zero otherwise).
    A policy need not implement this interface.
    """
    def diagnostics(self) -> Mapping[str, float | str]: ...


class FixedEscapePolicy:
    """Untrained escape decoder.

    * Trigger: summed DNp01 trace crosses `threshold` and the fly is not in its
      post-escape refractory period.
    * Alert: subthreshold DNp01 activity enables a modest, smoothed turn.
    * Direction: graded DNp01 left/right contrast in the fly's body frame,
      away from the more active side; a tie has no arbitrary lateral bias.
    * Steering: DNp01 contrast plus a small DNa02 contribution, gated by
      DNp01 activity. The away-turn sign is a game decoder convention, not a
      biological claim about DNa02 polarity. No retina/world inputs here.
    """

    def __init__(self, threshold: float, refractory_seconds: float, tick_seconds: float,
                 forward_bias: float = 0.35, turn_gain: float = 0.8,
                 alert_threshold_fraction: float = 0.55, steering_tau_seconds: float = 0.12,
                 alert_saccade_strength: float = 0.6, saccade_interval_seconds: float = 0.8,
                 alert_saccade_dwell_seconds: float = 0.06):
        if not (threshold > 0.0):
            raise ValueError(f"escape threshold must be positive, got {threshold!r}")
        self.threshold = float(threshold)
        self.refractory_ticks = int(round(refractory_seconds / tick_seconds))
        self.tick_seconds = float(tick_seconds)
        self.forward_bias = float(forward_bias)
        self.turn_gain = float(turn_gain)
        self.alert_threshold = self.threshold * float(alert_threshold_fraction)
        self.steering_alpha = 1.0 - math.exp(-tick_seconds / steering_tau_seconds)
        self.alert_saccade_strength = float(alert_saccade_strength)
        self.saccade_interval_ticks = max(1, int(round(saccade_interval_seconds / tick_seconds)))
        self.alert_dwell_ticks = max(1, int(round(alert_saccade_dwell_seconds / tick_seconds)))
        self.reset()

    def reset(self) -> None:
        self._cooldown = 0
        self._turn = 0.0
        self._side_left = self._side_right = 0.0
        self._state = "CALM"
        self._escape_strength = 0.0
        self._alert_ticks = 0
        self._saccade_cooldown = 0

    @property
    def refractory_remaining(self) -> int:
        return self._cooldown

    def diagnostics(self) -> dict[str, float | str]:
        return {"escape_threshold": self.threshold,
                "refractory_seconds": self._cooldown * self.tick_seconds,
                "behavior_state": self._state,
                "escape_strength": self._escape_strength}

    def decide(self, motor: MotorState) -> Action:
        total = motor.dnp01_total
        # Accumulate side evidence separately from the calibrated emergency
        # gate. One contralateral noise spike must not instantly reverse an
        # already developing escape. This memory contains neural state only.
        self._side_left += self.steering_alpha * (motor.dnp01_left - self._side_left)
        self._side_right += self.steering_alpha * (motor.dnp01_right - self._side_right)
        asymmetry = (self._side_left - self._side_right) / max(
            self._side_left + self._side_right, 1e-9)
        alert = total >= self.alert_threshold
        self._alert_ticks = self._alert_ticks + 1 if alert else 0
        self._saccade_cooldown = max(0, self._saccade_cooldown - 1)
        target_turn = 0.0
        if alert:
            # Both terms come from descending neurons. DNp01 owns the gate
            # and determines side; DNa02 modulates amplitude by at most 15%
            # and cannot reverse the away-turn or invent a side for a tie.
            steer = (motor.dna02_left - motor.dna02_right) / max(
                motor.dna02_left + motor.dna02_right, 1e-9)
            intensity = min(1.0, total / (2.0 * self.threshold))
            target_turn = float(np.clip(self.turn_gain * intensity *
                                       (asymmetry + 0.15 * abs(asymmetry) * steer), -1.0, 1.0))
        self._turn += self.steering_alpha * (target_turn - self._turn)
        cooling_down = self._cooldown > 0
        if cooling_down:
            self._cooldown -= 1
        else:
            self._escape_strength = 0.0
        self._state = "ESCAPE" if cooling_down else (
            "ALERT" if alert or abs(self._turn) > 0.03 else "CALM")
        if cooling_down or total < self.threshold:
            pulse = 0.0
            if (not cooling_down and self._alert_ticks >= self.alert_dwell_ticks
                    and self._saccade_cooldown == 0 and abs(asymmetry) > 0.1):
                pulse = self.alert_saccade_strength * asymmetry
                self._saccade_cooldown = self.saccade_interval_ticks
            return Action(turn=self._turn, saccade=pulse)
        strength = float(min(1.0, total / (2.0 * self.threshold)))
        self._cooldown = self.refractory_ticks
        self._escape_strength = strength
        self._state = "ESCAPE"
        return Action(escape=True, lateral=float(asymmetry),
                      forward=self.forward_bias, turn=self._turn, strength=strength,
                      saccade=float(asymmetry) * strength)
