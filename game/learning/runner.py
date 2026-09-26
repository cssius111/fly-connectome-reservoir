"""Episode runner, frozen benchmark suite and run manifest.

The runner drives an unchanged `Session`: every tick the scenario (environment side) sets the
pointer / strike, the session projects the Retina, steps the brain, asks the policy for an
Action through the `Policy` protocol and advances the world (flight, walls, lifecycle). The
runner only observes: metrics and reward are computed from world state after the tick and are
never passed to the policy.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from . import contracts, runmode
from .metrics import STRIKE_PHASES, EpisodeRecorder
from .policies import CONTROLS, PROBES, PROBES_V2, ManeuverPolicy
from .reward import RewardSpec, RewardTracker
from .scenarios import SCENARIO_INDEX, SCENARIOS

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / 'game_room_config.json'
DT = 0.02

# ----------------------------------------------------------------- frozen suite ---
SUITE_VERSION = 'm2.0-benchmark-v1'
SEEDS_PER_SCENARIO = 20
SUITE = [{'scenario': cls.name, 'index': SCENARIO_INDEX[cls.name], 'seconds': cls.seconds,
          'max_seconds': cls.max_seconds, 'eval_seeds': runmode.eval_seeds(SCENARIO_INDEX[cls.name], SEEDS_PER_SCENARIO)}
         for cls in SCENARIOS]
BENCHMARK_POLICIES = ('baseline_n4b1c',) + tuple(CONTROLS) + tuple(PROBES)


def suite_hash():
    return hashlib.sha256(json.dumps({'version': SUITE_VERSION, 'suite': SUITE,
                                      'policies': BENCHMARK_POLICIES}, sort_keys=True).encode()).hexdigest()


# ----------------------------------------------------------------- sessions ---
def load_config():
    from ..session import load_config as _load
    return _load(CONFIG_PATH)


def make_policy(name, config, model=None, seed=0, mode=runmode.EVAL):
    """The accepted baseline is built unchanged by build_policy; everything else goes through
    the ManeuverPolicy adapter."""
    from ..session import build_policy
    if name == 'baseline_n4b1c':
        return build_policy(config, ROOT)[0]
    tick = float(config['sim']['tick_seconds'])
    refractory = float(config['policy']['refractory_seconds'])
    if name == 'mlp':
        from .policies import ModelDecision
        decision = ModelDecision(model)
    else:
        decision = {**CONTROLS, **PROBES_V2}[name]()
    return ManeuverPolicy(decision, tick, refractory, seed=seed, explore=mode.explore, record=mode.updates_allowed)


def make_session(policy, config):
    from ..session import Session
    return Session(config, policy=policy, seed=runmode.EVAL_SEED_BASE + 1, mode='evaluation', root=ROOT)


# ----------------------------------------------------------------- episode ---
def run_episode(session, scenario_cls, seed, mode, reward_spec=RewardSpec(), model=None, keep_rows=False,
                tick_hook=None):
    mode.check_seed(seed)
    policy = session.policy
    session.reset(seed)
    if isinstance(policy, ManeuverPolicy):
        policy.reseed(seed + 104_729)
        policy.explore = mode.explore
    enc_rng = np.random.default_rng([seed, 17])
    scenario = scenario_cls()
    scenario.setup(session, enc_rng)
    rec = EpisodeRecorder(session)
    rew = RewardTracker(reward_spec, DT)
    h = hashlib.sha256()
    cap = int(round((scenario.max_seconds or scenario.seconds) / DT))
    t = 0
    while True:
        w = session.world
        pointer, strike = scenario.step(session, t, enc_rng)
        committed_before = w.swatter.phase.value in STRIKE_PHASES
        horizontal = float(np.hypot(w.swatter.x - w.fly.x, w.swatter.y - w.fly.y))
        mode_before = None if w.lifecycle is None else w.lifecycle.mode
        events = session.tick(pointer=pointer, strike=strike)
        action = session.fly_loop.last_action
        idx = policy.last_index if isinstance(policy, ManeuverPolicy) else None
        rec.record(t, action, events, idx)
        rew.step(w, action, events, committed_before, horizontal)
        if tick_hook is not None:
            tick_hook(session, t, events, action, committed_before, horizontal, mode_before, False)
        h.update(np.array([w.fly.x, w.fly.y, w.fly.heading, float(w.fly.alive), float(action.escape),
                           action.turn, action.saccade]).tobytes())
        t += 1
        if events.hit or scenario.done(session, t) or t >= cap:
            break
    m = rec.metrics(scenario.info())
    out = {'scenario': scenario_cls.name, 'seed': seed, 'mode': mode.name, 'metrics': m,
           'reward': rew.summary(), 'trajectory_sha256': h.hexdigest()}
    if isinstance(policy, ManeuverPolicy) and mode.updates_allowed:
        out['trajectory'] = policy.trajectory
        out['reward_per_tick'] = rew.per_tick
    if keep_rows:
        out['rows'] = rec.rows
    return out


# ----------------------------------------------------------------- manifest ---
def git_state():
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                             cwd=ROOT, text=True).strip())
    except Exception:            # pragma: no cover
        head, dirty = None, None
    return head, dirty


def run_manifest(kind, policies, seeds, config, reward_spec, model=None, train_seeds=(), metrics=None, extra=None):
    head, dirty = git_state()
    return {
        'kind': kind, 'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'code_commit': head, 'working_tree_dirty': dirty,
        'config_path': str(CONFIG_PATH.relative_to(ROOT)), 'config_sha256': hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
        'config_version': config.get('config_version'), 'numba_threads': os.environ.get('NUMBA_NUM_THREADS'),
        'policies': list(policies), 'eval_seeds': list(seeds), 'train_seeds': list(train_seeds),
        'suite_version': SUITE_VERSION, 'suite_sha256': suite_hash(),
        'observation_schema': contracts.OBSERVATION_SCHEMA, 'action_schema': contracts.ACTION_SCHEMA,
        'reward': reward_spec.as_dict(),
        'model': None if model is None else {'arch': model.arch, 'n_parameters': model.n_parameters,
                                             'checkpoint_sha256': model.param_hash()},
        'metrics': metrics, **(extra or {})}
