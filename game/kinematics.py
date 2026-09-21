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
import math

import numpy as np

# Ordinary airborne cruise: a = k * (target*direction - v); v += a * dt
DAMPED_CRUISE = 'damped_cruise'
# Lifecycle landing approach: alpha = 1 - exp(-dt/tau); v += alpha * (target*direction - v)
EXPONENTIAL_APPROACH = 'exponential_approach'
# WORLD sets the velocity directly (stationary contact, launch impulse); the executor
# performs no translation of its own.
DIRECT = 'direct'

RELAXATIONS = (DAMPED_CRUISE, EXPONENTIAL_APPROACH, DIRECT)


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
    max_speed: float = math.inf
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
                 damping: float):
        self.baseline_speed = float(baseline_speed)
        self.max_speed = float(max_speed)
        self.body_length = float(body_length)
        self.damping = float(damping)

    def airborne(self, command, threat_priority: bool) -> KinematicProfile:
        """Ordinary flight. Neural threat and pulses outrank the ecological command."""
        if command is None or threat_priority:
            return KinematicProfile(
                context='baseline_cruise' if command is None else 'neural_priority',
                relaxation=DAMPED_CRUISE, target_speed=self.baseline_speed,
                relaxation_rate=self.damping, steering_rad_s=0.0,
                spontaneous_clock_rate=1.0, max_speed=self.max_speed, clamp_speed=True)
        return KinematicProfile(
            context='ecology_' + command.state.lower(), relaxation=DAMPED_CRUISE,
            target_speed=min(self.max_speed, command.target_speed_bl_s*self.body_length),
            relaxation_rate=self.damping, steering_rad_s=command.steering_rad_s,
            spontaneous_clock_rate=command.spontaneous_clock_rate,
            max_speed=self.max_speed, clamp_speed=True)

    def landing_approach(self, target_speed_bl_s: float, tau_seconds: float,
                         turn_rad_s: float) -> KinematicProfile:
        """Lifecycle-owned visual approach. Ecological intent is not executed here."""
        return KinematicProfile(
            context='lifecycle_visual_approach', relaxation=EXPONENTIAL_APPROACH,
            target_speed=min(self.max_speed, target_speed_bl_s*self.body_length),
            relaxation_rate=float(tau_seconds), steering_rad_s=turn_rad_s,
            spontaneous_clock_rate=0.0, max_speed=self.max_speed, clamp_speed=False)

    def lifecycle_direct(self, context: str, target_speed: float = 0.0) -> KinematicProfile:
        """Stationary contact and launch, where WORLD sets velocity directly."""
        return KinematicProfile(context=context, relaxation=DIRECT,
                                target_speed=target_speed, spontaneous_clock_rate=0.0,
                                max_speed=self.max_speed, clamp_speed=False)


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
            if speed > profile.max_speed:
                fly.vx *= profile.max_speed / speed
                fly.vy *= profile.max_speed / speed

    @staticmethod
    def yaw_rate(profile: KinematicProfile, neural_turn: float, drift_turn: float,
                 pulse: float, dt: float, max_yaw_rate: float) -> float:
        """Compose the actuator yaw rate. The clip is a safety bound, not a behavior."""
        return float(np.clip(neural_turn + drift_turn
                             + profile.steering_rad_s * profile.turn_gain
                             + pulse / dt,
                             -max_yaw_rate, max_yaw_rate))
