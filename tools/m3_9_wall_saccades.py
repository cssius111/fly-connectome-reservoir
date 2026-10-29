"""M3.9 research: wall-evoked turns of the model against the real fly (read-only).

Exploratory. No runtime file changes. Real saccades are mostly triggered by visual expansion
(Tammero and Dickinson 2002, J Exp Biol 205:327-343; 1 m cylinder, textured and uniform walls):
- **Amplitude.** About ±90°, independent of the approach angle to the wall: within each turn
  direction, regressions of saccade angle on approach angle have slopes 0.05 and 0.14 and
  r² < 0.01.
- **Direction.** It depends on the approach angle: the fly turns away from the side where the
  wall is nearer.
- **Trigger.** It is not a time-to-collision threshold. Slower flies (textured walls) saccade
  farther from the walls, which a time-to-collision rule would not give.

The model's wall turns are `flight.FreeFlightController` events:
- **AVOID.** It fires when the time to contact with the surface being closed on falls to
  `avoid_time_to_contact_seconds`. It turns onto the wall tangent plus `avoid_inward_degrees`.
- **DEPART.** It fires after a sampled patience near the perimeter.

**Runs.** 180 s no-player ROOM runs with the pointer parked, under the working ROOM
configuration, on seeds 974001-974012.

**Each accepted AVOID or DEPART request records:**
- the approach angle: the body-frame bearing of the wall's outward normal, as in Tammero and
  Dickinson's definition;
- the clearance to that wall, in body lengths;
- the speed;
- the time to contact;
- the signed requested turn;
- whether the turn is away from the wall.
SACCADE and CORRECTION requests are counted for the share.

**summary.** It reports, per kind:
- the amplitude distribution;
- the amplitude-on-approach-angle regression within each turn direction;
- the trigger distance and its regression on speed;
- the share of turns away from the wall.

Outputs go to artifacts/m3_9/wall_saccades/ (git-ignored).

    NUMBA_NUM_THREADS=1 python tools/m3_9_wall_saccades.py run --lane K --lanes 2
    python tools/m3_9_wall_saccades.py summary
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.enclosure import wrap  # noqa: E402
from game.session import Session, load_config  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402

OUT = ROOT / 'artifacts/m3_9/wall_saccades'
SEEDS = tuple(range(974001, 974013))
TICKS = 9000
KINDS = ('AVOID', 'DEPART', 'SACCADE', 'CORRECTION')
FIELDS = ('tick', 'kind', 'approach_deg', 'clearance_bl', 'speed_bl_s', 'ttc_s', 'turn_deg', 'away')


def wall_geometry(world, bearing):
    """Clearance (world units) and closing speed for the wall whose normal has this bearing."""
    fly = world.fly
    best = None
    for _side, clearance, (nx, ny), _along in world.enclosure._walls(fly.x, fly.y):
        b = wrap(math.atan2(ny, nx) - fly.heading)
        if best is None or abs(wrap(b - bearing)) < abs(wrap(best[0] - bearing)):
            best = (b, clearance, fly.vx * nx + fly.vy * ny)
    return best[1], best[2]


def run(args):
    config = load_config(ROOT / 'game_room_config.json')
    OUT.mkdir(parents=True, exist_ok=True)
    M.check_provenance(OUT, 'seed*.json')
    brain = None
    for k, seed in enumerate(SEEDS):
        if k % args.lanes != args.lane:
            continue
        path = OUT / ('seed%d.json' % seed)
        if path.exists():
            continue
        session = Session(config, brain=brain, seed=seed, mode='evaluation')
        brain, world = session.brain, session.world
        body = world.body_length
        events, airborne_ticks = [], 0
        request = world.saccades.request

        def logged(kind, angle, peak_rate):
            accepted = request(kind, angle, peak_rate)
            if not accepted or kind not in KINDS:
                return accepted
            cue = world.wall_cue
            bearing = cue.contact_bearing if kind == 'AVOID' else cue.surface_bearing
            clearance, closing = wall_geometry(world, bearing)
            speed = math.hypot(world.fly.vx, world.fly.vy)
            # A turn is away from the wall when it moves the wall's bearing away from straight ahead.
            away = abs(wrap(bearing - angle)) > abs(bearing)
            events.append((session.ticks, kind, math.degrees(bearing), clearance / body, speed / body,
                           clearance / closing if closing > 1e-9 else None, math.degrees(angle), bool(away)))
            return accepted

        world.saccades.request = logged
        for _ in range(TICKS):
            session.tick(pointer=M.PARKED)
            if not world.fly.alive:
                break
            airborne_ticks += int(not (world.lifecycle_active and world.lifecycle.stationary))
        session.close()
        path.write_text(json.dumps({'seed': seed, 'config_version': config['config_version'],
                                    'airborne_seconds': airborne_ticks * config['sim']['tick_seconds'],
                                    'fields': FIELDS, 'events': events}) + '\n', encoding='utf-8')
        print('seed %d: %d events' % (seed, len(events)), flush=True)


def regression(x, y):
    if len(x) < 3:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = np.corrcoef(x, y)[0, 1]
    return {'n': len(x), 'slope': float(slope), 'intercept': float(intercept), 'r2': float(r * r)}


def summary(_args):
    paths = [OUT / ('seed%d.json' % s) for s in SEEDS]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        sys.exit('incomplete: %s' % ', '.join(missing))
    M.recorded_provenance(OUT)
    runs = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    airborne = sum(r['airborne_seconds'] for r in runs)
    rows = [dict(zip(FIELDS, e)) for r in runs for e in r['events']]
    result = {'config_versions': sorted({r['config_version'] for r in runs}), 'airborne_s': airborne,
              'rates_per_s': {k: sum(1 for e in rows if e['kind'] == k) / airborne for k in KINDS}, 'kinds': {}}
    for kind in ('AVOID', 'DEPART'):
        ev = [e for e in rows if e['kind'] == kind]
        amp = np.array([abs(e['turn_deg']) for e in ev])
        app = np.array([abs(e['approach_deg']) for e in ev])
        k = {'n': len(ev), 'amplitude_deg': {'median': float(np.median(amp)), 'p10': float(np.percentile(amp, 10)),
                                               'p90': float(np.percentile(amp, 90))},
             'approach_abs_deg': {'median': float(np.median(app)), 'p10': float(np.percentile(app, 10)),
                                  'p90': float(np.percentile(app, 90))},
             'away_share': float(np.mean([e['away'] for e in ev])),
             'clearance_bl': {'median': float(np.median([e['clearance_bl'] for e in ev])),
                              'p10': float(np.percentile([e['clearance_bl'] for e in ev], 10)),
                              'p90': float(np.percentile([e['clearance_bl'] for e in ev], 90))}}
        # Tammero and Dickinson's regression: signed saccade angle on signed approach angle, per direction.
        for sign, label in ((1, 'right_turns'), (-1, 'left_turns')):
            sel = [e for e in ev if np.sign(e['turn_deg']) == sign]
            k[label] = regression(np.array([e['approach_deg'] for e in sel]), np.array([e['turn_deg'] for e in sel]))
        k['amplitude_on_abs_approach'] = regression(app, amp)
        timed = [e for e in ev if e['ttc_s'] is not None]
        k['ttc_s_median'] = float(np.median([e['ttc_s'] for e in timed])) if timed else None
        k['clearance_on_speed'] = regression(np.array([e['speed_bl_s'] for e in ev]),
                                             np.array([e['clearance_bl'] for e in ev]))
        result['kinds'][kind] = k
        print('== %s: %d events (%.3f per airborne s); away from the wall %.2f' % (
            kind, len(ev), result['rates_per_s'][kind], k['away_share']))
        print('   amplitude median %.0f deg (p10 %.0f, p90 %.0f); |approach| median %.0f deg (p10 %.0f, p90 %.0f)' % (
            k['amplitude_deg']['median'], k['amplitude_deg']['p10'], k['amplitude_deg']['p90'],
            k['approach_abs_deg']['median'], k['approach_abs_deg']['p10'], k['approach_abs_deg']['p90']))
        for label in ('right_turns', 'left_turns', 'amplitude_on_abs_approach', 'clearance_on_speed'):
            g = k[label]
            if g:
                print('   %s: n %d, slope %.2f, intercept %.1f, r2 %.2f' % (label, g['n'], g['slope'], g['intercept'], g['r2']))
        print('   clearance median %.1f BL (p10 %.1f, p90 %.1f); time to contact median %s s' % (
            k['clearance_bl']['median'], k['clearance_bl']['p10'], k['clearance_bl']['p90'],
            '%.2f' % k['ttc_s_median'] if k['ttc_s_median'] is not None else '-'))
    print('rates per airborne s: ' + ', '.join('%s %.3f' % kv for kv in result['rates_per_s'].items()))
    (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary'))
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    {'run': run, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
