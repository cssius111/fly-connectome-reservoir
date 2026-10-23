"""M3.2 check V6a: the N4B6 controlled-approach matrix under the v27 and v28 ROOM configurations.

Descriptive (game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md, amendment 1). It reuses the
preregistered N4B6 trajectories, seeds and placement (tools/n4b6_protocol.py,
tools/n4b6_controlled_approach.py) unchanged:
- fixed fly (fly motion and collisions disabled) and no ecology, as in N4B6;
- the runtime decoder running live, built from each configuration's own transfer record.

Arms:
- baseline: the v27 ROOM configuration at commit d67808f, read from git;
- candidate: the configuration in the working tree.

Both run with this checkout's code, whose legacy encoder mode is bit-identical to v27's.

    python tools/m3_2_threat_matrix.py run --arm baseline
    python tools/m3_2_threat_matrix.py run --arm candidate
    python tools/m3_2_threat_matrix.py summary
    (add --out DIR to keep another milestone's runs apart; M3.3 uses artifacts/m3_3_run/threat_matrix)

Outputs go to artifacts/m3_2/threat_matrix/ (git-ignored), one file per arm and trajectory,
with the M3.0 provenance guard.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.session import Session, load_config  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.n4b6_controlled_approach as N  # noqa: E402

P = N.P
OUT = ROOT / 'artifacts/m3_2/threat_matrix'
BASELINE_COMMIT = 'd67808f62bef6a11205f65be6aad827b48f4d82a'
ARMS = ('baseline', 'candidate')


def arm_config(arm):
    if arm == 'baseline':
        config = json.loads(subprocess.check_output(
            ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
        assert config['config_version'] == 27
        return config
    return load_config(ROOT / 'game_room_config.json')


def run(arm):
    config = arm_config(arm)
    session = Session(config, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    out = OUT / arm
    M.check_provenance(out, '*.json')
    for tid in P.MATRIX:
        path = out / ('%s.json' % tid)
        if path.exists():
            continue
        offs, pointer, marks = N.pointer_path(tid)
        trials = []
        for seed in P.SEEDS:
            session.reset(seed)
            N.place(session, offs)
            w = session.world
            escapes = []
            for k, (ox, oy) in enumerate(pointer):
                session.tick(pointer=(P.FLY_POSE[0] + ox, P.FLY_POSE[1] + oy), strike=False)
                if session.fly_loop.last_action.escape:
                    escapes.append((k, math.degrees(session.last_retina.theta)))
                if (w.fly.x, w.fly.y) != P.FLY_POSE[:2] or 'approach' not in str(w.swatter.phase).lower():
                    raise RuntimeError('controlled state violated')
            after = [e for e in escapes if e[0] >= P.PRE_HOLD_TICKS]
            trials.append({'seed': seed, 'escapes': len(escapes),
                           'pre_hold_escapes': len(escapes) - len(after),
                           'first_after_onset_s': None if not after else (after[0][0] - P.PRE_HOLD_TICKS + 1) * N.DT,
                           'theta_at_first_deg': None if not after else after[0][1]})
        path.write_text(json.dumps({'arm': arm, 'trajectory': tid, 'role': P.MATRIX[tid]['role'],
                                    'family': P.MATRIX[tid]['family'], 'trials': trials}) + '\n',
                        encoding='utf-8')
        print('%s %s: %d of %d trials escaped after onset' % (
            arm, tid, sum(t['first_after_onset_s'] is not None for t in trials), len(trials)), flush=True)
    session.close()


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def summary():
    rows = {}
    for arm in ARMS:
        M.recorded_provenance(OUT / arm)
        for tid in P.MATRIX:
            path = OUT / arm / ('%s.json' % tid)
            if not path.exists():
                raise SystemExit('%s is incomplete: %s is missing' % (arm, path.name))
            data = json.loads(path.read_text(encoding='utf-8'))
            if len(data['trials']) != len(P.SEEDS):
                raise SystemExit('%s %s has %d trials' % (arm, tid, len(data['trials'])))
            t = data['trials']
            rows.setdefault(tid, {'role': data['role'], 'family': data['family']})[arm] = {
                'escape_fraction': sum(x['first_after_onset_s'] is not None for x in t) / len(t),
                'median_first_s': median(x['first_after_onset_s'] for x in t),
                'median_theta_deg': median(x['theta_at_first_deg'] for x in t),
                'pre_hold_escapes': sum(x['pre_hold_escapes'] for x in t)}
    (OUT / 'summary.json').write_text(json.dumps(rows, indent=1) + '\n', encoding='utf-8')
    fmt = lambda v, s='%.2f': '-' if v is None else s % v
    print('trajectory | role | baseline: fraction, first (s), size (deg) | candidate: fraction, first (s), size (deg)')
    for tid, r in rows.items():
        b, c = r['baseline'], r['candidate']
        print('%-6s | %-8s | %.2f %s %s | %.2f %s %s' % (
            tid, r['role'], b['escape_fraction'], fmt(b['median_first_s']), fmt(b['median_theta_deg'], '%.1f'),
            c['escape_fraction'], fmt(c['median_first_s']), fmt(c['median_theta_deg'], '%.1f')))


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary'))
    parser.add_argument('--arm', choices=ARMS)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.out
    if args.mode == 'run':
        if args.arm is None:
            parser.error('run needs --arm')
        run(args.arm)
    else:
        summary()


if __name__ == '__main__':
    main()
