"""Category B: phenomenological free flight and boundary behaviour.

This controller decides *when* the fly changes course and *by how much*. It
is not the connectome and does not pretend to be. Its only inputs are its own
seeded clock and an `enclosure.WallCue` -- a local, body-frame percept of the
surrounding surfaces. It never sees the swatter, the brain, arena size or an
absolute position, and there is no global planner, waypoint or exit location
anywhere in it.

What it produces:

* **CORRECTION** -- a small course adjustment.
* **SACCADE** -- an ordinary spontaneous rapid turn.
* **AVOID** -- a pre-contact turn onto a heading tangent to a surface the fly
  is closing on, triggered by the optic-flow proxy, not by wall coordinates.
* **DEPART** -- a turn back into open space after the fly has spent a while
  near the perimeter.

Timing is a seeded three-component mixture (some short gaps, mostly ordinary
gaps, occasionally a long straight run) so the rhythm is not metronomic.
Nothing here steers frame by frame: between pulses the heading is left alone,
which is what preserves the visible structure of coherent flight -> discrete
rapid turn -> coherent flight.

The threat pathway (category C) and the geometric containment constraint
(category D) are elsewhere; see game/FLIGHT.md for the full table.
"""
from __future__ import annotations

import math

import numpy as np

from .enclosure import WallCue


class FreeFlightController:
    def __init__(self, config: dict, seed: int):
        i, c, s, b = (config["interval"], config["correction"],
                      config["saccade"], config["boundary"])
        self.short_range = tuple(i["short_seconds"])
        self.ordinary_range = tuple(i["ordinary_seconds"])
        self.long_range = tuple(i["long_seconds"])
        self.short_probability = float(i["short_probability"])
        self.long_probability = float(i["long_probability"])
        self.perimeter_multiplier = float(i["perimeter_multiplier"])
        if self.short_probability + self.long_probability >= 1.0:
            raise ValueError("ordinary intervals must keep a positive probability")
        self.correction_degrees = tuple(c["degrees"])
        self.correction_peak = tuple(c["peak_rate_deg_per_second"])
        self.correction_probability = float(c["probability"])
        self.saccade_degrees = tuple(s["degrees"])
        self.saccade_peak = tuple(s["peak_rate_deg_per_second"])
        self.avoid_ttc = float(b["avoid_time_to_contact_seconds"])
        self.avoid_inward = math.radians(float(b["avoid_inward_degrees"]))
        self.avoid_refractory_seconds = float(b["avoid_refractory_seconds"])
        self.avoid_peak = tuple(b["avoid_peak_rate_deg_per_second"])
        self.perimeter_enter = float(b["perimeter_enter_proximity"])
        self.perimeter_leave = float(b["perimeter_leave_proximity"])
        if self.perimeter_leave >= self.perimeter_enter:
            raise ValueError("perimeter thresholds must leave a hysteresis band")
        self.patience_range = tuple(b["patience_seconds"])
        self.depart_degrees = tuple(b["depart_degrees"])
        self.depart_peak = tuple(b["depart_peak_rate_deg_per_second"])
        self.reset(seed)

    def reset(self, seed: int) -> None:
        # Its own stream: adding or removing course changes must not resample
        # the world's drift or the brain's noise.
        self.rng = np.random.default_rng(seed + 3907)
        self.perimeter_seconds = 0.0
        self.near_wall = False
        self.departing = False
        self.avoid_refractory = 0.0
        self.patience = self._uniform(self.patience_range)
        self.wall_side = 1.0 if self.rng.random() < 0.5 else -1.0
        self.last_request = "NONE"
        self.wait = self._interval(near=False)

    # ---- seeded sampling --------------------------------------------------
    def _uniform(self, span) -> float:
        return float(self.rng.uniform(span[0], span[1]))

    def _interval(self, near: bool) -> float:
        """Mixture of gap lengths, so turns do not arrive on a metronome."""
        u = float(self.rng.random())
        if u < self.short_probability:
            gap = self._uniform(self.short_range)
        elif u < self.short_probability + self.long_probability:
            gap = self._uniform(self.long_range)
        else:
            gap = self._uniform(self.ordinary_range)
        # Along a wall the fly holds its course longer, which is what reads as
        # following the edge rather than pinballing off it.
        return gap * (self.perimeter_multiplier if near else 1.0)

    def _away_sign(self, bearing: float) -> float:
        if abs(bearing) < 1e-9:
            return self.wall_side
        return -1.0 if bearing > 0.0 else 1.0

    # ---- boundary responses ----------------------------------------------
    def _avoid_angle(self, cue: WallCue) -> float:
        """Turn onto a heading tangent to the surface, tilted slightly inward.

        Turning by `delta` moves the surface bearing from `b` to `b - delta`,
        so the two tangent solutions are `b -+ (pi/2 + inward)`. Taking the
        smaller one is the directional-persistence rule: the fly keeps as much
        of its current course as it can and ends up travelling along the wall
        instead of rebounding off it.
        """
        target = 0.5 * math.pi + self.avoid_inward
        left, right = cue.contact_bearing - target, cue.contact_bearing + target
        if abs(abs(left) - abs(right)) < 1e-9:
            delta = target * self.wall_side          # dead ahead: hold a side
        else:
            delta = left if abs(left) < abs(right) else right
        self.wall_side = 1.0 if delta > 0.0 else -1.0
        return delta

    # ---- main entry point -------------------------------------------------
    def update(self, dt: float, cue: WallCue, actuator, neural_active: bool = False,
               spontaneous_clock_rate: float = 1.0) -> None:
        """Advance the clock and, at most, request one pulse.

        `neural_active` means the connectome-driven policy is currently
        steering. Spontaneous turns stand down so that threat behaviour reads
        as categorically different from baseline locomotion, but avoidance and
        departure keep running -- a fly held against a wall by a hovering
        swatter must not be stuck there forever. The actuator's own priorities
        still let an ESCAPE outrank an AVOID.
        """
        if type(cue) is not WallCue:
            raise TypeError("FreeFlightController accepts only WallCue")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        if not math.isfinite(spontaneous_clock_rate) or not 0 <= spontaneous_clock_rate <= 2:
            raise ValueError("spontaneous clock rate must be in [0,2]")
        self.avoid_refractory = max(0.0, self.avoid_refractory - dt)
        if cue.proximity >= self.perimeter_enter and not self.near_wall:
            self.near_wall = True
            self.patience = self._uniform(self.patience_range)
        elif cue.proximity <= self.perimeter_leave:
            self.near_wall = self.departing = False
            self.perimeter_seconds = 0.0
        near = self.near_wall
        if near:
            self.perimeter_seconds += dt
        # Gaps measure quiet eligible flight time *after* a pulse. An occupied
        # actuator never causes frame-wise resampling of a rejected event.
        if not actuator.active and not neural_active:
            self.wait -= dt * spontaneous_clock_rate

        if (cue.expansion * self.avoid_ttc >= 1.0 and not cue.open_ahead
                and abs(cue.contact_bearing) < math.pi / 2 + self.avoid_inward
                and self.avoid_refractory <= 0.0 and actuator.can_request("AVOID")):
            if actuator.request("AVOID", self._avoid_angle(cue),
                                math.radians(self._uniform(self.avoid_peak))):
                self.avoid_refractory = actuator.duration + self.avoid_refractory_seconds
                self.last_request = "AVOID"
                return

        if (near and not self.departing and self.perimeter_seconds >= self.patience
                and actuator.can_request("DEPART")):
            angle = math.radians(self._uniform(self.depart_degrees))
            if actuator.request("DEPART", angle * self._away_sign(cue.surface_bearing),
                                math.radians(self._uniform(self.depart_peak))):
                self.departing = True
                self.wait = self._interval(near=False)
                self.last_request = "DEPART"
                return

        if (self.wait <= 0.0 and not neural_active and not actuator.active
                and not self.departing and actuator.enabled):
            self._spontaneous(cue, actuator, near)

    def _spontaneous(self, cue: WallCue, actuator, near: bool) -> None:
        # Near a surface the fly only trims its course; a full saccade there
        # would point it straight back into the wall it is following.
        correction = near or float(self.rng.random()) < self.correction_probability
        span, peak = ((self.correction_degrees, self.correction_peak) if correction
                      else (self.saccade_degrees, self.saccade_peak))
        magnitude = self._uniform(span)
        if near and abs(cue.surface_bearing) < math.pi / 3.0:
            sign = self._away_sign(cue.surface_bearing)
        else:
            sign = 1.0 if self.rng.random() < 0.5 else -1.0
        kind = "CORRECTION" if correction else "SACCADE"
        if actuator.request(kind, math.radians(magnitude * sign),
                            math.radians(self._uniform(peak))):
            self.last_request = kind
            self.wait = self._interval(near)
        else:
            # Actuator busy with something more important; look again soon
            # rather than dropping the event or retrying every frame.
            self.wait = self._uniform(self.short_range)

    def diagnostics(self) -> dict[str, float | str]:
        return {"requested": self.last_request,
                "perimeter_seconds": self.perimeter_seconds,
                "boundary_mode": "departing" if self.departing else "perimeter" if self.near_wall else "interior",
                "next_turn_seconds": max(0.0, self.wait)}
