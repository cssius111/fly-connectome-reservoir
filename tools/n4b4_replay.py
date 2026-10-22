"""M1.8-N4B4 research: deterministic reconstruction and counterfactual replay of the accepted
N4B1C runtime's no-player free-flight escapes.

Research only. The runtime is the unchanged M1.8-N4B1C code from the clean detached
worktree at e3c55b3 (tools/n4b2_record.verify_runtime_worktree). No runtime file,
configuration, calibration record, policy whitelist or recorder is changed.

A run is re-simulated from its seed under its recorded Numba thread count, and verified
against the original record (escape ticks and DNp01 traces on every tick; fly position
where recorded). Optionally one escape is suppressed as a simulator counterfactual:

* from the event tick for SUPPRESS_TICKS ticks, any escape action of the runtime policy is
  replaced by a non-escape action that keeps only its smoothed turn (no impulse, no escape
  saccade);
* during that window the policy's reported behavior_state ESCAPE is shown to the session
  as ALERT, so ecology and lifecycle see an alerted, non-escaping fly.

The policy itself runs unchanged; only what the world receives from it is altered, and
only in the counterfactual run. WORLD geometry is recorded for offline interpretation.

    python tools/n4b4_replay.py inventory
    python tools/n4b4_replay.py replay --source n4b3_holdout --seed 7401 [--suppress 3563]
    python tools/n4b4_replay.py all            # every reconstruction and counterfactual (parallel lanes)
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

MAIN = Path(__file__).resolve().parent.parent
OUT = MAIN / 'artifacts/m1_8_n4b4'
SUPPRESS_TICKS = 100          # 2 s: covers the 0.4 s refractory and any re-fire
HORIZON_TICKS = 150           # 3 s after the event
PARKED = (1920.0, 388.8)

# Every stored no-player free-flight run of the accepted runtime.
SOURCES = {
    'n4b2_dev': {'glob': 'artifacts/m1_8_n4b2/room_seed710[1-4].json', 'format': 'n4b2'},
    'n4b2_holdout': {'glob': 'artifacts/m1_8_n4b2/room_seed72*.json', 'format': 'n4b2'},
    'n4b3_dev': {'glob': 'artifacts/m1_8_n4b3/room_dev_seed*.json', 'format': 'n4b3'},
    'n4b3_holdout': {'glob': 'artifacts/m1_8_n4b3/room_holdout_seed*.json', 'format': 'n4b3'},
    # N4B1C runtime validation, scenario D (tools/n4b1c_runtime_validation.py closed-loop, run
    # in the feature-branch worktree): summaries only; reconstructed here from the seed.
    'runtime_validation': {'seeds': (101, 255, 4242), 'threads': 4, 'ticks': 9000,
                           'record': 'artifacts/worktrees/n4b1c-runtime/artifacts/m1_8_n4b1c_runtime/closed_loop.json'},
}


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('inventory', 'replay', 'all'))
    p.add_argument('--source', choices=tuple(SOURCES))
    p.add_argument('--seed', type=int)
    p.add_argument('--suppress', type=int, help='event tick whose escape is suppressed')
    p.add_argument('--lanes', type=int, default=8)
    return p.parse_args()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_record(source, seed):
    """Original record of one run: ticks, escape ticks, DNp01 traces, fly positions, threads."""
    spec = SOURCES[source]
    if source == 'runtime_validation':
        d = json.loads((MAIN / spec['record']).read_text(encoding='utf-8'))
        runs = d['scenarios']['D_no_player']
        seeds = list(spec['seeds'])
        run = runs[seeds.index(seed)]['runtime_lateral_dual_path_v1']
        return {'threads': spec['threads'], 'ticks': spec['ticks'],
                'escape_ticks': [e['tick'] for e in run.get('escape_list', [])],
                'escape_channels': [e.get('channel') for e in run.get('escape_list', [])],
                'rows': None, 'format': 'summary'}
    path = [p for p in glob.glob(str(MAIN / spec['glob'])) if p.endswith('seed%d.json' % seed)]
    if len(path) != 1:
        raise SystemExit('no unique record for %s seed %d' % (source, seed))
    meta = json.loads(Path(path[0]).read_text(encoding='utf-8'))
    rows = meta['rows']
    if spec['format'] == 'n4b2':
        rows = [r for r in rows if r['stepped']]
    return {'threads': int(meta['numba_threads']), 'ticks': int(meta['ticks']), 'format': spec['format'],
            'escape_ticks': [r['tick'] for r in rows if r['escape']],
            'escape_channels': [r['channel'] for r in rows if r['escape']], 'rows': rows, 'path': path[0]}


def inventory():
    events, runs = [], []
    for source, spec in SOURCES.items():
        if source == 'runtime_validation':
            seeds = spec['seeds']
        else:
            seeds = sorted(int(Path(p).stem.split('seed')[1]) for p in glob.glob(str(MAIN / spec['glob'])))
        for seed in seeds:
            rec = load_record(source, seed)
            runs.append({'source': source, 'seed': seed, 'threads': rec['threads'], 'ticks': rec['ticks'],
                         'escapes': len(rec['escape_ticks'])})
            for t, ch in zip(rec['escape_ticks'], rec['escape_channels']):
                events.append({'source': source, 'seed': seed, 'tick': t, 'channel': ch, 'threads': rec['threads']})
    keys = [(r['seed'], r['threads']) for r in runs]
    assert len(keys) == len(set(keys)), 'duplicate runs'
    minutes = sum(r['ticks'] for r in runs) / 3000
    OUT.mkdir(parents=True, exist_ok=True)
    body = {'runs': runs, 'events': events, 'minutes': minutes}
    (OUT / 'inventory.json').write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')
    print('%d runs, %.0f min, %d escapes' % (len(runs), minutes, len(events)))
    for e in events:
        print('  ', e)
    return body


class Suppress:
    """Counterfactual wrapper: the runtime policy runs unchanged; escapes in the window are
    withheld from the world and its ESCAPE state is shown as ALERT."""

    def __init__(self, policy, session_ref, start, length):
        self._p, self._s, self.start, self.end = policy, session_ref, start, start + length
        self.suppressed = []

    def __getattr__(self, name):
        return getattr(self._p, name)

    def _active(self):
        return self.start <= self._s['tick'] < self.end

    def reset(self):
        return self._p.reset()

    def decide(self, motor):
        a = self._p.decide(motor)
        if a.escape and self._active():
            self.suppressed.append(self._s['tick'])
            from game.action import Action
            return Action(turn=a.turn)
        return a

    def diagnostics(self):
        d = dict(self._p.diagnostics())
        if self._active() and d.get('behavior_state') == 'ESCAPE':
            d['behavior_state'] = 'ALERT'
        return d


def replay(source, seed, suppress=None):
    rec = load_record(source, seed)
    if int(os.environ.get('NUMBA_NUM_THREADS', '0')) != rec['threads']:
        raise SystemExit('run with NUMBA_NUM_THREADS=%d' % rec['threads'])
    from tools import n4b2_record as R
    R.verify_runtime_worktree()
    sys.path.insert(0, str(R.RUNTIME_WORKTREE))
    import numpy as np
    from game.session import Session, build_policy, load_config
    config = load_config(R.RUNTIME_WORKTREE / 'game_room_config.json')
    policy, _ = build_policy(config, root=R.RUNTIME_WORKTREE)
    ref = {'tick': 0}
    active = Suppress(policy, ref, suppress, SUPPRESS_TICKS) if suppress is not None else policy
    session = Session(config, policy=active, seed=seed, mode='evaluation', root=R.RUNTIME_WORKTREE)
    drec = R.DNRecorder(session.brain, session.encoder)
    until = rec['ticks'] if suppress is None else min(rec['ticks'], suppress + HORIZON_TICKS)
    rows, motion = [], []
    started = time.perf_counter()
    for t in range(until):
        ref['tick'] = t
        n_before = len(drec.spikes)
        session.tick(pointer=PARKED, strike=False)
        stepped = len(drec.spikes) > n_before
        motor = session.fly_loop.last_motor
        action = session.fly_loop.last_action if stepped else None
        fly, sw, lc = session.world.fly, session.world.swatter, session.world.lifecycle
        r = session.last_retina
        m = motor.motion if motor is not None else None
        rows.append({
            'tick': t, 'stepped': stepped, 'alive': bool(fly.alive),
            'theta': float(r.theta), 'theta_dot': float(r.theta_dot), 'azimuth': float(r.azimuth),
            'dnp01_left': None if motor is None else float(motor.dnp01_left),
            'dnp01_right': None if motor is None else float(motor.dnp01_right),
            'policy_escape': bool(stepped and policy.criterion_diagnostics()['escape_trigger_channel'] != 'NONE'
                                  and policy.refractory_remaining == policy.refractory_ticks),
            'world_escape': bool(action is not None and action.escape),
            'paths': policy.criterion_diagnostics()['escape_trigger_paths'],
            'refractory_remaining': int(policy.refractory_remaining),
            'behavior_state': policy.diagnostics().get('behavior_state'),
            'lifecycle_mode': None if lc is None else str(lc.mode),
            'events': [e['type'] for e in lc.events] if lc is not None else [],
            'saccade_kind': str(session.world.saccades.kind),
            'motion': None if m is None else [m.forward_speed, m.lateral_speed, m.yaw_rate, m.saccade_remaining],
            'fly': [fly.x, fly.y, fly.vx, fly.vy, fly.heading],
            'paddle': [sw.x, sw.y, sw.height, sw.vx, sw.vy, sw.face, getattr(sw, 'orientation', 0.0)],
            'visual_half_size': float(session.world.visual_half_size),
            'lethal': bool(session.world.lethal), 'hits': int(session.stats.hits)})
        motion.append(rows[-1]['motion'])
    session.close()
    sp, se, dr = drec.window(0, len(drec.spikes))
    stepped_idx = [i for i, row in enumerate(rows) if row['stepped']]
    # ---- verification against the original record (pre-divergence ticks only)
    limit = until if suppress is None else suppress
    esc = [row['tick'] for row in rows if row['policy_escape'] and row['tick'] < limit]
    want = [t for t in rec['escape_ticks'] if t < limit]
    check = {'escape_ticks_match': esc == want, 'escape_ticks': esc, 'recorded_escape_ticks': want}
    if rec['rows'] is not None:
        by_tick = {row['tick']: row for row in rec['rows']}
        mism = 0
        pos_err = 0.0
        for row in rows:
            if row['tick'] >= limit or not row['stepped']:
                continue
            o = by_tick.get(row['tick'])
            if o is None or o['dnp01_left'] != row['dnp01_left'] or o['dnp01_right'] != row['dnp01_right']:
                mism += 1
            fx = o['fly'][0:2] if rec['format'] == 'n4b3' else o['fly_xyz'][0:2]
            pos_err = max(pos_err, math.hypot(fx[0] - row['fly'][0], fx[1] - row['fly'][1]))
        check.update({'dnp01_mismatch_ticks': mism, 'max_fly_position_error': pos_err})
    check['exact'] = check['escape_ticks_match'] and check.get('dnp01_mismatch_ticks', 0) == 0 \
        and check.get('max_fly_position_error', 0.0) < 1e-9
    OUT.mkdir(parents=True, exist_ok=True)
    name = '%s_seed%d%s' % (source, seed, '' if suppress is None else '_cf%d' % suppress)
    np.savez_compressed(OUT / (name + '.npz'), spikes=sp, sensory=se, drive=dr, stepped_ticks=np.array(stepped_idx))
    meta = {'source': source, 'seed': seed, 'suppress_event_tick': suppress, 'suppress_ticks': SUPPRESS_TICKS,
            'horizon_ticks': HORIZON_TICKS, 'threads': rec['threads'], 'runtime_commit': R.RUNTIME_COMMIT,
            'suppressed_escape_ticks': None if suppress is None else active.suppressed,
            'check': check, 'wall_seconds': time.perf_counter() - started, 'tool_sha256': sha256(__file__),
            'rows': rows}
    meta.update(drec.panel_meta())
    (OUT / (name + '.json')).write_text(json.dumps(meta) + '\n', encoding='utf-8')
    print('%s: exact %s %s' % (name, check['exact'], {k: v for k, v in check.items() if k != 'escape_ticks'}))


def run_all(lanes):
    inv = inventory()
    jobs = []
    for r in inv['runs']:
        # Reconstruct every run with an escape (factual reference for the counterfactual windows)
        # and all validation runs (their original record is a summary only).
        if r['source'] == 'runtime_validation' or r['escapes']:
            jobs.append((r['source'], r['seed'], None, r['threads']))
    for e in inv['events']:
        jobs.append((e['source'], e['seed'], e['tick'], e['threads']))
    jobs = [j for j in jobs if not (OUT / ('%s_seed%d%s.json' % (j[0], j[1], '' if j[2] is None else '_cf%d' % j[2]))).exists()]
    print('%d jobs' % len(jobs), flush=True)
    procs = []
    while jobs or procs:
        while jobs and len(procs) < lanes:
            src, seed, sup, th = jobs.pop(0)
            env = dict(os.environ, NUMBA_NUM_THREADS=str(th), SDL_VIDEODRIVER='dummy')
            cmd = [sys.executable, __file__, 'replay', '--source', src, '--seed', str(seed)]
            if sup is not None:
                cmd += ['--suppress', str(sup)]
            log = open(OUT / ('log_%s_%d_%s.txt' % (src, seed, sup)), 'w')
            procs.append((subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT), log, cmd))
        time.sleep(2)
        for p in list(procs):
            if p[0].poll() is not None:
                p[1].close()
                procs.remove(p)
                print('done rc=%s %s' % (p[0].returncode, ' '.join(p[2][2:])), flush=True)


if __name__ == '__main__':
    ARGS = _args()
    sys.path.insert(0, str(MAIN))
    if ARGS.mode == 'inventory':
        inventory()
    elif ARGS.mode == 'replay':
        replay(ARGS.source, ARGS.seed, ARGS.suppress)
    else:
        run_all(ARGS.lanes)
