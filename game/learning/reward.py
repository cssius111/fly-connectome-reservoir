"""Proposed reward terms (research only; no training uses them in M2.0).

The reward is computed OUTSIDE the policy from privileged world state. It is never passed to
`ManeuverPolicy.decide`, never enters the observation, and changing the reward cannot change
an EVAL episode (a test checks this).

Every term is interpretable and is reported separately. Weights are proposals, to be frozen
before any training run and recorded in its manifest.

| term | per | definition | purpose / exploit it blocks |
|---|---|---|---|
| death | episode | -10 when the fly is hit | primary objective |
| strike_survived | committed strike | +1 when a committed strike resolves as a miss | rewards surviving real attacks, not passive time |
| unnecessary_escape | escape | -0.2 per executed escape while no strike is committed and the paddle is > 310 units away horizontally | blocks escape spam / permanent max speed |
| speed_cost | second | -0.05 * max(0, speed / cruise - 1.5)^2 | blocks permanent max-speed flight |
| wall_contact | second | -0.5 while in wall or object contact | blocks wall hugging / sliding |
| turn_cost | second / request | -0.01 * abs(turn) per second, -0.01 per saccade request | blocks constant turning |

Deliberately absent:

* no survival-time reward: a timeout gives nothing, and episodes are truncated, not
  terminated, at the horizon, so no timeout exploit exists;
* no term for landing, perching or feeding: the reward is neutral to ecological states, so
  avoiding them earns nothing (lifecycle behaviour is monitored as a diagnostic instead);
* no distance or proximity shaping: it would reward keeping away from the paddle using
  information the policy cannot observe.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

NEAR = 310.0


@dataclass(frozen=True)
class RewardSpec:
    death: float = -10.0
    strike_survived: float = 1.0
    unnecessary_escape: float = -0.2
    speed_cost: float = -0.05
    speed_free_multiple: float = 1.5
    wall_contact: float = -0.5
    turn_cost: float = -0.01
    saccade_cost: float = -0.01
    version: str = 'm2.0-reward-v1'

    def as_dict(self):
        return asdict(self)


class RewardTracker:
    """Accumulates per-term rewards from privileged world state (environment side)."""

    def __init__(self, spec: RewardSpec, dt: float):
        self.spec, self.dt = spec, dt
        self.totals = {k: 0.0 for k in ('death', 'strike_survived', 'unnecessary_escape', 'speed_cost',
                                        'wall_contact', 'turn_cost')}
        self.per_tick = []

    def step(self, world, action, events, committed_before, horizontal):
        s = self.spec
        r = {k: 0.0 for k in self.totals}
        if events.hit:
            r['death'] = s.death
        elif events.strike_resolved:
            r['strike_survived'] = s.strike_survived
        if action.escape and action.strength > 0 and not committed_before and horizontal > NEAR:
            r['unnecessary_escape'] = s.unnecessary_escape
        cruise = world.baseline_speed
        excess = max(0.0, math.hypot(world.fly.vx, world.fly.vy) / cruise - s.speed_free_multiple)
        r['speed_cost'] = s.speed_cost * excess * excess * self.dt
        if world.wall_contact or world.object_contact:
            r['wall_contact'] = s.wall_contact * self.dt
        r['turn_cost'] = s.turn_cost * abs(action.turn) * self.dt + (s.saccade_cost if action.saccade else 0.0)
        for k, v in r.items():
            self.totals[k] += v
        total = sum(r.values())
        self.per_tick.append(total)
        return total

    def summary(self):
        return {'total': sum(self.totals.values()), **self.totals}
