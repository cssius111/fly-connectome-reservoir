"""M2.3 teacher: the accepted N4B1C FixedEscapePolicy expressed in the frozen 11-maneuver contract.

Policy-side module (imports only game.action and the learning contracts). The teacher decides
from the MotorState exactly as in the accepted runtime; its continuous Action is mapped to one
of the 11 frozen maneuvers by the fixed rule below, and the MAPPED maneuver is executed through
the same ManeuverActuator as a learner (0.4 s escape refractory). The learner's observation is
built by the frozen ObservationEncoder from the MotorState and the actuator's own behavior
state; no teacher internal (thresholds, windows, spike memory, smoothed side evidence) and no
world information enters it.

Mapping rule (fixed before any BC training; precedence escape > saccade > turn > none):
    escape:  abs(lateral) < 0.3 -> ESCAPE_FORWARD
             lateral < 0 -> ESCAPE_LEFT (strength >= 0.75) or ESCAPE_LEFT_HALF (strength < 0.75)
             lateral > 0 -> ESCAPE_RIGHT / ESCAPE_RIGHT_HALF
    saccade (alert, no escape): sign -> ALERT_SACCADE_LEFT / ALERT_SACCADE_RIGHT
    turn:    abs(turn) >= 0.25 -> TURN_LEFT / TURN_RIGHT
    else:    NONE
The accepted policy's escape impulse points along lateral x right + 0.35 x forward, so the
lateral maneuvers (lateral +/-1, forward 0.35) match it when abs(lateral) is large; a small
lateral contrast is mapped to the forward escape.
"""
from __future__ import annotations

from .contracts import MANEUVERS, ManeuverActuator, ObservationEncoder
from ..action import FixedEscapePolicy, MotorState

INDEX = {m.name: i for i, m in enumerate(MANEUVERS)}
MAPPING_RULE = __doc__.split('Mapping rule')[1].split('The accepted policy')[0].strip()


def map_action(a) -> int:
    if a.escape and a.strength > 0:
        if abs(a.lateral) < 0.3:
            return INDEX['ESCAPE_FORWARD']
        side = 'LEFT' if a.lateral < 0 else 'RIGHT'
        return INDEX['ESCAPE_%s%s' % (side, '' if a.strength >= 0.75 else '_HALF')]
    if a.saccade:
        return INDEX['ALERT_SACCADE_LEFT' if a.saccade < 0 else 'ALERT_SACCADE_RIGHT']
    if abs(a.turn) >= 0.25:
        return INDEX['TURN_LEFT' if a.turn < 0 else 'TURN_RIGHT']
    return INDEX['NONE']


class MappedTeacherPolicy:
    """Policy protocol: N4B1C decides, the mapped maneuver is executed. Optionally records
    (observation, teacher label) pairs for behaviour cloning."""

    def __init__(self, teacher: FixedEscapePolicy, tick_seconds: float, refractory_seconds: float, record=False):
        if type(teacher) is not FixedEscapePolicy:
            raise TypeError('the teacher must be the accepted FixedEscapePolicy')
        self.teacher = teacher
        self.encoder = ObservationEncoder()
        self.actuator = ManeuverActuator(tick_seconds, refractory_seconds)
        self.record = record
        self.reset()

    def reset(self):
        self.teacher.reset()
        self.encoder.reset()
        self.actuator.reset()
        self.samples = []
        self.last_index = 0

    def reseed(self, seed):          # deterministic; interface parity with ManeuverPolicy
        pass

    def decide(self, motor: MotorState):
        if type(motor) is not MotorState:
            raise TypeError('MappedTeacherPolicy accepts only MotorState')
        obs = self.encoder.encode(motor, self.actuator.behavior_state)   # learner-visible input
        label = map_action(self.teacher.decide(motor))                    # teacher label
        self.last_index = label
        if self.record:
            self.samples.append((obs, label))
        return self.actuator.act(label)

    def diagnostics(self):
        return {'escape_threshold': 0.0, 'refractory_seconds': self.actuator.cooldown * 0.02,
                'behavior_state': self.actuator.behavior_state, 'escape_strength': self.actuator.last_escape_strength}
