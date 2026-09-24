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

from collections import deque
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
    The human-session recorder persists this whole mapping, so its key set is
    part of the frozen recorder schema. FixedEscapePolicy reports escape-trigger
    provenance separately through criterion_diagnostics(), which the recorder
    does not call. A policy need not implement this interface.
    """
    def diagnostics(self) -> Mapping[str, float | str]: ...


class FixedEscapePolicy:
    """Untrained escape decoder.

    * Trigger: the fly is not in its post-escape refractory period and the
      summed DNp01 trace satisfies the escape criterion. With the default
      single-sample criterion that is one sample at or above `threshold`.
      The M1.8-N2 dual-path criterion (`fast_threshold` set,
      `persistence_samples` > 1) fires on either path:
        - FAST: one sample at or above `fast_threshold`;
        - SUSTAINED: `persistence_samples` consecutive samples at or above
          `threshold`, counting the first qualifying sample, so N = 3 is
          satisfied on sample t + 2 * tick (40 ms at 20 ms ticks).
      The streak counts every sample, including refractory samples, is cleared
      by any sample below `threshold`, and is cleared when an escape fires.
      The M1.8-N2b gap-tolerant variant (`sustained_window_samples` set)
      replaces the consecutive streak: SUSTAINED holds when the current sample
      is at or above `threshold` AND at least `persistence_samples` of the most
      recent `sustained_window_samples` samples, including the current one, are
      at or above it. The window gains one flag on every sample, refractory
      samples included, never holds more than its length, and is cleared when
      an escape fires and on reset. A current sample below `threshold` never
      fires SUSTAINED.
      These parameters are Class C decoder constants chosen to separate the
      simulator's spontaneous DNp01 coincidences from sustained threat
      evidence; they are not biological constants.
      The M1.8-N4B1C lateral path (`lateral_window_samples` set, on top of the
      window criterion) adds a third path, LATERAL: the SAME DNp01 side
      produces two inferred spikes at most `lateral_window_samples` samples
      apart. Spikes are inferred per side from that side's own leaky trace,
      spike_t = trace_t - trace_decay * trace_{t-1} >= 0.5 (the trace adds
      1.0 per spike); no spike is inferred on the first sample after reset,
      whose previous trace value is unknown. Left and right are tracked
      independently, so a left spike followed by a right spike never
      qualifies. Spike history updates on every sample, refractory samples
      included, and both sides' last-spike memory is cleared when an escape
      fires and on reset, so a spike before an escape never pairs with one
      after it. The qualifying spike must be on the current sample. Channel
      precedence for diagnostics is LATERAL, then FAST, then SUSTAINED; the
      motor output does not depend on which path fired. The 60 ms window
      (3 samples) is a Class C simulator-derived engineering parameter, not a
      biological constant.
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
                 alert_saccade_dwell_seconds: float = 0.06,
                 fast_threshold: float | None = None, persistence_samples: int = 1,
                 sustained_window_samples: int | None = None,
                 require_current_qualifying: bool = True,
                 lateral_window_samples: int | None = None,
                 lateral_required_spikes: int = 2,
                 trace_decay: float | None = None):
        if not (threshold > 0.0):
            raise ValueError(f"escape threshold must be positive, got {threshold!r}")
        if isinstance(persistence_samples, bool) or not isinstance(persistence_samples, int) \
                or persistence_samples < 1:
            raise ValueError(f"persistence_samples must be an integer >= 1, got {persistence_samples!r}")
        if fast_threshold is not None and not (math.isfinite(fast_threshold)
                                               and fast_threshold > threshold):
            raise ValueError(f"fast_threshold must be finite and above threshold, got {fast_threshold!r}")
        if (fast_threshold is None) != (persistence_samples == 1):
            raise ValueError("the dual-path criterion needs both fast_threshold and "
                             "persistence_samples > 1; the single-sample criterion needs neither")
        if sustained_window_samples is not None:
            if isinstance(sustained_window_samples, bool) \
                    or not isinstance(sustained_window_samples, int) \
                    or not (fast_threshold is not None
                            and 2 <= persistence_samples <= sustained_window_samples):
                raise ValueError("the window criterion needs fast_threshold and "
                                 "2 <= persistence_samples <= sustained_window_samples")
            if require_current_qualifying is not True:
                # Plain k-of-n can fire on a sub-threshold sample at refractory
                # expiry from evidence up to n samples old; it is not supported.
                raise ValueError("the window criterion requires require_current_qualifying=True")
        if lateral_window_samples is not None:
            if isinstance(lateral_window_samples, bool) or not isinstance(lateral_window_samples, int) \
                    or lateral_window_samples < 1:
                raise ValueError("lateral_window_samples must be an integer >= 1")
            if sustained_window_samples is None:
                raise ValueError("the lateral path is defined only on top of the window criterion")
            if lateral_required_spikes != 2 or isinstance(lateral_required_spikes, bool):
                raise ValueError("only two-spike same-side lateral evidence is supported")
            if trace_decay is None or not (0.0 < trace_decay < 1.0):
                raise ValueError("the lateral path needs the DNp01 trace decay in (0, 1)")
        elif trace_decay is not None:
            raise ValueError("trace_decay is used only by the lateral path")
        self.lateral_window_samples = (None if lateral_window_samples is None
                                       else int(lateral_window_samples))
        self.lateral_required_spikes = int(lateral_required_spikes)
        self.trace_decay = None if trace_decay is None else float(trace_decay)
        self.threshold = float(threshold)
        self.fast_threshold = None if fast_threshold is None else float(fast_threshold)
        self.persistence_samples = int(persistence_samples)
        self.dual_path = self.fast_threshold is not None
        self.sustained_window_samples = (None if sustained_window_samples is None
                                         else int(sustained_window_samples))
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
        self._streak = 0
        self._channel = "NONE"
        self._window = deque(maxlen=self.sustained_window_samples or 1)
        # M1.8-N4B1C lateral evidence (scalars only; neural state, no world data).
        self._sample_index = 0
        self._lat_prev_left = self._lat_prev_right = None     # unknown before the first sample
        self._lat_last_left = self._lat_last_right = None     # sample index of the last spike
        self._lat_now_left = self._lat_now_right = False
        self._pending_paths = ""
        self._trigger_paths = ""

    @property
    def refractory_remaining(self) -> int:
        return self._cooldown

    def diagnostics(self) -> dict[str, float | str]:
        # Recorded verbatim by the session recorder: keep this key set frozen.
        return {"escape_threshold": self.threshold,
                "refractory_seconds": self._cooldown * self.tick_seconds,
                "behavior_state": self._state,
                "escape_strength": self._escape_strength}

    def criterion_diagnostics(self) -> dict[str, float | int | str | None]:
        """Escape-trigger provenance for validation tools and tests.

        Deliberately outside diagnostics(), so it is not persisted by the frozen
        recorder schema. escape_trigger_channel is LATERAL, FAST, SUSTAINED or
        SINGLE_SAMPLE during the escape/refractory bout and NONE otherwise;
        escape_trigger_paths lists every path that qualified on the firing
        sample (for example "LATERAL+FAST").
        """
        windowed = self.sustained_window_samples is not None
        lateral = self.lateral_window_samples is not None
        return {"escape_decoder": ("lateral_dual_path_v1" if lateral else
                                   "dual_path_window_v1" if windowed else
                                   "dual_path_v1" if self.dual_path else "single_sample"),
                "escape_threshold": self.threshold,
                "escape_fast_threshold": self.fast_threshold,
                "escape_persistence_samples": self.persistence_samples,
                "escape_sustained_window_samples": self.sustained_window_samples,
                "escape_sustained_streak": self._streak,
                "escape_window_qualifying": sum(self._window) if windowed else None,
                "escape_lateral_window_samples": self.lateral_window_samples,
                "escape_lateral_required_spikes": self.lateral_required_spikes if lateral else None,
                "escape_lateral_last_spike_left": self._lat_last_left,
                "escape_lateral_last_spike_right": self._lat_last_right,
                "escape_sample_index": self._sample_index,
                "escape_trigger_paths": self._trigger_paths,
                "escape_trigger_channel": self._channel}

    def _observe_lateral(self, motor: MotorState, sample: int) -> None:
        """Infer this sample's spike on each side and whether that side qualifies."""
        window, decay = self.lateral_window_samples, self.trace_decay
        prev = self._lat_prev_left
        spike = prev is not None and motor.dnp01_left - decay * prev >= 0.5
        self._lat_now_left = spike and self._lat_last_left is not None \
            and sample - self._lat_last_left <= window
        if spike:
            self._lat_last_left = sample
        self._lat_prev_left = float(motor.dnp01_left)
        prev = self._lat_prev_right
        spike = prev is not None and motor.dnp01_right - decay * prev >= 0.5
        self._lat_now_right = spike and self._lat_last_right is not None \
            and sample - self._lat_last_right <= window
        if spike:
            self._lat_last_right = sample
        self._lat_prev_right = float(motor.dnp01_right)

    def _trigger_channel(self, total: float) -> str | None:
        """Which criterion path this sample satisfies.

        Precedence for the diagnostic channel: LATERAL, FAST, SUSTAINED. The
        full set of qualifying paths is kept in self._pending_paths.
        """
        summed = self._summed_channel(total)
        if self.lateral_window_samples is None:
            return summed
        paths = []
        if self._lat_now_left or self._lat_now_right:
            paths.append("LATERAL")
        if summed is not None:
            paths.append(summed)
        self._pending_paths = "+".join(paths)
        return paths[0] if paths else None

    def _summed_channel(self, total: float) -> str | None:
        """The summed-trace criterion path this sample satisfies; FAST wins a tie."""
        if not self.dual_path:
            # The pre-N2 comparison, kept in its exact form.
            return None if total < self.threshold else "SINGLE_SAMPLE"
        if total >= self.fast_threshold:
            return "FAST"
        if self.sustained_window_samples is not None:
            if total >= self.threshold and sum(self._window) >= self.persistence_samples:
                return "SUSTAINED"
            return None
        if self._streak >= self.persistence_samples:
            return "SUSTAINED"
        return None

    def decide(self, motor: MotorState) -> Action:
        total = motor.dnp01_total
        # Sustained evidence is counted on every sample, refractory or not, so a
        # threat still present when the refractory period expires can fire at
        # once. Any sample below threshold clears the streak, and the window
        # forgets evidence older than its length, so stale evidence cannot.
        self._streak = self._streak + 1 if total >= self.threshold else 0
        if self.sustained_window_samples is not None:
            self._window.append(total >= self.threshold)
        sample = self._sample_index
        self._sample_index += 1
        if self.lateral_window_samples is not None:
            self._observe_lateral(motor, sample)
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
            self._channel = "NONE"
            self._trigger_paths = ""
        self._state = "ESCAPE" if cooling_down else (
            "ALERT" if alert or abs(self._turn) > 0.03 else "CALM")
        channel = None if cooling_down else self._trigger_channel(total)
        if channel is None:
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
        self._streak = 0
        self._window.clear()
        self._channel = channel
        if self.lateral_window_samples is not None:
            self._trigger_paths = self._pending_paths
            # Evidence from before an escape cannot pair with later spikes.
            self._lat_last_left = self._lat_last_right = None
        return Action(escape=True, lateral=float(asymmetry),
                      forward=self.forward_bias, turn=self._turn, strength=strength,
                      saccade=float(asymmetry) * strength)
