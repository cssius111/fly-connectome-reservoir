"""M3.5 research: do the M3.x candidates escape strikes? (read-only)

Exploratory. No runtime file changes. M3.4 found that a fly deciding by angular size never
escapes a hovering paddle, whose image stays below 31 deg (results/game/M3_4_RETINOTOPIC_DRIVE.md,
V6a). The N4B6 threat matrix has no strike. This tool measures strikes.

Protocol (the fixed-fly strike of tools/calibrate_escape.py, with the runtime decoder live):
- **Setup.** A fixed fly: collisions, fly motion and wander disabled. The paddle hovers at an
  offset from the fly in the fly's own frame, and settles for
  swatter.physical.calibration_settle_seconds.
- **Strike.** A strike is then launched and observed for 60 ticks (1.2 s).
- **Offsets.** Horizontal distances 0, 40, 80 and 150 units at bearings front, right, rear and
  left (13 positions). The paddle radius is 144 units, so 0-80 are hitting strikes and 150 a near
  miss.
- **Seeds.** 950001-950024, unused before.

Recorded per trial:
- the first escape tick after the click;
- the first ACTIVE_CONTACT tick (contact);
- the Retina theta and elevation at the escape;
- whether the escape came before contact.

Arms:
- v27: the working ROOM configuration (legacy encoder, N4B1C decoder);
- v29: the M3.3 candidate at 9830757 (ache2019_v1 encoder, doublet decoder);
- v30: the M3.4 candidate at 10e12f6 (retinotopic_v1 encoder, doublet decoder); it needs
  data/receptive_fields_v1.npz (tools/build_receptive_fields.py).

Each arm's decoder comes from its own committed record, exactly as the runtime loads it. Outputs
go to artifacts/m3_5/strikes/ (git-ignored), one file per arm and position, with the M3.0
provenance guard.

    NUMBA_NUM_THREADS=1 python tools/m3_5_strike_escapes.py run --arm v27
    NUMBA_NUM_THREADS=1 python tools/m3_5_strike_escapes.py run --arm v29
    NUMBA_NUM_THREADS=1 python tools/m3_5_strike_escapes.py run --arm v30
    python tools/m3_5_strike_escapes.py summary
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

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.session import Session, load_config  # noqa: E402
from game.world import StrikePhase  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/strikes'
ARMS = {'v27': None, 'v29': '9830757837a181114b15923df8929f231b710ce9',
        'v30': '10e12f6c29a285817e020b06b7c0dfc2d3ae5fe1'}
SEEDS = tuple(range(950001, 950025))
DISTANCES = (40.0, 80.0, 150.0)
BEARINGS_DEG = {'front': 0.0, 'right': 90.0, 'rear': 180.0, 'left': -90.0}
OBSERVE_TICKS = 60
CLICK_TICK = 0


def positions():
    out = {'overhead': (0.0, 0.0)}
    for d in DISTANCES:
        for name, b in BEARINGS_DEG.items():
            out['%s_%g' % (name, d)] = (d, b)
    return out


def arm_config(arm):
    commit = ARMS[arm]
    if commit is None:
        c = load_config(ROOT / 'game_room_config.json')
        if c['config_version'] != 27:
            raise SystemExit('the working ROOM configuration is not v27')
        return c
    return json.loads(subprocess.check_output(['git', 'show', commit + ':game_room_config.json'],
                                              cwd=ROOT, text=True))


def trial(session, seed, distance, bearing_deg):
    session.reset(seed)
    w = session.world
    fly = w.fly
    fly.vx = fly.vy = 0.0
    pose = (fly.x, fly.y, fly.heading)
    a = fly.heading + math.radians(bearing_deg)       # +bearing = to the fly's right
    pointer = (fly.x + distance * math.cos(a), fly.y + distance * math.sin(a))
    settle = round(session.config['swatter']['physical']['calibration_settle_seconds'] / session.tick_seconds)
    for _ in range(settle):
        session.tick(pointer=pointer, strike=False)
    sw = w.swatter
    if math.hypot(sw.vx, sw.vy) > 0.1 or math.hypot(sw.x - pointer[0], sw.y - pointer[1]) > 0.1:
        raise RuntimeError('paddle did not settle')
    pre_escapes = 0
    escape = contact = None
    hover = session.last_retina
    for t in range(OBSERVE_TICKS):
        session.tick(pointer=pointer, strike=(t == CLICK_TICK))
        if contact is None and sw.phase == StrikePhase.ACTIVE_CONTACT:
            contact = t
        if escape is None and session.fly_loop.last_action.escape:
            r = session.last_retina
            escape = {'tick': t, 'theta_deg': math.degrees(r.theta),
                      'elevation_deg': math.degrees(getattr(r, 'elevation', 0.0)),
                      'phase': sw.phase.value}
        if (fly.x, fly.y, fly.heading) != pose:
            raise RuntimeError('the fly moved')
    return {'seed': seed, 'contact_tick': contact, 'escape': escape,
            'hover_theta_deg': math.degrees(hover.theta),
            'before_contact': escape is not None and contact is not None and escape['tick'] < contact}


def run(arm):
    config = arm_config(arm)
    session = Session(config, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    out = OUT / arm
    M.check_provenance(out, '*.json')
    for name, (distance, bearing) in positions().items():
        path = out / ('%s.json' % name)
        if path.exists():
            continue
        rows = [trial(session, seed, distance, bearing) for seed in SEEDS]
        path.write_text(json.dumps({'arm': arm, 'position': name, 'distance': distance,
                                    'bearing_deg': bearing, 'trials': rows}) + '\n', encoding='utf-8')
        e = [r for r in rows if r['escape'] is not None]
        print('%s %-10s escaped %2d/%d, before contact %2d' % (
            arm, name, len(e), len(rows), sum(r['before_contact'] for r in rows)), flush=True)
    session.close()


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def summary():
    rows = {}
    for arm in ARMS:
        if not (OUT / arm).exists():
            continue
        M.recorded_provenance(OUT / arm)
        for name in positions():
            path = OUT / arm / ('%s.json' % name)
            if not path.exists():
                raise SystemExit('%s is incomplete: %s is missing' % (arm, path.name))
            t = json.loads(path.read_text(encoding='utf-8'))['trials']
            e = [r for r in t if r['escape'] is not None]
            rows.setdefault(name, {})[arm] = {
                'escaped': len(e) / len(t), 'before_contact': sum(r['before_contact'] for r in t) / len(t),
                'median_escape_tick': median(r['escape']['tick'] for r in e),
                'median_contact_tick': median(r['contact_tick'] for r in t),
                'median_theta_deg': median(r['escape']['theta_deg'] for r in e),
                'hover_theta_deg': median(r['hover_theta_deg'] for r in t)}
    (OUT / 'summary.json').write_text(json.dumps(rows, indent=1) + '\n', encoding='utf-8')
    arms = [a for a in ARMS if any(a in r for r in rows.values())]
    fmt = lambda v, s='%.0f': '-' if v is None else s % v
    print('position   | hover theta | ' + ' | '.join('%s: escaped, before contact, escape tick, theta' % a for a in arms))
    for name, r in rows.items():
        first = r[arms[0]]
        print('%-10s | %5.1f deg | %s' % (name, first['hover_theta_deg'], ' | '.join(
            '%.2f %.2f %s %s' % (r[a]['escaped'], r[a]['before_contact'], fmt(r[a]['median_escape_tick']),
                                 fmt(r[a]['median_theta_deg'])) for a in arms)))
    print('contact tick (median):', {name: r[arms[0]]['median_contact_tick'] for name, r in rows.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary'))
    parser.add_argument('--arm', choices=tuple(ARMS))
    args = parser.parse_args()
    if args.mode == 'run':
        if args.arm is None:
            parser.error('run needs --arm')
        run(args.arm)
    else:
        summary()


if __name__ == '__main__':
    main()
