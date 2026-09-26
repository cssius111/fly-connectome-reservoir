"""Policy adapter for learned / scripted maneuver policies, plus non-learning controls.

`ManeuverPolicy` implements the existing `Policy` protocol. Per tick it:

1. builds the whitelisted observation from the `MotorState` and its own pre-action behavior
   state (`ObservationEncoder`; the model never sees the MotorState itself);
2. asks its decision model for a maneuver index (`act(obs, rng, explore)`);
3. converts the maneuver to an `Action` through `ManeuverActuator` (escape refractory);
4. optionally records (obs, index) for TRAIN-mode learning. Rewards are never passed here.

Non-learning decision models (controls and exploit probes) use the same observation and
action contracts, so they are directly comparable with a future learned model.
The accepted baseline (`FixedEscapePolicy`, N4B1C) is NOT wrapped: it is built unchanged by
`game.session.build_policy`.
"""
from __future__ import annotations

import numpy as np

from .contracts import MANEUVERS, N_MANEUVERS, ManeuverActuator, ObservationEncoder
from ..action import MotorState

INDEX = {m.name: i for i, m in enumerate(MANEUVERS)}


class ManeuverPolicy:
    def __init__(self, model, tick_seconds: float, refractory_seconds: float, seed: int = 0,
                 explore: bool = False, record: bool = False):
        self.model = model
        self.encoder = ObservationEncoder()
        self.actuator = ManeuverActuator(tick_seconds, refractory_seconds)
        self.explore = bool(explore)
        self.record = bool(record)
        self.base_seed = int(seed)
        self.reseed(seed)
        self.reset()

    def reseed(self, seed: int):
        self.rng = np.random.default_rng(int(seed))

    def reset(self):
        self.encoder.reset()
        self.actuator.reset()
        self.trajectory = []
        self.last_index = 0
        if hasattr(self.model, 'reset'):
            self.model.reset()

    def decide(self, motor: MotorState):
        if type(motor) is not MotorState:
            raise TypeError('ManeuverPolicy accepts only MotorState')
        obs = self.encoder.encode(motor, self.actuator.behavior_state)
        index, _ = self.model.act(obs, self.rng, self.explore)
        self.last_index = int(index)
        if self.record:
            self.trajectory.append((obs, int(index)))
        return self.actuator.act(int(index))

    def diagnostics(self):
        # Same key set as FixedEscapePolicy.diagnostics() (frozen recorder schema).
        return {'escape_threshold': 0.0,
                'refractory_seconds': self.actuator.cooldown * 0.02,
                'behavior_state': self.actuator.behavior_state,
                'escape_strength': self.actuator.last_escape_strength}


# ----------------------------------------------------------------- decision models ---
class NoEscapeModel:
    name = 'no_escape'

    def act(self, obs, rng, explore):
        return INDEX['NONE'], {}


class RandomLegalModel:
    """Uniform over all maneuvers at a fixed decision rate (every tick)."""
    name = 'random_legal'

    def act(self, obs, rng, explore):
        return int(rng.integers(N_MANEUVERS)), {}


class FixedManeuverModel:
    """Simple non-learning rule on whitelisted signals only: when the summed DNp01 trace of
    the current frame is >= 1.45 (the accepted sustained threshold), escape away from the
    more active DNp01 side; otherwise do nothing. Unlike N4B1C it has no dual-path timing."""
    name = 'fixed_maneuver'

    def act(self, obs, rng, explore):
        left, right = obs[1], obs[2]            # t0.neural.dnp01_left / dnp01_right
        if left + right >= 1.45:
            return (INDEX['ESCAPE_RIGHT'] if left > right else INDEX['ESCAPE_LEFT'] if right > left
                    else INDEX['ESCAPE_FORWARD']), {}
        return INDEX['NONE'], {}


class AlwaysEscapeProbe:
    """Exploit probe: escapes whenever the refractory allows (drives permanent high speed)."""
    name = 'probe_always_escape'

    def act(self, obs, rng, explore):
        return INDEX['ESCAPE_FORWARD'], {}


class ConstantTurnProbe:
    """Exploit probe: turns right on every tick (circling)."""
    name = 'probe_constant_turn'

    def act(self, obs, rng, explore):
        return INDEX['TURN_RIGHT'], {}


class ClockEscapeProbe:
    """Exploit probe (M2.1): escapes on a fixed internal clock (every 3.0 s from reset,
    starting at 2.0 s), independent of any signal. Tests whether threat timing can be memorized."""
    name = 'probe_clock_escape'

    def __init__(self):
        self.reset()

    def reset(self):
        self.t = 0

    def act(self, obs, rng, explore):
        self.t += 1
        return (INDEX['ESCAPE_FORWARD'] if self.t >= 100 and (self.t - 100) % 150 == 0 else INDEX['NONE']), {}


class ModelDecision:
    """Adapter for MLPPolicyModel (explore -> sample, otherwise greedy)."""

    def __init__(self, model):
        self.model = model
        self.name = 'mlp'

    def act(self, obs, rng, explore):
        return self.model.act(obs, rng, explore)


CONTROLS = {'no_escape': NoEscapeModel, 'random_legal': RandomLegalModel, 'fixed_maneuver': FixedManeuverModel}
PROBES = {'probe_always_escape': AlwaysEscapeProbe, 'probe_constant_turn': ConstantTurnProbe}
PROBES_V2 = {**PROBES, 'probe_clock_escape': ClockEscapeProbe}
