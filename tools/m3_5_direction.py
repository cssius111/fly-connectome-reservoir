"""M3.5 research: can DNp02 against DNp11 give the escape direction? (read-only)

Exploratory. No runtime file changes. M3.0 scored E4, the takeoff direction:
- **Real fly.** "flies jumped backward in response to looming objects in front of them and jumped
  forward in response to looming objects behind them" (Card and Dickinson 2008).
- **Model.** v30 jumps forward from frontal looms (+4.5°), because the decoder's forward
  component is a constant (`forward_bias`) and its lateral component the DNp01 left-right
  contrast.
- **The DNs.** Dombrovski et al. 2023 found that "Activation of DNp11 evoked forward takeoffs",
  and that activating DNp02 with DNp04 "evoked a strong bias towards backward takeoffs"; the GF
  "is not expected to control the escape takeoff direction".

This tool records what a readout would see at the moment of the v30 doublet decision:
- **Traces.** The DNp02, DNp11, DNp01 and DNp04 traces in `MotorState.trace`, the policy's own
  input.
- **Spikes.** Their spikes from loom onset to the decision tick.

Stimulus: protocol-E looms, l/v 40 ms from 10°, at azimuth 0° (front), 90° (right), -90° (left)
and 180° (rear), at elevation 0° and 50°. The 50° elevation matches the real-fly assays (a disk
falling along a 50° trajectory; FlyPEZ looms at 45°). Seeds 970201-970224. The rule is the encoder
cell selection of tools/m3_5_side_balance.py.

Outputs go to artifacts/m3_5/direction/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    NUMBA_NUM_THREADS=1 python tools/m3_5_direction.py trials --rule all
    python tools/m3_5_direction.py summary
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_4_retinotopic as T  # noqa: E402
import tools.m3_5_side_balance as B  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/direction'
LV_MS = 40
AZIMUTHS = {'front': 0.0, 'right': 90.0, 'left': -90.0, 'rear': 180.0}
ELEVATIONS = (0.0, 50.0)
SEEDS = tuple(range(970201, 970225))
READ_DNS = ('DNp01', 'DNp02', 'DNp11', 'DNp04')


def run(session, retinas, seed, dn, slots, pre, last):
    """One fixed-fly trial; the first escape in [pre, last] with the DN traces and spike counts."""
    session.reset(seed)
    fly = session.world.fly
    fly.vx = fly.vy = 0.0
    pose = (fly.x, fly.y, fly.heading)
    counts, undo = T.dn_counter(session, dn)
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    result = {'seed': seed, 'escaped': False}
    try:
        for i in range(len(retinas)):
            session.tick()
            a = session.fly_loop.last_action
            if (fly.x, fly.y, fly.heading) != pose:
                raise RuntimeError('the fly moved')
            if a.escape and pre <= i <= last:
                trace = session.fly_loop.last_motor.trace
                result.update({'escaped': True, 'tick': i,
                               'direction_deg': math.degrees(math.atan2(a.lateral, a.forward)),
                               'trace': {k: float(trace[s]) for k, s in slots.items()},
                               'spikes': {k: int(sum(v[pre:i + 1])) for k, v in counts.items()}})
                break
    finally:
        del session.projector.project
        undo()
    return result


def trials(args):
    out = OUT / args.rule
    M.check_provenance(out, '*.json')
    T.check_fields(out)
    config, session = B.v30_session()
    B.install(session, args.rule)
    brain = session.brain
    dn = {'%s_%s' % (d, s): int(np.flatnonzero((brain.cell_type == d) & (brain.side == s))[0])
          for d in READ_DNS for s in 'LR'}
    slot_of = session.fly_loop.trace.slot
    slots = {k: int(slot_of[i]) for k, i in dn.items()}
    if min(slots.values()) < 0:
        raise SystemExit('a read DN is missing from the policy trace')
    dt = float(config['sim']['tick_seconds'])
    for el in ELEVATIONS:
        for name, az in AZIMUTHS.items():
            path = out / ('%s_el%02d.json' % (name, el))
            if path.exists():
                continue
            retinas, pre, t0, _ = M.stimulus(LV_MS / 1000.0, 0.5, dt)
            retinas = T.placed(retinas, az, el)
            last = pre + int(math.floor((t0 + M.WINDOW_AFTER_S) / dt + 1e-9)) - 1
            rows = [run(session, retinas, seed, dn, slots, pre, last) for seed in SEEDS]
            for r in rows:
                if r['escaped']:
                    r['t_before'] = t0 - (r['tick'] - pre + 1) * dt
            path.write_text(json.dumps({'lv_ms': LV_MS, 'azimuth_deg': az, 'elevation_deg': el,
                                        'trials': rows}, indent=1) + '\n', encoding='utf-8')
            print('%s %s el %g: %d of %d escaped' % (args.rule, name, el, sum(r['escaped'] for r in rows),
                                                    len(rows)), flush=True)
    session.close()


def contrast(d, key):
    """(DNp11 - DNp02) / (DNp11 + DNp02), both sides summed; positive reads forward."""
    fwd = d[key]['DNp11_L'] + d[key]['DNp11_R']
    back = d[key]['DNp02_L'] + d[key]['DNp02_R']
    return (fwd - back) / (fwd + back) if fwd + back > 0 else 0.0


def summary(_args):
    for rule in B.RULES:
        out = OUT / rule
        if not out.exists():
            continue
        print('== %s (l/v %d ms): escaped, before collision, current direction, DNp11-vs-DNp02 contrast '
              'from traces and from spikes (median; share > 0), DNp02 / DNp11 spikes (median)' % (rule, LV_MS))
        for el in ELEVATIONS:
            for name in AZIMUTHS:
                path = out / ('%s_el%02d.json' % (name, el))
                if not path.exists():
                    continue
                hit = [r for r in json.loads(path.read_text(encoding='utf-8'))['trials'] if r['escaped']]
                if not hit:
                    print('  %-5s el %2g: no escapes' % (name, el))
                    continue
                ct = [contrast(r, 'trace') for r in hit]
                cs = [contrast(r, 'spikes') for r in hit]
                med = statistics.median
                print('  %-5s el %2g: %2d, %2d before, dir %+6.1f deg | trace %+.2f (%.2f) | spikes %+.2f (%.2f) | '
                      'DNp02 %g, DNp11 %g' % (
                          name, el, len(hit), sum(1 for r in hit if r['t_before'] > 0),
                          med(r['direction_deg'] for r in hit), med(ct), np.mean([c > 0 for c in ct]),
                          med(cs), np.mean([c > 0 for c in cs]),
                          med(r['spikes']['DNp02_L'] + r['spikes']['DNp02_R'] for r in hit),
                          med(r['spikes']['DNp11_L'] + r['spikes']['DNp11_R'] for r in hit)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('trials', 'summary'))
    parser.add_argument('--rule', choices=B.RULES)
    args = parser.parse_args()
    if args.mode == 'trials' and args.rule is None:
        parser.error('trials needs --rule')
    {'trials': trials, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
