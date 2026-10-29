"""M3.9 checks P1, P2, P5, P6, P7 and descriptives D1, D3 (game/M3_9_WALL_SACCADE_DESIGN.md).

**The checks and their tools.**
- **P1, P2, D1.** Wall runs on seeds 974101-974124 (24 × 180 s, no player, pointer parked), both
  arms.
  - **Per wall turn.** Every accepted AVOID or DEPART request is recorded as in
    `tools/m3_9_wall_saccades.py`.
  - **Per tick.** Wall-contact onsets (`World.wall_contact` rising, the containment acting) and the
    near-wall flag, counted on airborne ticks.
- **P5, P7.** `tools/m3_7_saccades.py`, with M3.9's seeds, output directory and arms:
  - protocol E on seeds 974301-974324;
  - protocol S on seeds 974501-974520.
- **P6, D3.** `tools/m3_7_encounters.py` on seeds 974401-974440.

P3 uses `tools/kinematics_sanity.py`, and P4 `tools/paired_free_flight_check.py` (seeds
974201-974280), both unchanged; see the design note for the commands.

**Arms.**
- **baseline.** v32 at commit 925427c.
- **candidate.** The working ROOM configuration (v33) for the wall runs and protocols S and E; for
  the P6 runs, the commit given with `--candidate-commit`.

    NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py walls --arm candidate --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py protocol-s --arm baseline --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py protocol-e --arm candidate
    NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py encounters --arm candidate --candidate-commit SHA --lane 0 --lanes 2
    python tools/m3_9_checks.py summary --candidate-commit SHA
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
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_7_encounters as E  # noqa: E402
import tools.m3_7_saccades as S  # noqa: E402
from tools.m3_9_wall_saccades import FIELDS, KINDS, regression, wall_geometry  # noqa: E402

OUT = ROOT / 'artifacts/m3_9'
BASELINE_COMMIT = '925427c'
WALL_SEEDS = tuple(range(974101, 974125))
TICKS = 9000
P1_SLOPE, P1_R2, P1_MEDIAN = 0.2, 0.05, (60.0, 120.0)
P2_CONTACT_FACTOR, P2_CONTACT_FLOOR, P2_NEAR_FACTOR = 2.0, 0.5, 1.25
P6_TOLERANCE = 0.05
REPEAT_WINDOW_S = 1.0


def arm_config(arm):
    if arm == 'baseline':
        c = json.loads(subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                               cwd=ROOT, text=True))
        assert c['config_version'] == 32
        return c
    c = load_config(ROOT / 'game_room_config.json')
    assert c['config_version'] == 33, 'the working ROOM configuration is not the M3.9 candidate'
    return c


def configure(candidate_commit=None):
    S.OUT = OUT
    S.S_SEEDS = tuple(range(974501, 974521))
    S.E_SEEDS = tuple(range(974301, 974325))
    S.arm_config = arm_config
    E.OUT = OUT / 'encounters'
    E.SEEDS = tuple(range(974401, 974441))
    E.COMMITS = {'baseline': BASELINE_COMMIT, 'candidate': candidate_commit or 'unset'}


# ---------------------------------------------------------------------------- wall runs ---
def walls(args):
    config = arm_config(args.arm)
    out = OUT / 'walls' / args.arm
    M.check_provenance(out, 'seed*.json')
    brain = None
    dt = config['sim']['tick_seconds']
    for k, seed in enumerate(WALL_SEEDS):
        if k % args.lanes != args.lane:
            continue
        path = out / ('seed%d.json' % seed)
        if path.exists():
            continue
        session = Session(config, brain=brain, root=ROOT, seed=seed, mode='evaluation')
        brain, world = session.brain, session.world
        body = world.body_length
        events = []
        counts = {'airborne_ticks': 0, 'near_wall_ticks': 0, 'contact_onsets': 0}
        request = world.saccades.request

        def logged(kind, angle, peak_rate):
            accepted = request(kind, angle, peak_rate)
            if not accepted or kind not in KINDS:
                return accepted
            cue = world.wall_cue
            bearing = cue.contact_bearing if kind == 'AVOID' else cue.surface_bearing
            clearance, closing = wall_geometry(world, bearing)
            speed = math.hypot(world.fly.vx, world.fly.vy)
            away = abs(wrap(bearing - angle)) > abs(bearing)
            events.append((session.ticks, kind, math.degrees(bearing), clearance / body, speed / body,
                           clearance / closing if closing > 1e-9 else None, math.degrees(angle), bool(away)))
            return accepted

        world.saccades.request = logged
        was_contact = False
        for _ in range(TICKS):
            session.tick(pointer=M.PARKED)
            if not world.fly.alive:
                break
            if world.lifecycle_active and world.lifecycle.stationary:
                was_contact = False
                continue
            counts['airborne_ticks'] += 1
            counts['near_wall_ticks'] += int(world.flight.near_wall)
            counts['contact_onsets'] += int(world.wall_contact and not was_contact)
            was_contact = world.wall_contact
        session.close()
        path.write_text(json.dumps({'seed': seed, 'arm': args.arm, 'config_version': config['config_version'],
                                    'dt': dt, 'counts': counts, 'fields': FIELDS, 'events': events}) + '\n',
                        encoding='utf-8')
        print('%s seed %d: %d wall turns, %d contact onsets' % (args.arm, seed, len(events),
                                                               counts['contact_onsets']), flush=True)


def wall_summary():
    result = {}
    for arm in S.ARMS:
        out = OUT / 'walls' / arm
        paths = [out / ('seed%d.json' % s) for s in WALL_SEEDS]
        missing = [p.name for p in paths if not p.exists()]
        if missing:
            print('walls %s incomplete: %d missing' % (arm, len(missing)))
            continue
        M.recorded_provenance(out)
        runs = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
        dt = runs[0]['dt']
        airborne_s = sum(r['counts']['airborne_ticks'] for r in runs) * dt
        rows = [dict(zip(FIELDS, e)) for r in runs for e in r['events']]
        avoid = [e for e in rows if e['kind'] == 'AVOID']
        repeats = 0
        for r in runs:
            ticks = [e[0] for e in r['events'] if e[1] == 'AVOID']
            repeats += sum(1 for a, b in zip(ticks, ticks[1:]) if (b - a) * dt <= REPEAT_WINDOW_S)
        amp = np.array([abs(e['turn_deg']) for e in avoid])
        a = {'airborne_s': airborne_s,
             'rates_per_s': {k: sum(1 for e in rows if e['kind'] == k) / airborne_s for k in ('AVOID', 'DEPART')},
             'avoid_n': len(avoid),
             'avoid_amplitude_deg': {'median': float(np.median(amp)), 'p10': float(np.percentile(amp, 10)),
                                     'p90': float(np.percentile(amp, 90))},
             'avoid_away_share': float(np.mean([e['away'] for e in avoid])),
             'avoid_clearance_bl_median': float(np.median([e['clearance_bl'] for e in avoid])),
             'avoid_repeats_within_1s': repeats,
             'contact_onsets_per_min': sum(r['counts']['contact_onsets'] for r in runs) / (airborne_s / 60.0),
             'near_wall_share': sum(r['counts']['near_wall_ticks'] for r in runs)
             / sum(r['counts']['airborne_ticks'] for r in runs)}
        for sign, label in ((1, 'right_turns'), (-1, 'left_turns')):
            sel = [e for e in avoid if np.sign(e['turn_deg']) == sign]
            a[label] = regression(np.array([e['approach_deg'] for e in sel]), np.array([e['turn_deg'] for e in sel]))
        result[arm] = a
        print('== walls %s: %.0f airborne s; AVOID %.3f per s, DEPART %.3f per s; %d AVOIDs within %.0f s of another' % (
            arm, airborne_s, a['rates_per_s']['AVOID'], a['rates_per_s']['DEPART'], repeats, REPEAT_WINDOW_S))
        print('   AVOID amplitude median %.0f deg (p10 %.0f, p90 %.0f); away %.2f; clearance median %.1f BL' % (
            a['avoid_amplitude_deg']['median'], a['avoid_amplitude_deg']['p10'], a['avoid_amplitude_deg']['p90'],
            a['avoid_away_share'], a['avoid_clearance_bl_median']))
        for label in ('right_turns', 'left_turns'):
            g = a[label]
            print('   %s: n %d, slope %.2f, r2 %.3f' % (label, g['n'], g['slope'], g['r2']))
        print('   contact onsets %.3f per airborne min; near-wall share %.3f' % (
            a['contact_onsets_per_min'], a['near_wall_share']))
    if set(result) != set(S.ARMS):
        return result
    c, b = result['candidate'], result['baseline']
    p1 = (all(abs(c[l]['slope']) <= P1_SLOPE and c[l]['r2'] <= P1_R2 for l in ('right_turns', 'left_turns'))
          and P1_MEDIAN[0] <= c['avoid_amplitude_deg']['median'] <= P1_MEDIAN[1] and c['avoid_away_share'] == 1.0)
    contact_limit = max(P2_CONTACT_FACTOR * b['contact_onsets_per_min'], P2_CONTACT_FLOOR)
    p2 = (c['contact_onsets_per_min'] <= contact_limit and c['near_wall_share'] <= P2_NEAR_FACTOR * b['near_wall_share'])
    result['P1'] = {'pass': bool(p1)}
    result['P2'] = {'contact_limit_per_min': contact_limit, 'near_wall_limit': P2_NEAR_FACTOR * b['near_wall_share'],
                    'pass': bool(p2)}
    print('P1: %s' % ('pass' if p1 else 'FAIL'))
    print('P2: contact onsets %.3f per min (limit %.3f), near-wall share %.3f (limit %.3f): %s' % (
        c['contact_onsets_per_min'], contact_limit, c['near_wall_share'], P2_NEAR_FACTOR * b['near_wall_share'],
        'pass' if p2 else 'FAIL'))
    return result


def p6():
    summary = json.loads((OUT / 'encounters' / 'summary.json').read_text(encoding='utf-8'))
    base = summary['baseline']['odor_track_upwind_share']
    cand = summary['candidate']['odor_track_upwind_share']
    ok = cand >= base - P6_TOLERANCE
    print('P6: ODOR_TRACK upwind share baseline %.3f, candidate %.3f (pass if >= %.3f): %s' % (
        base, cand, base - P6_TOLERANCE, 'pass' if ok else 'FAIL'))
    return {'baseline': base, 'candidate': cand, 'pass': ok}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('walls', 'protocol-s', 'protocol-e', 'encounters', 'summary'))
    parser.add_argument('--arm', choices=S.ARMS)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    configure(args.candidate_commit)
    if args.mode != 'summary' and args.arm is None:
        parser.error('%s needs --arm' % args.mode)
    if args.mode == 'walls':
        walls(args)
    elif args.mode == 'protocol-s':
        S.protocol_s(args)
    elif args.mode == 'protocol-e':
        S.protocol_e(args)
    elif args.mode == 'encounters':
        if args.arm == 'candidate' and not args.candidate_commit:
            parser.error('the candidate encounter runs need --candidate-commit')
        E.run(args)
    else:
        S.summary(args)
        E.summary(args)
        result = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
        result['walls'] = wall_summary()
        result['P6'] = p6()
        cand = result.get('candidate', {})
        result['P7'] = {'clock_saccade_rate_per_s': cand.get('clock_saccade_rate_per_s'),
                        'S3_match': cand.get('S3_match'),
                        'pass': bool(cand.get('P1_pass') and cand.get('S3_match'))}
        print('P7: candidate clock-driven saccades %s per s, S3 match %s: %s' % (
            '%.3f' % cand['clock_saccade_rate_per_s'] if cand else '-', cand.get('S3_match'),
            'pass' if result['P7']['pass'] else 'FAIL'))
        (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
