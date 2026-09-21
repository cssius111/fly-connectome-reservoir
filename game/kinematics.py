"""Kinematic profile interface between behavioral context and WORLD physics.

    behavioral / ecological / lifecycle context
        -> KinematicProfile request      (what the fly is asking its body to do)
        -> KinematicExecutor             (how that request becomes body velocity/yaw)
        -> WORLD integration, collision and containment

M1.8-B1 is a **no-op behavioral refactor**. Every effective value produced here equals
the accepted pre-B1 value, the arithmetic grouping of each update is preserved exactly,
and no new random draw is introduced. The envelope, limit and persistence fields are
inert hooks for M1.8-B2 and are ignored by the executor while they are None.

Nothing in this module maps literature magnitudes into ROOM. There is deliberately no
universal fly-speed constant: see game/M1_8_B_PLAN.md section 2.1, where the single
class-C `room_kinematic_scale` mapping is defined but its value is left unchosen.

Two relaxation laws exist because the accepted code uses two distinct formulas with
different floating-point grouping. They are kept separate rather than unified, so that
B1 can be accepted on bit-identical replay instead of on a tolerance.
"""
from dataclasses import dataclass
import copy
import math

import numpy as np

# Ecological locomotion contexts that M1.8-B2b may eventually sample. ALERT and ESCAPE
# are deliberately absent: they remain neural-override paths, so the configured
# ecology.speed_bl_s ALERT/ESCAPE envelopes are currently non-authoritative and are
# bypassed whenever threat_priority holds. LAND_APPROACH and TAKEOFF stay owned by the
# frozen M1.8-A lifecycle. See results/game/M1_8_B2A.md.
SAMPLED_CONTEXTS = frozenset({'EXPLORE', 'TRANSIT', 'ODOR_TRACK', 'ODOR_SEARCH', 'RECOVER'})
NEURAL_OVERRIDE_CONTEXTS = frozenset({'ALERT', 'ESCAPE'})
LIFECYCLE_OWNED_CONTEXTS = frozenset({'LAND_OR_PERCH'})

# Ordinary airborne cruise: a = k * (target*direction - v); v += a * dt
DAMPED_CRUISE = 'damped_cruise'
# Lifecycle landing approach: alpha = 1 - exp(-dt/tau); v += alpha * (target*direction - v)
EXPONENTIAL_APPROACH = 'exponential_approach'
# WORLD sets the velocity directly (stationary contact, launch impulse); the executor
# performs no translation of its own.
DIRECT = 'direct'

RELAXATIONS = (DAMPED_CRUISE, EXPONENTIAL_APPROACH, DIRECT)


@dataclass(frozen=True, slots=True)
class KinematicCaps:
    """Three separated ceilings, replacing one overloaded `fly.max_speed`.

    All three are **Class C** engineering values: numerical stability and simulator
    protection. None of them is a species flight maximum, and none is a biological
    escape-speed constant. See results/game/M1_8_B2B_I.md.

    * `ecological`      truncates commanded (later: sampled) ecological locomotion.
    * `legacy_accepted` the accepted constraint on threat-priority cruise, the neural
      escape impulse and the frozen M1.8-A lifecycle bounds. Held at the legacy value.
    * `safety_ceiling`  a global numerical guard applied last, on every path. It should
      never bind in normal play.

    M1.8-B2b-i sets all three to the legacy `fly.max_speed`, so every clamp reduces to
    the accepted arithmetic and the refactor is bit-identical.
    """

    ecological: float
    legacy_accepted: float
    safety_ceiling: float

    def __post_init__(self):
        for name in ('ecological', 'legacy_accepted', 'safety_ceiling'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError('kinematic cap must be positive and finite: ' + name)

    @classmethod
    def from_config(cls, config: dict, legacy_max_speed: float):
        """Absent keys fall back to the legacy ceiling, so LAB and GAME are unchanged."""
        block = config.get('kinematics', {})
        legacy = float(legacy_max_speed)
        return cls(float(block.get('ecological_cap_units_s', legacy)),
                   float(block.get('legacy_accepted_cap_units_s', legacy)),
                   float(block.get('safety_ceiling_units_s', legacy)))

    def effective(self, profile_cap: float) -> float:
        """The single clamp the executor applies: the tighter of profile and guard."""
        return min(profile_cap, self.safety_ceiling)


@dataclass(frozen=True, slots=True)
class KinematicProfile:
    """A request for body kinematics, separate from the context that produced it.

    `target_speed` is in world units/s and already resolved; `relaxation_rate` is a
    damping rate in 1/s for DAMPED_CRUISE and a time constant in seconds for
    EXPONENTIAL_APPROACH. `context` is an identity label for diagnostics only and never
    reaches a policy observation.
    """

    context: str
    relaxation: str = DIRECT
    target_speed: float = 0.0
    relaxation_rate: float = 0.0
    steering_rad_s: float = 0.0
    spontaneous_clock_rate: float = 1.0
    turn_gain: float = 1.0
    # `effective_cap` is what the executor clamps against. `profile_cap` and
    # `safety_ceiling` record which separated ceiling produced it, so the overloaded
    # legacy `max_speed` no longer has to mean three different things at once.
    effective_cap: float = math.inf
    profile_cap: float = math.inf
    safety_ceiling: float = math.inf
    clamp_speed: bool = False
    # ---- inert M1.8-B2 hooks; None means "use the accepted B1 behavior" -------------
    speed_envelope_bl_s: tuple[float, float] | None = None
    acceleration_limit: float | None = None
    deceleration_limit: float | None = None
    persistence_seconds: float | None = None

    def __post_init__(self):
        if self.relaxation not in RELAXATIONS:
            raise ValueError('unknown kinematic relaxation law: ' + str(self.relaxation))
        if not self.context:
            raise ValueError('kinematic profile requires a context identity')
        if self.effective_cap > min(self.profile_cap, self.safety_ceiling) + 1e-12:
            raise ValueError('effective cap must not exceed its components')
        for name in ('target_speed', 'relaxation_rate', 'steering_rad_s',
                     'spontaneous_clock_rate', 'turn_gain'):
            if not math.isfinite(getattr(self, name)):
                raise ValueError('kinematic profile requires finite ' + name)
        if self.target_speed < 0.0 or self.relaxation_rate < 0.0:
            raise ValueError('kinematic profile speeds and rates must be non-negative')
        if self.relaxation is EXPONENTIAL_APPROACH and self.relaxation_rate <= 0.0:
            raise ValueError('exponential approach requires a positive time constant')
        if self.speed_envelope_bl_s is not None:
            low, high = self.speed_envelope_bl_s
            if not 0.0 <= low <= high:
                raise ValueError('invalid speed envelope')


class KinematicResolver:
    """Maps behavioral context to a profile request.

    Pure: it holds only immutable body constants, performs no random draw and mutates
    no state, so introducing it cannot change any RNG call order.
    """

    def __init__(self, baseline_speed: float, max_speed: float, body_length: float,
                 damping: float, room_kinematic_scale: float = 1.0,
                 caps: 'KinematicCaps | None' = None):
        self.baseline_speed = float(baseline_speed)
        # Retained as the legacy alias for callers outside the kinematics layer; the
        # separated ceilings in `self.caps` are what this resolver actually applies.
        self.max_speed = float(max_speed)
        self.caps = caps if caps is not None else KinematicCaps(
            float(max_speed), float(max_speed), float(max_speed))
        self.body_length = float(body_length)
        self.damping = float(damping)
        # Class C simulator/environment mapping, not a measured biological constant.
        # 1.0 is the accepted no-op value; no literature magnitude has been adopted.
        self.room_kinematic_scale = float(room_kinematic_scale)
        if not math.isfinite(self.room_kinematic_scale) or self.room_kinematic_scale <= 0.0:
            raise ValueError('room_kinematic_scale must be positive and finite')

    def ecological_units(self, speed_bl_s: float) -> float:
        """BL/s -> body length -> ROOM mapping -> world units/s.

        The single site where the ROOM mapping is applied. At scale 1.0 the trailing
        multiply is exact in IEEE 754, so the accepted arithmetic is bit-identical.
        """
        return speed_bl_s*self.body_length*self.room_kinematic_scale

    def airborne(self, command, threat_priority: bool,
                 sampled_speed_bl_s: float | None = None) -> KinematicProfile:
        """Ordinary flight. Neural threat and pulses outrank the ecological command.

        `sampled_speed_bl_s` is the M1.8-B2b hook. None means "no sample taken; use the
        ecological command unchanged", which is the only behavior B2a produces.
        """
        if command is None or threat_priority:
            # Threat-priority cruise and the neural escape impulse share the accepted
            # legacy constraint; B2b-i does not change its effective value.
            cap = self.caps.legacy_accepted
            return KinematicProfile(
                context='baseline_cruise' if command is None else 'neural_priority',
                relaxation=DAMPED_CRUISE, target_speed=self.baseline_speed,
                relaxation_rate=self.damping, steering_rad_s=0.0,
                spontaneous_clock_rate=1.0, effective_cap=self.caps.effective(cap),
                profile_cap=cap, safety_ceiling=self.caps.safety_ceiling,
                clamp_speed=True)
        requested = (command.target_speed_bl_s if sampled_speed_bl_s is None
                     else float(sampled_speed_bl_s))
        cap = self.caps.ecological
        return KinematicProfile(
            context='ecology_' + command.state.lower(), relaxation=DAMPED_CRUISE,
            target_speed=min(cap, self.ecological_units(requested)),
            relaxation_rate=self.damping, steering_rad_s=command.steering_rad_s,
            spontaneous_clock_rate=command.spontaneous_clock_rate,
            effective_cap=self.caps.effective(cap), profile_cap=cap,
            safety_ceiling=self.caps.safety_ceiling, clamp_speed=True)

    def landing_approach(self, target_speed_bl_s: float, tau_seconds: float,
                         turn_rad_s: float) -> KinematicProfile:
        """Lifecycle-owned visual approach. Ecological intent is not executed here."""
        # Frozen M1.8-A: the lifecycle uses the accepted legacy constraint, and neither
        # the ROOM mapping nor the ecological cap applies to it.
        cap = self.caps.legacy_accepted
        return KinematicProfile(
            context='lifecycle_visual_approach', relaxation=EXPONENTIAL_APPROACH,
            target_speed=min(cap, target_speed_bl_s*self.body_length),
            relaxation_rate=float(tau_seconds), steering_rad_s=turn_rad_s,
            spontaneous_clock_rate=0.0, effective_cap=self.caps.effective(cap),
            profile_cap=cap, safety_ceiling=self.caps.safety_ceiling, clamp_speed=False)

    def lifecycle_direct(self, context: str, target_speed: float = 0.0) -> KinematicProfile:
        """Stationary contact and launch, where WORLD sets velocity directly."""
        cap = self.caps.legacy_accepted
        return KinematicProfile(context=context, relaxation=DIRECT,
                                target_speed=target_speed, spontaneous_clock_rate=0.0,
                                effective_cap=self.caps.effective(cap), profile_cap=cap,
                                safety_ceiling=self.caps.safety_ceiling,
                                clamp_speed=False)


class KinematicExecutor:
    """Turns a profile request into body velocity and yaw.

    Each branch reproduces the accepted pre-B1 arithmetic, including operand grouping,
    so the refactor is verifiable by bit-identical trace comparison rather than by a
    numerical tolerance.
    """

    @staticmethod
    def translate(profile: KinematicProfile, fly, dt: float) -> None:
        if profile.relaxation == DAMPED_CRUISE:
            # Damping relaxes velocity toward forward cruise, retaining inertia and
            # lateral escape momentum. Threat steering arrives only via Action.
            ax = profile.relaxation_rate * (profile.target_speed * math.cos(fly.heading) - fly.vx)
            ay = profile.relaxation_rate * (profile.target_speed * math.sin(fly.heading) - fly.vy)
            fly.vx += ax * dt
            fly.vy += ay * dt
        elif profile.relaxation == EXPONENTIAL_APPROACH:
            alpha = 1-math.exp(-dt/profile.relaxation_rate)
            fly.vx += alpha*(profile.target_speed*math.cos(fly.heading)-fly.vx)
            fly.vy += alpha*(profile.target_speed*math.sin(fly.heading)-fly.vy)
        else:
            return
        if profile.clamp_speed:
            speed = math.hypot(fly.vx, fly.vy)
            if speed > profile.effective_cap:
                fly.vx *= profile.effective_cap / speed
                fly.vy *= profile.effective_cap / speed

    @staticmethod
    def yaw_rate(profile: KinematicProfile, neural_turn: float, drift_turn: float,
                 pulse: float, dt: float, max_yaw_rate: float) -> float:
        """Compose the actuator yaw rate. The clip is a safety bound, not a behavior."""
        return float(np.clip(neural_turn + drift_turn
                             + profile.steering_rad_s * profile.turn_gain
                             + pulse / dt,
                             -max_yaw_rate, max_yaw_rate))


class KinematicSampler:
    """Owns the only kinematics random stream, kept out of the pure resolver.

        behavioral / ecological context
          -> KinematicSampler     (this class: may draw a context-dependent speed)
          -> KinematicResolver    (pure: request -> profile)
          -> KinematicProfile
          -> KinematicExecutor
          -> physics

    M1.8-B2a is inert. `target_speed_bl_s` returns None on every call, meaning "no
    sample; use the ecological command unchanged", and no draw is ever taken. The
    stream is nonetheless seeded and reset deterministically so that B2b can begin
    drawing without disturbing any existing stream's call order.
    """

    # Unique among the seeded streams: flight +3907, ecology +7013, spawn +8191,
    # lifecycle +18001. Asserted pairwise-unique by test_game_kinematics.
    SEED_OFFSET = 24593

    def __init__(self, seed: int):
        self.reset(seed)

    def reset(self, seed: int) -> None:
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed + self.SEED_OFFSET)
        self.initial_state = copy.deepcopy(self.rng.bit_generator.state)
        self.draws = 0

    @property
    def untouched(self) -> bool:
        """True while no draw has been taken, so B2a inertness is machine-checkable."""
        return self.draws == 0 and self.rng.bit_generator.state == self.initial_state

    def target_speed_bl_s(self, command, threat_priority: bool) -> float | None:
        """B2a: never samples. B2b will draw here for SAMPLED_CONTEXTS only."""
        return None
