"""Observation and action contracts for learned policies.

Observation contract (the M1.5 policy whitelist, unchanged):

* neural: dnp01_left, dnp01_right, dna02_left, dna02_right (MotorState scalars only; the
  full descending-neuron `trace` array in MotorState is NOT exposed);
* motion: forward_speed, lateral_speed, yaw_rate, saccade_remaining (MotionState);
* behavior_state: the policy's own pre-action state, CALM / ALERT / ESCAPE (one-hot);
* history: at most 4 preceding frames of the same fields.

Every frame is built with `game.recording.observation_frame`, the existing whitelist
function, so the learned-policy path and the recorder share one definition. Nothing else can
enter: this module imports no world, perception, room, lifecycle, ecology or session code,
and the encoder accepts only a `MotorState` and a behavior-state string.

Action contract: a small discrete set of maneuvers, each mapped to the existing body-frame
`Action` (impulse direction, turn command, saccade request, strength). No maneuver specifies
x / y movement; the world's flight dynamics, wall handling, lifecycle and brain stepping
execute every action. The actuator enforces the accepted 0.4 s escape refractory, so an
escape cannot be re-triggered every tick.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math

import numpy as np

from ..action import Action, MotorState
from ..recording import NEURAL_FIELDS, observation_frame

MOTION_FIELDS = ('forward_speed', 'lateral_speed', 'yaw_rate', 'saccade_remaining')
BEHAVIOR_STATES = ('CALM', 'ALERT', 'ESCAPE')
HISTORY_LENGTH = 4
# Per frame: validity flag, 4 neural, 4 motion, 3 behavior-state one-hot.
FRAME_FIELDS = (('valid',) + tuple('neural.' + k for k in NEURAL_FIELDS)
                + tuple('motion.' + k for k in MOTION_FIELDS)
                + tuple('behavior_state.' + s for s in BEHAVIOR_STATES))
FRAME_SIZE = len(FRAME_FIELDS)
OBSERVATION_FIELDS = tuple('t0.' + f for f in FRAME_FIELDS) + tuple(
    't-%d.%s' % (k, f) for k in range(1, HISTORY_LENGTH + 1) for f in FRAME_FIELDS)
OBSERVATION_SIZE = len(OBSERVATION_FIELDS)

# Documented exclusions (the tests check that none of these can reach the encoder).
FORBIDDEN = ('mouse / pointer coordinates', 'swatter coordinates, phase, height or face',
             'world coordinates or heading', 'distance to the paddle or walls', 'collision state',
             'Retina theta / theta_dot / azimuth', 'LC4 / LPLC2 activity or encoder drive',
             'the full descending-neuron trace (MotorState.trace)',
             'lifecycle / contact / surface variables', 'odor / food / perch variables',
             'hidden geometry', 'target direction')

OBSERVATION_SCHEMA = {
    'version': 'm2.0-observation-v1',
    'fields': list(OBSERVATION_FIELDS), 'size': OBSERVATION_SIZE,
    'history_length': HISTORY_LENGTH, 'frame_fields': list(FRAME_FIELDS),
    'source': 'game.recording.observation_frame (the M1.5 whitelist)', 'forbidden': list(FORBIDDEN),
    'behavior_state': 'the policy adapter\'s own pre-action state (CALM / ALERT / ESCAPE)',
}


class ObservationEncoder:
    """Whitelisted frames -> fixed-order float vector (current frame + 4 history frames)."""

    def __init__(self):
        self.history = deque(maxlen=HISTORY_LENGTH)

    def reset(self):
        self.history.clear()

    @staticmethod
    def frame_vector(frame: dict) -> np.ndarray:
        if set(frame) != {'neural', 'motion', 'behavior_state'} or set(frame['neural']) != set(NEURAL_FIELDS) \
                or set(frame['motion']) != set(MOTION_FIELDS) or frame['behavior_state'] not in BEHAVIOR_STATES:
            raise ValueError('observation frame is not a whitelisted frame')
        v = [1.0] + [float(frame['neural'][k]) for k in NEURAL_FIELDS] + [float(frame['motion'][k]) for k in MOTION_FIELDS]
        v += [1.0 if frame['behavior_state'] == s else 0.0 for s in BEHAVIOR_STATES]
        out = np.array(v, dtype=np.float64)
        if not np.all(np.isfinite(out)):
            raise ValueError('observation values must be finite')
        return out

    def encode(self, motor: MotorState, behavior_state: str) -> np.ndarray:
        """Observation for the current decision; afterwards the frame joins the history."""
        if type(motor) is not MotorState:
            raise TypeError('the observation encoder accepts only MotorState')
        if behavior_state not in BEHAVIOR_STATES:
            raise ValueError('behavior_state must be CALM, ALERT or ESCAPE')
        frame = observation_frame(motor, behavior_state)       # the shared whitelist
        parts = [self.frame_vector(frame)]
        hist = list(self.history)[::-1]                          # most recent first
        for k in range(HISTORY_LENGTH):
            parts.append(self.frame_vector(hist[k]) if k < len(hist) else np.zeros(FRAME_SIZE))
        self.history.append(frame)
        obs = np.concatenate(parts)
        obs.setflags(write=False)
        assert obs.shape == (OBSERVATION_SIZE,)
        return obs


# ----------------------------------------------------------------- actions ---
@dataclass(frozen=True)
class Maneuver:
    name: str
    escape: bool = False
    lateral: float = 0.0
    forward: float = 0.0
    turn: float = 0.0
    saccade: float = 0.0
    strength: float = 1.0


# Escape directions are body-frame impulse directions; the accepted forward bias (0.35)
# is kept for the lateral escapes. Saccade signs follow the Action convention (+ = right).
MANEUVERS = (
    Maneuver('NONE'),
    Maneuver('TURN_LEFT', turn=-0.5),
    Maneuver('TURN_RIGHT', turn=0.5),
    Maneuver('ALERT_SACCADE_LEFT', saccade=-0.6),
    Maneuver('ALERT_SACCADE_RIGHT', saccade=0.6),
    Maneuver('ESCAPE_LEFT', escape=True, lateral=-1.0, forward=0.35, saccade=-1.0),
    Maneuver('ESCAPE_RIGHT', escape=True, lateral=1.0, forward=0.35, saccade=1.0),
    Maneuver('ESCAPE_FORWARD', escape=True, lateral=0.0, forward=1.0),
    Maneuver('ESCAPE_BACKWARD', escape=True, lateral=0.0, forward=-1.0),
    Maneuver('ESCAPE_LEFT_HALF', escape=True, lateral=-1.0, forward=0.35, saccade=-0.5, strength=0.5),
    Maneuver('ESCAPE_RIGHT_HALF', escape=True, lateral=1.0, forward=0.35, saccade=0.5, strength=0.5),
)
N_MANEUVERS = len(MANEUVERS)
ACTION_SCHEMA = {
    'version': 'm2.0-maneuver-v1',
    'maneuvers': [m.__dict__ for m in MANEUVERS],
    'mapping': 'each maneuver maps to one game.action.Action (body-frame impulse direction, turn in [-1, 1] '
               'scaled by the world turn rate, saccade request in [-1, 1], strength in [0, 1])',
    'escape_refractory_seconds': 'from the accepted config policy.refractory_seconds (0.4 s); escape maneuvers '
                                 'inside the refractory are executed as NONE and counted as suppressed',
    'no_xy': 'no maneuver specifies world x / y movement; flight dynamics, walls, lifecycle and brain stepping '
             'are always executed by the world',
}


class ManeuverActuator:
    """Maneuver index -> Action, with the accepted escape refractory and the policy's own
    behavior state (CALM / ALERT / ESCAPE), which the session uses for ecology / lifecycle."""

    def __init__(self, tick_seconds: float, refractory_seconds: float, alert_hold_seconds: float = 0.2):
        self.refractory_ticks = int(round(refractory_seconds / tick_seconds))
        self.alert_hold_ticks = max(1, int(round(alert_hold_seconds / tick_seconds)))
        self.reset()

    def reset(self):
        self.cooldown = 0
        self.alert = 0
        self.suppressed = 0
        self.last_escape_strength = 0.0

    @property
    def behavior_state(self) -> str:
        if self.cooldown > 0:
            return 'ESCAPE'
        return 'ALERT' if self.alert > 0 else 'CALM'

    def act(self, index: int) -> Action:
        if not (isinstance(index, (int, np.integer)) and 0 <= int(index) < N_MANEUVERS):
            raise ValueError('maneuver index out of range')
        m = MANEUVERS[int(index)]
        if self.cooldown > 0:
            self.cooldown -= 1
        self.alert = max(0, self.alert - 1)
        if m.escape and self.cooldown > 0:
            self.suppressed += 1
            m = MANEUVERS[0]
        if m.escape:
            self.cooldown = self.refractory_ticks
            self.last_escape_strength = m.strength
            return Action(escape=True, lateral=m.lateral, forward=m.forward, turn=0.0, strength=m.strength,
                          saccade=m.saccade)
        if abs(m.turn) > 0.0 or m.saccade:
            self.alert = self.alert_hold_ticks
        if self.cooldown == 0:
            self.last_escape_strength = 0.0
        return Action(turn=m.turn, saccade=m.saccade)
