"""M3.12 checks P1, P2, P5, P6, P7 and descriptives D1, D3, D4 (game/M3_12_UPWIND_SURGE_FINAL_DESIGN.md).

These are the M3.11 tools with M3.12's fresh seeds, output directory and arms. The criteria are
M3.11's, unchanged. P6 and P7 use 120 seeds each, and share them.

**The checks and their tools.**
- **P1, P2, D1.** Odor runs, as in `tools/m3_10_checks.py`, on seeds 978401-978440.
- **P5.** `tools/m3_7_saccades.py` protocol E, on seeds 978301-978324.
- **P6, P7, D3, D4.** One no-player session per seed, 978501-978620, run once by `paired`.
- **P3 and P4.** P3 uses `tools/kinematics_sanity.py`, and P4 `tools/paired_free_flight_check.py`
  (seeds 978201-978280), both unchanged.

**The paired runner.**
- **Why one session serves three tools.** The wall runs of `tools/m3_9_checks.py`, protocol S of
  `tools/m3_7_saccades.py` and the factor runs of `tools/m3_10_saccade_loss.py` all run the same
  session: no player, pointer parked, 9,000 ticks.
- **What it writes.** All three output files, in their formats:
  - **The wall-run and factor files** stop recording at the first tick the fly is dead, where
    their own tools stop the session.
  - **The protocol-S file** records every tick, as its tool does.
- **Its check.** `validate` runs it on M3.11's baseline seeds 977101 and 977501. It must reproduce
  the separate tools' outputs in artifacts/m3_11/ exactly.

**Arms.**
- **baseline.** v32 at commit a5ca216.
- **candidate.** The working ROOM configuration (v36) for the paired, wall and protocol runs; for
  the odor runs, the commit given with `--candidate-commit`.

    NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py validate
    NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py paired --arm candidate --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py odor --arm candidate --candidate-commit SHA --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py protocol-e --arm baseline
    python tools/m3_12_checks.py summary --candidate-commit SHA
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.enclosure import wrap  # noqa: E402
from game.session import Session, load_config  # noqa: E402
from game.world import World  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_7_saccades as S  # noqa: E402
import tools.m3_9_checks as C9  # noqa: E402
import tools.m3_9_odor_diagnosis as D  # noqa: E402
import tools.m3_10_checks as C10  # noqa: E402
import tools.m3_10_saccade_loss as L  # noqa: E402
from tools.m3_9_wall_saccades import FIELDS, KINDS as WALL_KINDS, wall_geometry  # noqa: E402

OUT = ROOT / 'artifacts/m3_12'
BASELINE_COMMIT = 'a5ca216'
PAIRED_SEEDS = tuple(range(978501, 978621))
VALIDATION = {'walls': 977101, 'saccades': 977501, 'factors': 977501}
M3_11_OUT = ROOT / 'artifacts/m3_11'
P1_LIMIT_S = 0.5
P2_TOLERANCE = 0.05
P7_TOLERANCE = 0.03
BOOTSTRAP = 5000


def arm_config(arm):
    if arm == 'baseline':
        c = json.loads(subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                               cwd=ROOT, text=True))
        assert c['config_version'] == 32
        return c
    c = load_config(ROOT / 'game_room_config.json')
    assert c['config_version'] == 36, 'the working ROOM configuration is not the M3.12 candidate'
    return c


def configure(candidate_commit=None):
    commits = {'baseline': BASELINE_COMMIT, 'candidate': candidate_commit or 'unset'}
    S.OUT = OUT
    S.S_SEEDS = PAIRED_SEEDS
    S.E_SEEDS = tuple(range(978301, 978325))
    S.arm_config = arm_config
    C9.OUT = OUT
    C9.BASELINE_COMMIT = BASELINE_COMMIT
    C9.WALL_SEEDS = PAIRED_SEEDS
    C9.arm_config = arm_config
    D.OUT = OUT / 'odor'
    D.SEEDS = tuple(range(978401, 978441))
    D.COMMITS = dict(commits)
    L.OUT = OUT / 'factors'
    L.SEEDS = PAIRED_SEEDS
    L.COMMITS = dict(commits)


def run_paired(config, arm, seed, out, brain=None):
    """One no-player session; writes the wall-run, protocol-S and factor files under `out`."""
    paths = {'walls': out / 'walls' / arm / ('seed%d.json' % seed),
             'saccades': out / 'saccades' / arm / ('seed%d.npz' % seed),
             'factors': out / 'factors' / arm / ('seed%d.npz' % seed)}
    session = Session(config, brain=brain, root=ROOT, seed=seed, mode='evaluation')
    brain, w = session.brain, session.world
    body = w.body_length
    dt = config['sim']['tick_seconds']
    wall_events, factor_requests, kinds = [], [], []
    counts = {'airborne_ticks': 0, 'near_wall_ticks': 0, 'contact_onsets': 0}
    s_rows = np.zeros((M.SACCADE_TICKS, 5), np.float64)
    f_rows = np.zeros((M.SACCADE_TICKS, 5), np.float32)
    recording = [True]
    request = w.saccades.request

    def logged(kind, angle, peak_rate):
        accepted = request(kind, angle, peak_rate)
        if not (accepted and recording[0]):
            return accepted
        if kind in WALL_KINDS:
            cue = w.wall_cue
            bearing = cue.contact_bearing if kind == 'AVOID' else cue.surface_bearing
            clearance, closing = wall_geometry(w, bearing)
            speed = math.hypot(w.fly.vx, w.fly.vy)
            away = abs(wrap(bearing - angle)) > abs(bearing)
            wall_events.append((session.ticks, kind, math.degrees(bearing), clearance / body, speed / body,
                                clearance / closing if closing > 1e-9 else None, math.degrees(angle), bool(away)))
        if kind in L.KINDS:
            factor_requests.append((session.ticks, L.KINDS.index(kind), int(w.flight.near_wall)))
        return accepted

    w.saccades.request = logged
    was_contact = False
    for t in range(M.SACCADE_TICKS):
        idle = not w.saccades.active
        session.tick(pointer=M.PARKED)
        airborne = w.fly.alive and not (w.lifecycle_active and w.lifecycle.stationary)
        s_rows[t] = (airborne, math.hypot(w.fly.vx, w.fly.vy) / body, w.yaw_rate,
                     session.fly_loop.last_action.escape, w.fly.alive)
        kinds.append(w.saccades.kind)
        if not recording[0]:
            continue
        if not w.fly.alive:
            recording[0] = False
            continue
        if w.lifecycle_active and w.lifecycle.stationary:
            was_contact = False
            continue
        counts['airborne_ticks'] += 1
        counts['near_wall_ticks'] += int(w.flight.near_wall)
        counts['contact_onsets'] += int(w.wall_contact and not was_contact)
        was_contact = w.wall_contact
        state = session.ecology.state if session.ecology is not None else 'NONE'
        neural = World._neural_active(session.fly_loop.last_action)
        f_rows[t] = (1.0, w.kinematic_profile.spontaneous_clock_rate, float(idle and not neural),
                     float(w.flight.near_wall), L.STATES.index(state) if state in L.STATES else -1)
    session.close()
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(paths['saccades'], rows=s_rows, kinds=np.array(kinds), dt=dt)
    np.savez_compressed(paths['factors'], rows=f_rows, requests=np.array(factor_requests, np.int32).reshape(-1, 3),
                        dt=dt)
    paths['walls'].write_text(json.dumps({'seed': seed, 'arm': arm, 'config_version': config['config_version'],
                                          'dt': dt, 'counts': counts, 'fields': FIELDS,
                                          'events': wall_events}) + '\n', encoding='utf-8')
    return brain, counts, len(wall_events)


def paired(args):
    config = arm_config(args.arm)
    for name, pattern in (('walls', 'seed*.json'), ('saccades', 'seed*.npz'), ('factors', 'seed*.npz')):
        M.check_provenance(OUT / name / args.arm, pattern)
    brain = None
    for k, seed in enumerate(PAIRED_SEEDS):
        if k % args.lanes != args.lane:
            continue
        done = [OUT / 'walls' / args.arm / ('seed%d.json' % seed), OUT / 'saccades' / args.arm / ('seed%d.npz' % seed),
                OUT / 'factors' / args.arm / ('seed%d.npz' % seed)]
        if all(p.exists() for p in done):
            continue
        brain, counts, turns = run_paired(config, args.arm, seed, OUT, brain)
        print('%s paired seed %d: %d wall turns, %d contact onsets' % (args.arm, seed, turns,
                                                                      counts['contact_onsets']), flush=True)


def validate(_args):
    """The paired runner must reproduce M3.11's separate baseline runs exactly."""
    config = arm_config('baseline')
    out = OUT / 'validation'
    brain = None
    failures = []
    for seed in sorted(set(VALIDATION.values())):
        brain, _counts, _turns = run_paired(config, 'baseline', seed, out, brain)
    for name, seed in VALIDATION.items():
        ext = 'json' if name == 'walls' else 'npz'
        new, old = (d / name / 'baseline' / ('seed%d.%s' % (seed, ext)) for d in (out, M3_11_OUT))
        if ext == 'json':
            a, b = (json.loads(p.read_text(encoding='utf-8')) for p in (new, old))
            same = a == b
        else:
            a, b = np.load(new), np.load(old)
            same = sorted(a.files) == sorted(b.files) and all(np.array_equal(a[f], b[f]) for f in a.files)
        print('%s seed %d: %s' % (name, seed, 'identical' if same else 'DIFFERENT'))
        if not same:
            failures.append(name)
    if failures:
        raise SystemExit('the paired runner does not reproduce: %s' % failures)
    print('the paired runner reproduces the separate tools')


def near_wall_difference():
    """D4: the near-wall share of airborne time, candidate minus baseline, with a seed bootstrap."""
    v = []
    for seed in PAIRED_SEEDS:
        row = []
        for arm in S.ARMS:
            c = json.loads((OUT / 'walls' / arm / ('seed%d.json' % seed)).read_text(encoding='utf-8'))['counts']
            row += [c['airborne_ticks'], c['near_wall_ticks']]
        v.append(row)
    v = np.array(v, float)

    def diff(x):
        return x[:, 3].sum() / x[:, 2].sum() - x[:, 1].sum() / x[:, 0].sum()

    rng = np.random.default_rng(4)
    boots = [diff(v[rng.integers(0, len(v), len(v))]) for _ in range(BOOTSTRAP)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    higher = int(((v[:, 3] / v[:, 2]) > (v[:, 1] / v[:, 0])).sum())
    return {'difference': float(diff(v)), 'interval_95': [float(lo), float(hi)],
            'seeds_higher': higher, 'seeds': len(v)}


def saccade_rate_difference():
    """D3: accepted SACCADE requests per airborne second, candidate minus baseline, seed bootstrap."""
    v = []
    for seed in PAIRED_SEEDS:
        row = []
        for arm in S.ARMS:
            z = np.load(L.OUT / arm / ('seed%d.npz' % seed))
            saccades = int((z['requests'][:, 1] == L.KINDS.index('SACCADE')).sum())
            row += [float((z['rows'][:, 0] > 0).sum()) * float(z['dt']), saccades]
        v.append(row)
    v = np.array(v, float)

    def diff(x):
        return x[:, 3].sum() / x[:, 2].sum() - x[:, 1].sum() / x[:, 0].sum()

    rng = np.random.default_rng(5)
    boots = [diff(v[rng.integers(0, len(v), len(v))]) for _ in range(BOOTSTRAP)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {'difference': float(diff(v)), 'interval_95': [float(lo), float(hi)], 'seeds': len(v)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('validate', 'paired', 'odor', 'protocol-e', 'summary'))
    parser.add_argument('--arm', choices=S.ARMS)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    configure(args.candidate_commit)
    if args.mode in ('paired', 'odor', 'protocol-e') and args.arm is None:
        parser.error('%s needs --arm' % args.mode)
    if args.mode == 'odor' and args.arm == 'candidate' and not args.candidate_commit:
        parser.error('the candidate odor runs need --candidate-commit')
    if args.mode == 'validate':
        validate(args)
    elif args.mode == 'paired':
        paired(args)
    elif args.mode == 'odor':
        C10.odor(args)
    elif args.mode == 'protocol-e':
        S.protocol_e(args)
    else:
        S.summary(args)
        result = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
        D.summary(args)
        diag = json.loads((D.OUT / 'summary.json').read_text(encoding='utf-8'))
        walls = C9.wall_summary(labels=('M3.9 wall-turn amplitude (not an M3.12 check)', 'P6'))
        L.summary(args)
        factors = json.loads((L.OUT / 'summary.json').read_text(encoding='utf-8'))
        d4 = near_wall_difference()
        print('D4: near-wall share difference %+.3f [%+.3f, %+.3f]; %d of %d seeds higher' % (
            d4['difference'], *d4['interval_95'], d4['seeds_higher'], d4['seeds']))
        d3 = saccade_rate_difference()
        factors['seed_bootstrap_saccade_rate'] = d3
        print('D3: SACCADE per airborne s difference %+.3f [%+.3f, %+.3f] over %d seeds' % (
            d3['difference'], *d3['interval_95'], d3['seeds']))
        latency = {arm: C10.turn_latency(arm) for arm in S.ARMS}
        for arm, r in latency.items():
            print('== %s: %d off-wind entries, %d reach 45 deg; median %s s; %d bout entries, %d surge requests, '
                  '%d executed' % (arm, r['off_wind_entries'], r['reach_45'],
                                   'never' if math.isinf(r['median_s']) else '%.2f' % r['median_s'],
                                   r['bout_entries'], r['surge_requests'], r['surges_executed']))
        cand = latency['candidate']
        p1 = cand['median_s'] <= P1_LIMIT_S
        b2, c2 = diag['baseline']['upwind_share'], diag['candidate']['upwind_share']
        p2 = c2 >= b2 - P2_TOLERANCE
        sb, sc = result.get('baseline', {}), result.get('candidate', {})
        b7, c7 = sb['clock_saccade_rate_per_s'], sc['clock_saccade_rate_per_s']
        p7 = bool(c7 >= b7 - P7_TOLERANCE and sc.get('S3_match'))
        result.update({'odor': diag, 'walls': walls, 'factors': factors, 'D4': d4,
                       'turn_latency': {k: {kk: (None if isinstance(vv, float) and math.isinf(vv) else vv)
                                            for kk, vv in v.items()} for k, v in latency.items()},
                       'P1': {'median_s': None if math.isinf(cand['median_s']) else cand['median_s'], 'pass': bool(p1)},
                       'P2': {'baseline': b2, 'candidate': c2, 'pass': bool(p2)},
                       'P6': walls.get('P2'),
                       'P7': {'baseline': b7, 'candidate': c7, 'limit': b7 - P7_TOLERANCE,
                              'S3_match': sc.get('S3_match'), 'pass': p7}})
        print('P1: candidate median time to 45 deg %s s (pass if <= %.1f): %s' % (
            'never' if math.isinf(cand['median_s']) else '%.2f' % cand['median_s'], P1_LIMIT_S,
            'pass' if p1 else 'FAIL'))
        print('P2: ODOR_TRACK upwind share baseline %.3f, candidate %.3f (pass if >= %.3f): %s' % (
            b2, c2, b2 - P2_TOLERANCE, 'pass' if p2 else 'FAIL'))
        print('P7: clock-driven saccades baseline %.3f, candidate %.3f per s (pass if >= %.3f and S3 matches): %s' % (
            b7, c7, b7 - P7_TOLERANCE, 'pass' if p7 else 'FAIL'))
        (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
