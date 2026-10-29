"""M3.10 checks P1, P2, P5, P6, P7 and descriptives D1, D3 (game/M3_10_UPWIND_SURGE_DESIGN.md).

These are the M3.9 tools with M3.10's seeds, output directory and arms.
- **P1, P2, D1, D3.** Odor runs as in `tools/m3_9_odor_diagnosis.py`, seeds 975401-975440,
  with two more per-tick columns: surge requests and executed surges.
- **P6.** The wall runs of `tools/m3_9_checks.py`, seeds 975101-975124.
- **P5, P7.** `tools/m3_7_saccades.py`:
  - protocol E on seeds 975301-975324;
  - protocol S on seeds 975501-975520.

P3 uses `tools/kinematics_sanity.py`, and P4 `tools/paired_free_flight_check.py` (seeds
975201-975280), both unchanged; see the design note for the commands.

**Arms.**
- **baseline.** v32 at commit e113583.
- **candidate.** The working ROOM configuration (v34) for the wall runs and protocols S and E; for
  the odor runs, the commit given with `--candidate-commit`.

    NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py odor --arm candidate --candidate-commit SHA --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py walls --arm baseline --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py protocol-s --arm candidate --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py protocol-e --arm baseline
    python tools/m3_10_checks.py summary --candidate-commit SHA
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

from game.session import Session, load_config  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_7_saccades as S  # noqa: E402
import tools.m3_9_checks as C9  # noqa: E402
import tools.m3_9_odor_diagnosis as D  # noqa: E402

OUT = ROOT / 'artifacts/m3_10'
BASELINE_COMMIT = 'e113583'
P1_LIMIT_S = 0.5
P2_TOLERANCE = 0.05
TRACK = D.STATES.index('ODOR_TRACK')


def arm_config(arm):
    if arm == 'baseline':
        c = json.loads(subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                               cwd=ROOT, text=True))
        assert c['config_version'] == 32
        return c
    c = load_config(ROOT / 'game_room_config.json')
    assert c['config_version'] == 34, 'the working ROOM configuration is not the M3.10 candidate'
    return c


def configure(candidate_commit=None):
    S.OUT = OUT
    S.S_SEEDS = tuple(range(975501, 975521))
    S.E_SEEDS = tuple(range(975301, 975325))
    S.arm_config = arm_config
    C9.OUT = OUT
    C9.BASELINE_COMMIT = BASELINE_COMMIT
    C9.WALL_SEEDS = tuple(range(975101, 975125))
    C9.arm_config = arm_config
    D.OUT = OUT / 'odor'
    D.SEEDS = tuple(range(975401, 975441))
    D.COMMITS = {'baseline': BASELINE_COMMIT, 'candidate': candidate_commit or 'unset'}


def odor(args):
    """D.run with surge columns: the diagnosis fields, then surge requests and executed surges."""
    config = D.arm_config(args.arm)
    out = D.OUT / args.arm
    M.check_provenance(out, 'seed*.npz')
    food = config['room']['food']
    brain = None
    for k, seed in enumerate(D.SEEDS):
        if k % args.lanes != args.lane:
            continue
        path = out / ('seed%d.npz' % seed)
        if path.exists():
            continue
        session = Session(config, brain=brain, root=ROOT, seed=seed, mode='evaluation')
        brain, w = session.brain, session.world
        body = w.body_length
        rows = np.full((D.TICKS, 8), np.nan)
        for t in range(D.TICKS):
            requested, executed = w.surge_requests, w.surges_executed
            session.tick(pointer=M.PARKED)
            fly = w.fly
            if not fly.alive:
                break
            airborne = not (w.lifecycle_active and w.lifecycle.stationary)
            state = session.ecology.state if session.ecology is not None else 'NONE'
            wx, wy = w.room.wind(w.time_seconds)
            speed = math.hypot(wx, wy)
            ux, uy = wx / speed, wy / speed
            dx, dy = fly.x - food['x'], fly.y - food['y']
            upwind_error = abs(D.wrap(fly.heading - math.atan2(-wy, -wx)))
            clearance = min(c for _side, c, _n, _a in w.enclosure._walls(fly.x, fly.y))
            rows[t] = (D.STATES.index(state) if state in D.STATES else -1, float(airborne),
                       math.degrees(upwind_error), dx * ux + dy * uy, -dx * uy + dy * ux, clearance / body,
                       w.surge_requests - requested, w.surges_executed - executed)
        session.close()
        np.savez_compressed(path, rows=rows, dt=config['sim']['tick_seconds'])
        print('%s seed %d done' % (args.arm, seed), flush=True)


def turn_latency(arm):
    """Over airborne ODOR_TRACK entries more than 45 deg off upwind: time to within 45 deg, or never."""
    times, surges, executed, entries = [], 0, 0, 0
    for seed in D.SEEDS:
        z = np.load(D.OUT / arm / ('seed%d.npz' % seed))
        rows, dt = z['rows'], float(z['dt'])
        rows = rows[~np.isnan(rows[:, 1])]
        state, air, err = rows[:, 0].astype(int), rows[:, 1] > 0, rows[:, 2]
        surges += int(np.nansum(rows[:, 6]))
        executed += int(np.nansum(rows[:, 7]))
        entries += int(((state == TRACK) & np.concatenate([[True], state[:-1] != TRACK])).sum())
        i = 1
        while i < len(rows):
            if state[i] == TRACK and state[i - 1] != TRACK and air[i] and err[i] > D.UPWIND_DEG:
                j = i
                while j < len(rows) and state[j] == TRACK and err[j] > D.UPWIND_DEG:
                    j += 1
                times.append((j - i) * dt if j < len(rows) and state[j] == TRACK else math.inf)
                i = j
            i += 1
    times = np.array(times)
    return {'off_wind_entries': int(len(times)), 'reach_45': int(np.isfinite(times).sum()),
            'median_s': float(np.median(times)),
            'median_reached_s': float(np.median(times[np.isfinite(times)])) if np.isfinite(times).any() else None,
            'bout_entries': entries, 'surge_requests': surges, 'surges_executed': executed}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('odor', 'walls', 'protocol-s', 'protocol-e', 'summary'))
    parser.add_argument('--arm', choices=S.ARMS)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    configure(args.candidate_commit)
    if args.mode != 'summary' and args.arm is None:
        parser.error('%s needs --arm' % args.mode)
    if args.mode == 'odor':
        if args.arm == 'candidate' and not args.candidate_commit:
            parser.error('the candidate odor runs need --candidate-commit')
        odor(args)
    elif args.mode == 'walls':
        C9.walls(args)
    elif args.mode == 'protocol-s':
        S.protocol_s(args)
    elif args.mode == 'protocol-e':
        S.protocol_e(args)
    else:
        S.summary(args)
        result = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
        D.summary(args)
        diag = json.loads((D.OUT / 'summary.json').read_text(encoding='utf-8'))
        walls = C9.wall_summary(labels=('M3.9 wall-turn amplitude (not an M3.10 check)', 'P6'))
        latency = {arm: turn_latency(arm) for arm in S.ARMS}
        for arm, r in latency.items():
            print('== %s: %d off-wind entries, %d reach 45 deg; median %s s (%s s among those that do); '
                  '%d bout entries, %d surge requests, %d executed' % (
                      arm, r['off_wind_entries'], r['reach_45'],
                      'never' if math.isinf(r['median_s']) else '%.2f' % r['median_s'],
                      '-' if r['median_reached_s'] is None else '%.2f' % r['median_reached_s'],
                      r['bout_entries'], r['surge_requests'], r['surges_executed']))
        cand = latency['candidate']
        p1 = cand['median_s'] <= P1_LIMIT_S
        b, c = diag['baseline']['upwind_share'], diag['candidate']['upwind_share']
        p2 = c >= b - P2_TOLERANCE
        sc = result.get('candidate', {})
        p7 = bool(sc.get('P1_pass') and sc.get('S3_match'))
        result.update({'odor': diag, 'walls': walls,
                       'turn_latency': {k: {kk: (None if isinstance(vv, float) and math.isinf(vv) else vv)
                                            for kk, vv in v.items()} for k, v in latency.items()},
                       'P1': {'median_s': None if math.isinf(cand['median_s']) else cand['median_s'], 'pass': bool(p1)},
                       'P2': {'baseline': b, 'candidate': c, 'pass': bool(p2)},
                       'P6': walls.get('P2'),
                       'P7': {'clock_saccade_rate_per_s': sc.get('clock_saccade_rate_per_s'),
                              'S3_match': sc.get('S3_match'), 'pass': p7}})
        print('P1: candidate median time to 45 deg %s s (pass if <= %.1f): %s' % (
            'never' if math.isinf(cand['median_s']) else '%.2f' % cand['median_s'], P1_LIMIT_S,
            'pass' if p1 else 'FAIL'))
        print('P2: ODOR_TRACK upwind share baseline %.3f, candidate %.3f (pass if >= %.3f): %s' % (
            b, c, b - P2_TOLERANCE, 'pass' if p2 else 'FAIL'))
        print('P7: %s' % ('pass' if p7 else 'FAIL'))
        (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
