"""Game world: swatter kinematics, fly physics, collision, statistics.

This is the ONLY module allowed to know where the mouse is. It holds no
reference to the brain, the encoder or `FlyLoop`; the fly's brain reaches it
exclusively as an `Action` (a body-frame impulse), and the mouse reaches the
fly exclusively as geometry that `perception.py` turns into a `Retina`.

Geometry note: the swatter lives in 3-D. It has a position in the play plane
plus a height above it, and a paddle that rotates from edge-on (while
hovering) to face-on (while striking). The wind-up is therefore *visible* --
it drops the paddle from hover height and turns its face toward the fly, which
is a genuine looming expansion on the fly's retina. No phase flag is ever
handed to the fly.
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass

import numpy as np

from .action import NO_ACTION, Action, MotionState
from .enclosure import Enclosure, WallCue
from .flight import FreeFlightController
from .saccade import SaccadeActuator


class StrikePhase(enum.Enum):
    IDLE = "idle"
    WINDUP = "windup"
    ACTIVE = "active"
    COOLDOWN = "cooldown"


_PHASE_CODE = {StrikePhase.IDLE: 0.0, StrikePhase.WINDUP: 1.0,
               StrikePhase.ACTIVE: 2.0, StrikePhase.COOLDOWN: 3.0}


@dataclass
class Swatter:
    x: float
    y: float
    target_x: float
    target_y: float
    phase: StrikePhase = StrikePhase.IDLE
    phase_elapsed: float = 0.0
    height: float = 0.0
    face: float = 0.0          # 0 = edge-on, 1 = face-on


@dataclass
class Fly:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    heading: float = 0.0       # radians; 0 points along +x
    alive: bool = True


@dataclass
class Stats:
    survival_seconds: float = 0.0
    strikes: int = 0
    hits: int = 0
    misses: int = 0
    escapes: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.strikes if self.strikes else 0.0

    @property
    def escape_rate(self) -> float:
        return self.escapes / self.strikes if self.strikes else 0.0


@dataclass(frozen=True, slots=True)
class TickEvents:
    strike_started: bool = False
    strike_resolved: bool = False
    hit: bool = False
    escaped: bool = False


class World:
    def __init__(self, config: dict, seed: int):
        w, s, f = config["world"], config["swatter"], config["fly"]
        self.width = float(w["width"])
        self.height = float(w["height"])
        self.margin = float(w["margin"])
        self.splat_seconds = float(w["splat_seconds"])
        self.paddle_radius = float(s["paddle_radius"])
        self.hover_height = float(s["hover_height"])
        self.windup_height = float(s["windup_height"])
        self.active_height = float(s["active_height"])
        self.edge_on_factor = float(s["edge_on_factor"])
        self.max_tracking_speed = float(s["max_tracking_speed"])
        self.smoothing_tau = float(s["smoothing_tau"])
        self.windup_tracking_factor = float(s["windup_tracking_factor"])
        self.active_tracking_factor = float(s["active_tracking_factor"])
        self.windup_seconds = float(s["windup_seconds"])
        self.active_seconds = float(s["active_seconds"])
        self.cooldown_seconds = float(s["cooldown_seconds"])
        self.fly_radius = float(f["radius"])
        self.damping = float(f["damping_per_second"])
        self.max_speed = float(f["max_speed"])
        self.escape_impulse = float(f["escape_impulse"])
        self.turn_rate = float(f["turn_rate"])
        self.max_yaw_rate = float(f["max_yaw_rate"])
        self.body_length = float(f["body_length_px"])
        if not (self.body_length > 0.0):
            raise ValueError("fly.body_length_px must be positive")
        self.baseline_speed = float(f["baseline_speed"])
        self.wander_turn_rate = float(f["wander_turn_rate"])
        self.wander_turn_tau = float(f["wander_turn_tau_seconds"])
        self.wander_interval = float(f["wander_interval_seconds"])
        sa = config["saccades"]
        self.saccades = SaccadeActuator(sa)
        self.alert_max_angle = math.radians(float(sa["alert_max_degrees"]))
        self.alert_peak_rate = math.radians(float(sa["alert_peak_rate_deg_per_second"]))
        self.escape_max_angle = math.radians(float(sa["escape_max_degrees"]))
        self.escape_peak_rate = math.radians(float(sa["escape_peak_rate_deg_per_second"]))
        self.enclosure = Enclosure(self.width, self.height, self.margin, self.fly_radius,
                                   float(config["flight"]["boundary"]["sense_range"]))
        self.flight = FreeFlightController(config["flight"], seed)
        # Measurement escape hatch: tools/calibrate_escape.py turns this off so
        # a full strike can be observed without the fly dying part-way through.
        # Always True during play.
        self.collisions_enabled = True
        # Calibration freezes position, heading and velocity, including wander.
        # This flag persists across reset(), like collisions_enabled.
        self.fly_motion_enabled = True
        self.reset(seed)

    # ---- lifecycle --------------------------------------------------------
    def reset(self, seed: int) -> None:
        self.rng = np.random.default_rng(seed)
        self.saccades.reset()
        self.flight.reset(seed)
        self.yaw_rate = 0.0
        self.wall_cue = WallCue()
        self.wall_contact = False
        self.swatter = Swatter(x=self.width * 0.5, y=self.height * 0.18,
                               target_x=self.width * 0.5, target_y=self.height * 0.18,
                               height=self.hover_height, face=0.0)
        # Airborne from the first frame: a fly does not accelerate from rest,
        # and starting at cruise removes a visible start-up lurch.
        self.fly = Fly(x=self.width * 0.5, y=self.height * 0.62, heading=0.0,
                       vx=self.baseline_speed if self.fly_motion_enabled else 0.0, vy=0.0)
        self.stats = Stats()
        self.splat_elapsed = 0.0
        self._wander_turn = 0.0
        self._wander_target = 0.0
        self._wander_timer = 0.0
        self._escape_seen_this_strike = False
        self._strike_outcome_recorded = True
        self._resample_wander()

    # ---- input (the only mouse entry point in the codebase) ---------------
    def set_pointer(self, x: float, y: float) -> None:
        """Mouse position in world units. Sets the swatter's *target*; the
        swatter itself is smoothed and speed-capped, so it cannot teleport."""
        self.swatter.target_x = float(min(max(x, 0.0), self.width))
        self.swatter.target_y = float(min(max(y, 0.0), self.height))

    def request_strike(self) -> bool:
        """Left click. Accepted only from IDLE, which is what enforces the
        cooldown between strikes."""
        if self.swatter.phase is not StrikePhase.IDLE or not self.fly.alive:
            return False
        self.swatter.phase = StrikePhase.WINDUP
        self.swatter.phase_elapsed = 0.0
        self.stats.strikes += 1
        self._escape_seen_this_strike = False
        self._strike_outcome_recorded = False
        return True

    # ---- derived swatter geometry (what perception reads) -----------------
    @property
    def visual_half_size(self) -> float:
        """Half-width of the paddle as presented to the fly. The paddle is
        edge-on while hovering and face-on while striking, so this grows during
        the wind-up without anyone telling the fly a strike is coming."""
        f = self.edge_on_factor + (1.0 - self.edge_on_factor) * self.swatter.face
        return self.paddle_radius * f

    @property
    def lethal(self) -> bool:
        return self.swatter.phase is StrikePhase.ACTIVE

    @property
    def splat_finished(self) -> bool:
        return (not self.fly.alive) and self.splat_elapsed >= self.splat_seconds

    # ---- update -----------------------------------------------------------
    def tick(self, dt: float, action: Action = NO_ACTION) -> TickEvents:
        # Per-tick event, not a sticky state after death or calibration freeze.
        self.wall_contact = False
        hit = False
        if self.fly.alive:
            self.stats.survival_seconds += dt
            if (self.fly_motion_enabled and action.escape and action.strength > 0.0
                    and math.hypot(action.lateral, action.forward) > 0.0):
                self._escape_seen_this_strike = True
        else:
            self.splat_elapsed += dt
        resolved = self._advance_phase(dt)
        self._move_swatter(dt)
        if self.fly.alive:
            if self.fly_motion_enabled:
                self._move_fly(dt, action)
            else:
                self.fly.vx = self.fly.vy = self.yaw_rate = 0.0
            hit = self._resolve_collision()
        # Each strike is scored exactly once. The kill lands on an ACTIVE tick
        # while the window closes on a later tick, so without this guard a
        # successful strike would be counted as a hit AND a miss.
        escaped = False
        if hit:
            self.fly.alive = False
            self.fly.vx = self.fly.vy = 0.0
            self.stats.hits += 1
            self.splat_elapsed = 0.0
            self._strike_outcome_recorded = True
        elif resolved and not self._strike_outcome_recorded:
            self.stats.misses += 1
            self._strike_outcome_recorded = True
            if self._escape_seen_this_strike:
                self.stats.escapes += 1
                escaped = True
        return TickEvents(False, resolved, hit, escaped)

    def _advance_phase(self, dt: float) -> bool:
        """Advance the strike state machine. Returns True on the tick an
        unsuccessful strike finishes its active window."""
        sw = self.swatter
        sw.phase_elapsed += dt
        resolved = False
        if sw.phase is StrikePhase.WINDUP:
            if sw.phase_elapsed >= self.windup_seconds:
                sw.phase = StrikePhase.ACTIVE
                sw.phase_elapsed -= self.windup_seconds
        elif sw.phase is StrikePhase.ACTIVE:
            if sw.phase_elapsed >= self.active_seconds:
                sw.phase = StrikePhase.COOLDOWN
                sw.phase_elapsed -= self.active_seconds
                resolved = True
        elif sw.phase is StrikePhase.COOLDOWN:
            if sw.phase_elapsed >= self.cooldown_seconds:
                sw.phase = StrikePhase.IDLE
                sw.phase_elapsed = 0.0
        self._apply_phase_geometry()
        return resolved

    def _apply_phase_geometry(self) -> None:
        sw = self.swatter
        if sw.phase is StrikePhase.WINDUP:
            p = min(1.0, sw.phase_elapsed / self.windup_seconds)
            sw.height = self.hover_height + (self.windup_height - self.hover_height) * p
            sw.face = p
        elif sw.phase is StrikePhase.ACTIVE:
            p = min(1.0, sw.phase_elapsed / self.active_seconds)
            sw.height = self.windup_height + (self.active_height - self.windup_height) * p
            sw.face = 1.0
        elif sw.phase is StrikePhase.COOLDOWN:
            p = min(1.0, sw.phase_elapsed / self.cooldown_seconds)
            sw.height = self.active_height + (self.hover_height - self.active_height) * p
            sw.face = 1.0 - p
        else:
            sw.height = self.hover_height
            sw.face = 0.0

    def _move_swatter(self, dt: float) -> None:
        """Exponential smoothing toward the pointer, hard-capped by
        max_tracking_speed, and slowed once the player commits to a strike."""
        sw = self.swatter
        factor = {StrikePhase.IDLE: 1.0,
                  StrikePhase.COOLDOWN: 1.0,
                  StrikePhase.WINDUP: self.windup_tracking_factor,
                  StrikePhase.ACTIVE: self.active_tracking_factor}[sw.phase]
        if factor <= 0.0:
            return
        alpha = 1.0 - math.exp(-dt / self.smoothing_tau)
        step_x = (sw.target_x - sw.x) * alpha * factor
        step_y = (sw.target_y - sw.y) * alpha * factor
        limit = self.max_tracking_speed * factor * dt
        mag = math.hypot(step_x, step_y)
        if mag > limit and mag > 0.0:
            step_x *= limit / mag
            step_y *= limit / mag
        sw.x += step_x
        sw.y += step_y

    def _resample_wander(self) -> None:
        # Tonic exploration changes angular velocity, never screen direction.
        self._wander_target = float(self.rng.uniform(-self.wander_turn_rate,
                                                     self.wander_turn_rate))

    def _move_fly(self, dt: float, action: Action) -> None:
        fly = self.fly
        self._wander_timer += dt
        if self._wander_timer >= self.wander_interval:
            self._wander_timer -= self.wander_interval
            self._resample_wander()
        self._wander_turn += (self._wander_target - self._wander_turn) * (
            1.0 - math.exp(-dt / self.wander_turn_tau))

        # Escape is an impulse on velocity, never a position jump.
        if action.escape:
            hx, hy = math.cos(fly.heading), math.sin(fly.heading)
            rx, ry = -hy, hx                       # the fly's own right
            ix = rx * action.lateral + hx * action.forward
            iy = ry * action.lateral + hy * action.forward
            mag = math.hypot(ix, iy)
            if mag > 0.0:
                fly.vx += self.escape_impulse * action.strength * ix / mag
                fly.vy += self.escape_impulse * action.strength * iy / mag

        # Tonic locomotion is game physics, NOT a connectome threat response.
        # Damping relaxes velocity toward forward cruise, retaining inertia and
        # lateral escape momentum. Threat steering arrives only via Action.
        ax = self.damping * (self.baseline_speed * math.cos(fly.heading) - fly.vx)
        ay = self.damping * (self.baseline_speed * math.sin(fly.heading) - fly.vy)
        fly.vx += ax * dt
        fly.vy += ay * dt
        speed = math.hypot(fly.vx, fly.vy)
        if speed > self.max_speed:
            fly.vx *= self.max_speed / speed
            fly.vy *= self.max_speed / speed
        fly.x += fly.vx * dt
        fly.y += fly.vy * dt

        # (A) Local sensory geometry: what the surrounding surfaces look like
        # from the fly's own heading. No wall coordinates leave the enclosure.
        self.wall_cue = self.enclosure.sense(fly.x, fly.y, fly.vx, fly.vy, fly.heading)
        # (D) Last-resort constraint: slide, never bounce. Sense approach
        # before this safety constraint removes outward speed.
        self.wall_contact = self.enclosure.contain(fly)
        # (C) Threat turns, and only these, come from the connectome.
        self._request_threat_pulse(action)
        # (B) Free flight and boundary behaviour, driven by the local cue.
        self.flight.update(dt, self.wall_cue, self.saccades,
                           neural_active=self._neural_active(action))

        # Do not overwrite heading from velocity: that used to erase steering
        # at cruise speed and abruptly swivel the body after a lateral impulse.
        # The clip is an actuator safety bound; it sits above every pulse peak
        # rate plus normal steering/drift under the shipped configuration.
        # Custom excessive steering is clipped as a final safety constraint.
        pulse = self.saccades.step(dt)
        self.yaw_rate = float(np.clip(action.turn * self.turn_rate + self._wander_turn
                                      + pulse / dt,
                                      -self.max_yaw_rate, self.max_yaw_rate))
        fly.heading = (fly.heading + self.yaw_rate * dt) % (2.0 * math.pi)

    @staticmethod
    def _neural_active(action: Action) -> bool:
        """True while the descending-neuron policy is steering the fly."""
        return bool(action.escape or action.saccade or abs(action.turn) > 0.03)

    def _request_threat_pulse(self, action: Action) -> None:
        """Category C: the only route from the connectome to a rapid turn.

        Amplitude and side come from the policy's reading of DNp01/DNa02.
        Peak rates are fixed rather than sampled, so a threat response can
        never be manufactured by the baseline RNG.
        """
        if not action.saccade:
            return
        if action.escape:
            if action.strength > 0.0:
                self.saccades.request("ESCAPE", self.escape_max_angle * action.saccade,
                                      self.escape_peak_rate)
        else:
            self.saccades.request("ALERT", self.alert_max_angle * action.saccade,
                                  self.alert_peak_rate)

    # ---- body-relative scale ----------------------------------------------
    @property
    def cruise_body_lengths_per_second(self) -> float:
        return self.baseline_speed / self.body_length

    @property
    def body_lengths_per_second(self) -> float:
        return math.hypot(self.fly.vx, self.fly.vy) / self.body_length

    def motion_state(self) -> MotionState:
        """Whitelisted body-frame feedback, with no absolute pose or threat."""
        f = self.fly
        hx, hy = math.cos(f.heading), math.sin(f.heading)
        return MotionState(f.vx * hx + f.vy * hy, -f.vx * hy + f.vy * hx,
                           self.yaw_rate, self.saccades.remaining)

    def _resolve_collision(self) -> bool:
        """Lethal only inside the active strike window."""
        if not self.lethal or not self.collisions_enabled:
            return False
        d = math.hypot(self.swatter.x - self.fly.x, self.swatter.y - self.fly.y)
        return d <= self.paddle_radius + self.fly_radius

    def state_vector(self) -> np.ndarray:
        """Compact snapshot of everything that evolves, for the determinism test."""
        sw, fly, st = self.swatter, self.fly, self.stats
        return np.array([sw.x, sw.y, sw.height, sw.face, _PHASE_CODE[sw.phase],
                         sw.phase_elapsed, fly.x, fly.y, fly.vx, fly.vy, fly.heading,
                         float(fly.alive), st.survival_seconds, st.strikes,
                         st.hits, st.misses, st.escapes], dtype=np.float64)
