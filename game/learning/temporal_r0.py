"""M2.4-R0 temporal action abstraction feasibility: worker-side recording code (research only).

Nothing here changes the observation contract, the 11 maneuvers, reward v2, the attacker
distributions, MaleCNS, the Retina / encoder, physics, lifecycle or the accepted runtime. It only:

* records per-tick decision and executed-maneuver streams of existing policies through the frozen
  M2.1 trial / background code (a read-only tick hook, as in training / evaluation);
* runs the mapped N4B1C teacher under a HYPOTHETICAL decision cadence (`HeldTeacherPolicy`): the
  teacher still observes every 20 ms tick (its decoder integrates spikes every tick), but a new
  maneuver is only selected every `period` ticks and held in between. Two selection variants:

    sampled   the teacher's label at the decision tick (events between decisions are lost)
    latched   the highest-priority label emitted since the previous decision (escape > alert
              saccade > turn > none; earliest occurrence within the class), i.e. an escape is
              delayed to the next decision tick instead of lost

  Holding uses the existing actuator semantics unchanged: a held escape is executed once and then
  suppressed by the 0.4 s refractory; a held alert saccade is ignored while its pulse runs; a held
  turn keeps commanding yaw.

Privileged context in the hook (committed strike, contact, lifecycle mode, click) is analysis-only
and never reaches a policy.
"""
from __future__ import annotations

import os

import numpy as np

from . import runmode, runner, trials
from .contracts import MANEUVERS
from .teacher import INDEX, MappedTeacherPolicy, map_action

FAMILIES = {f.name: f for f in trials.THREAT_FAMILIES}
BACKGROUND = {c.name: c for c in trials.BACKGROUND_FAMILIES}
NAMES = [m.name for m in MANEUVERS]


def category_rank(index: int) -> int:
    m = MANEUVERS[int(index)]
    if m.escape:
        return 3
    if m.saccade and not m.turn:
        return 2
    if m.turn:
        return 1
    return 0


def executed_index(action) -> int:
    """Executed Action -> maneuver category (teacher mapping rule; backward escape kept distinct)."""
    if action.escape and action.strength > 0 and abs(action.lateral) < 0.3 and action.forward < 0:
        return INDEX['ESCAPE_BACKWARD']
    return map_action(action)


class HeldTeacherPolicy(MappedTeacherPolicy):
    """Mapped N4B1C teacher with a hypothetical decision cadence (period 1 = the 50 Hz reference)."""

    def __init__(self, teacher, tick_seconds, refractory_seconds, period=1, variant='sampled'):
        if variant not in ('sampled', 'latched') or int(period) < 1:
            raise ValueError('invalid cadence')
        self.period, self.variant = int(period), variant
        super().__init__(teacher, tick_seconds, refractory_seconds, record=False)

    def reset(self):
        super().reset()
        self.k = 0
        self.held = INDEX['NONE']
        self.pending = None
        self.labels, self.chosen, self.decision_tick = [], [], []

    def decide(self, motor):
        self.encoder.encode(motor, self.actuator.behavior_state)       # keep encoder history identical
        label = map_action(self.teacher.decide(motor))                  # teacher sees every tick
        if self.variant == 'latched' and (self.pending is None or category_rank(label) > category_rank(self.pending)):
            self.pending = label
        is_decision = self.k % self.period == 0
        if is_decision:
            self.held = label if self.variant == 'sampled' else self.pending
            self.pending = None
        self.k += 1
        self.last_index = self.held
        self.labels.append(label)
        self.chosen.append(self.held)
        self.decision_tick.append(is_decision)
        return self.actuator.act(self.held)


class RecordingPassthrough:
    """Wraps the accepted FixedEscapePolicy unchanged and records the mapped category of its Action."""

    def __init__(self, inner):
        self.inner = inner
        self.chosen = []

    def reset(self):
        self.inner.reset()
        self.chosen = []

    def decide(self, motor):
        a = self.inner.decide(motor)
        self.chosen.append(executed_index(a))
        return a

    def __getattr__(self, name):
        return getattr(self.inner, name)


_W = {}


def worker_init():
    os.environ.setdefault('NUMBA_NUM_THREADS', '1')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    from ..session import build_brain
    cfg = runner.load_config()
    _W['config'] = cfg
    _W['brain'] = build_brain(cfg, runner.ROOT)
    _W['sessions'] = {}


def _policy(spec):
    from ..session import Session, build_policy
    from .model import MLPPolicyModel
    from .policies import ManeuverPolicy, ModelDecision
    cfg = _W['config']
    tick, refr = float(cfg['sim']['tick_seconds']), float(cfg['policy']['refractory_seconds'])
    kind = spec['kind']
    if kind == 'accepted':
        pol = RecordingPassthrough(build_policy(cfg, runner.ROOT)[0])
    elif kind == 'teacher':
        pol = HeldTeacherPolicy(build_policy(cfg, runner.ROOT)[0], tick, refr, spec['period'], spec['variant'])
    elif kind == 'mlp':
        m = MLPPolicyModel(seed=0)
        for k, v in spec['params'].items():
            m.params[k] = np.array(v, dtype=np.float64)
        pol = ManeuverPolicy(ModelDecision(m, stochastic=True), tick, refr, record=True)
    else:
        raise ValueError(kind)
    return Session(cfg, brain=_W['brain'], policy=pol, seed=runmode.EVAL_SEED_BASE + 1, mode='evaluation', root=runner.ROOT)


def _session(name, spec):
    if name not in _W['sessions']:
        _W['sessions'][name] = _policy(spec)
    return _W['sessions'][name]


def _chosen(pol, n):
    if isinstance(pol, (HeldTeacherPolicy, RecordingPassthrough)):
        c = list(pol.chosen)
    else:
        c = [a for _, a in pol.trajectory]
    if len(c) != n:
        raise RuntimeError('decision stream misaligned (%d vs %d)' % (len(c), n))
    return np.array(c, np.int8)


def record_task(args):
    """Run episodes for one policy configuration; return M2.1 records + per-tick streams."""
    from ..edge_analysis import edge_diagnostics
    name, spec, episodes = args
    s = _session(name, spec)
    pol = s.policy
    out = []
    for kind, fam, level, seed in episodes:
        w = s.world
        r = {'exec': [], 'committed': [], 'wall': [], 'near_wall': [], 'life': [], 'resolved': [], 'hit': []}

        def hook(session, t, events, action, committed_before, horizontal, mode_before, resolved_now):
            r['exec'].append(executed_index(action))
            r['committed'].append(bool(committed_before))
            r['wall'].append(bool(w.wall_contact or w.object_contact))
            r['near_wall'].append(bool(edge_diagnostics(w)['fly_near_wall']))
            life = w.lifecycle
            r['life'].append(0 if life is None else (2 if life.stationary else (1 if life.mode not in ('AIRBORNE', 'NONE') else 0)))
            r['resolved'].append(bool(resolved_now))
            r['hit'].append(bool(events.hit))

        if hasattr(pol, 'record'):
            pol.record = True
        if kind == 'threat':
            rec = trials.run_threat_trial(s, FAMILIES[fam], level, seed, runmode.TRAIN, tick_hook=hook)
            rec['group'] = 'threat:%s:%s' % (fam, level)
        else:
            rr = trials.run_background(s, BACKGROUND[fam], seed, runmode.TRAIN, tick_hook=hook)
            rec = {'metrics': rr['metrics'], 'trajectory_sha256': rr['trajectory_sha256'], 'group': 'background:%s' % fam}
        rec.update({'kind': kind, 'seed': seed})
        n = len(r['exec'])
        stream = {k: np.array(v, np.int8 if k in ('exec', 'life') else bool) for k, v in r.items()}
        stream['chosen'] = _chosen(pol, n)
        if isinstance(pol, HeldTeacherPolicy):
            stream['label'] = np.array(pol.labels, np.int8)
            stream['decision'] = np.array(pol.decision_tick, bool)
        click = rec.get('click_s') if kind == 'threat' else None
        stream['click_index'] = -1 if click is None else int(round(click / 0.02))
        out.append((rec, stream))
    return out
