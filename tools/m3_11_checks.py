"""M3.11 checks P1, P2, P5, P6, P7 and descriptives D1, D3 (game/M3_11_UPWIND_SURGE_RETEST_DESIGN.md).

These are the M3.10 tools with M3.11's fresh seeds, output directory and arms. The one change of
criterion is P7, which is baseline-relative.

**The checks and their tools.**
- **P1, P2, D1.** Odor runs, as in `tools/m3_10_checks.py`, on seeds 977401-977440.
- **P6.** The wall runs of `tools/m3_9_checks.py`, on seeds 977101-977124.
- **P5.** `tools/m3_7_saccades.py` protocol E, on seeds 977301-977324.
- **P7.** `tools/m3_7_saccades.py` protocol S, on seeds 977501-977540. The candidate's clock-driven
  saccade rate must be at least the baseline's minus 0.03 per s, and S3 must match.
- **D3.** `tools/m3_10_saccade_loss.py`, on P7's seeds.

P3 uses `tools/kinematics_sanity.py`, and P4 `tools/paired_free_flight_check.py` (seeds
977201-977280), both unchanged.

**Arms.**
- **baseline.** v32 at commit a5ca216.
- **candidate.** The working ROOM configuration (v35) for the wall runs and protocols S and E; for
  the odor and D3 runs, the commit given with `--candidate-commit`.

    NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py odor --arm candidate --candidate-commit SHA --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py walls --arm baseline --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py protocol-s --arm candidate --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py protocol-e --arm baseline
    NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py factors --arm candidate --candidate-commit SHA --lane 0 --lanes 2
    python tools/m3_11_checks.py summary --candidate-commit SHA
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

from game.session import load_config  # noqa: E402
import tools.m3_7_saccades as S  # noqa: E402
import tools.m3_9_checks as C9  # noqa: E402
import tools.m3_9_odor_diagnosis as D  # noqa: E402
import tools.m3_10_checks as C10  # noqa: E402
import tools.m3_10_saccade_loss as L  # noqa: E402

OUT = ROOT / 'artifacts/m3_11'
BASELINE_COMMIT = 'a5ca216'
P1_LIMIT_S = 0.5
P2_TOLERANCE = 0.05
P7_TOLERANCE = 0.03


def arm_config(arm):
    if arm == 'baseline':
        c = json.loads(subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                               cwd=ROOT, text=True))
        assert c['config_version'] == 32
        return c
    c = load_config(ROOT / 'game_room_config.json')
    assert c['config_version'] == 35, 'the working ROOM configuration is not the M3.11 candidate'
    return c


def configure(candidate_commit=None):
    commits = {'baseline': BASELINE_COMMIT, 'candidate': candidate_commit or 'unset'}
    S.OUT = OUT
    S.S_SEEDS = tuple(range(977501, 977541))
    S.E_SEEDS = tuple(range(977301, 977325))
    S.arm_config = arm_config
    C9.OUT = OUT
    C9.BASELINE_COMMIT = BASELINE_COMMIT
    C9.WALL_SEEDS = tuple(range(977101, 977125))
    C9.arm_config = arm_config
    D.OUT = OUT / 'odor'
    D.SEEDS = tuple(range(977401, 977441))
    D.COMMITS = dict(commits)
    L.OUT = OUT / 'factors'
    L.SEEDS = S.S_SEEDS
    L.COMMITS = dict(commits)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('odor', 'walls', 'protocol-s', 'protocol-e', 'factors', 'summary'))
    parser.add_argument('--arm', choices=S.ARMS)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    configure(args.candidate_commit)
    if args.mode != 'summary' and args.arm is None:
        parser.error('%s needs --arm' % args.mode)
    if args.mode in ('odor', 'factors') and args.arm == 'candidate' and not args.candidate_commit:
        parser.error('the candidate %s runs need --candidate-commit' % args.mode)
    if args.mode == 'odor':
        C10.odor(args)
    elif args.mode == 'factors':
        L.run(args)
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
        walls = C9.wall_summary(labels=('M3.9 wall-turn amplitude (not an M3.11 check)', 'P6'))
        L.summary(args)
        factors = json.loads((L.OUT / 'summary.json').read_text(encoding='utf-8'))
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
        result.update({'odor': diag, 'walls': walls, 'factors': factors,
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
