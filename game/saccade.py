"""The turning actuator: bounded, continuous heading pulses.

This module is pure kinematics. It decides *how* a requested course change is
executed, never *whether* one should happen. Requests arrive from two
unrelated places:

* `flight.FreeFlightController` -- category B, phenomenological free flight
  and boundary behaviour (CORRECTION / SACCADE / AVOID / DEPART).
* `world.World`, forwarding an `Action` from the neural policy -- category C,
  the MaleCNS threat pathway (ALERT / ESCAPE).

A pulse is a half-sine angular-velocity profile: zero yaw rate at both
endpoints, finite duration, and an integral that is exactly the requested
angle. There is no instantaneous heading assignment anywhere, and a pulse
always spans several ticks, so heading is continuous at every frame. Duration
is derived from a peak angular speed rather than fixed, so a larger turn takes
proportionally longer and the peak rate stays under `peak_rate_cap`.

Turn sizes, peak rates and priorities are game conventions. Drosophila body
saccades are much faster than the M1.3 values these replace, but nothing here
is a measured MaleCNS dynamic, and the model is 2-D: no wings, banking, roll
or angular inertia. See game/FLIGHT.md.
"""
from __future__ import annotations

import math

# Higher wins. A request is accepted when the actuator is idle or when it
# strictly outranks the pulse in flight, so an emergency can cut through a
# spontaneous turn while ordinary turns cannot interrupt each other.
PRIORITY = {"NONE": 0, "CORRECTION": 1, "SACCADE": 2, "DEPART": 2,
            "AVOID": 3, "ALERT": 3, "ESCAPE": 4}


class SaccadeActuator:
    """Executes one heading pulse at a time."""

    def __init__(self, config: dict):
        self.enabled = bool(config["enabled"])
        self.min_duration = float(config["min_duration_seconds"])
        self.max_duration = float(config["max_duration_seconds"])
        self.max_degrees = float(config["max_degrees"])
        self.peak_rate_cap = math.radians(float(config["peak_rate_cap_deg_per_second"]))
        if not (self.min_duration > 0.0) or self.max_duration < self.min_duration:
            raise ValueError("saccade durations must be positive and ordered")
        if not (self.max_degrees > 0.0) or self.max_degrees >= 180.0:
            raise ValueError("max_degrees must be positive and below a half turn")
        if not math.isfinite(self.peak_rate_cap) or self.peak_rate_cap <= 0:
            raise ValueError("peak rate cap must be finite and positive")
        if not math.isfinite(self.max_duration):
            raise ValueError("duration must be finite")
        self.reset()

    def reset(self) -> None:
        self.kind = "NONE"
        self.angle = self.duration = self.elapsed = 0.0
        self.last_delta = 0.0

    @property
    def active(self) -> bool:
        return self.kind != "NONE"

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed) if self.active else 0.0

    def duration_for(self, angle: float, peak_rate: float) -> float:
        """Half-sine peak rate is pi/2 times the mean, hence the pi/2 factor.

        Infeasible requests raise without changing the active pulse. The
        minimum duration prevents one-frame snaps, and the pulse never
        exceeds the actuator angular-speed cap.
        """
        peak = min(float(peak_rate), self.peak_rate_cap)
        if peak <= 0 or not math.isfinite(peak):
            raise ValueError("peak rate must be positive and finite")
        needed = abs(angle) * math.pi / (2.0 * peak)
        if needed > self.max_duration:
            raise ValueError("requested angle/rate cannot fit max_duration_seconds")
        return max(self.min_duration, needed)

    def can_request(self, kind: str) -> bool:
        """Arbitration without sampling or mutating pulse state."""
        return (self.enabled and kind in PRIORITY and kind != "NONE"
                and PRIORITY[kind] > PRIORITY[self.kind])

    def request(self, kind: str, angle: float, peak_rate: float) -> bool:
        """Ask for a pulse. Returns True if it was started.

        The requested angle is clipped to `max_degrees`, which is what forbids
        an instant about-face. Preemption restarts the profile from the
        current heading, so heading stays continuous across the switch, but
        this is not an angular-inertia model.
        """
        if not self.can_request(kind):
            return False
        if not math.isfinite(angle) or not math.isfinite(peak_rate):
            raise ValueError("saccade request must be finite")
        limit = math.radians(self.max_degrees)
        angle = max(-limit, min(limit, float(angle)))
        if angle == 0.0:
            return False
        duration = self.duration_for(angle, peak_rate)
        self.kind, self.angle = kind, angle
        self.duration, self.elapsed = duration, 0.0
        return True

    def step(self, dt: float) -> float:
        """Advance the active pulse and return this tick's heading delta."""
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be positive and finite")
        self.last_delta = 0.0
        if not self.active:
            return 0.0
        before = min(1.0, self.elapsed / self.duration)
        self.elapsed = min(self.duration, self.elapsed + dt)
        after = self.elapsed / self.duration
        self.last_delta = self.angle * (math.cos(math.pi * before)
                                        - math.cos(math.pi * after)) / 2.0
        if self.elapsed >= self.duration:
            self.kind = "NONE"
            self.angle = self.duration = self.elapsed = 0.0
        return self.last_delta
