"""M3.5 research: why the M3.4 candidate fails V2 at l/v 40 ms (read-only).

Exploratory. No runtime file changes. V2 (start-size invariance) failed at l/v 40 ms: the median
sizes at escape for starts of 5°, 10° and 20° were 95.8°, 133.5° and 160.6°
(results/game/M3_4_RETINOTOPIC_DRIVE.md, section 4). That report described two clusters of
escapes, at 55-70° and at 130-180°.

This tool records, tick by tick, what decides each trial:
- θ and the time to collision τ;
- the right-side encoder cells at the 0.8 V cap;
- the synaptic input to the right DNp01 (gain times the weights of the cells that fired), which
  takes effect at the next tick;
- the right DNp01 spikes, and the tick of the doublet decision.

Conditions: l/v 40 ms, V2's stimulus (tools/m3_2_escape_roles.looming).
- **Starts.** 5°, 10° and 20° at V2's position, azimuth 90° and elevation 0°.
- **Positions.** A 10° start at the calibration position (azimuth 50°, elevation 11°) and at
  azimuth 90°, elevation 30°; 5° and 20° starts at the calibration position.
- **Tick-grid control.** A 19.144° start at V2's position. Its expansion time t0 has the same
  phase on the 20 ms tick grid as the 10° start's (17.2 ms), where the 20° start's is 6.9 ms.
Seeds 970301-970348, under the v30 candidate (`count` rule of tools/m3_5_side_balance.py).

Outputs go to artifacts/m3_5/v2_split/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    NUMBA_NUM_THREADS=1 python tools/m3_5_v2_split.py trace
    python tools/m3_5_v2_split.py summary
    python tools/m3_5_v2_split.py reach      # static DNp01 reach by disk position
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
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.m3_4_retinotopic as T  # noqa: E402
import tools.m3_5_side_balance as B  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/v2_split'
LV_MS = 40
CONDITIONS = {'start5_az90_el0': (5.0, 90.0, 0.0), 'start10_az90_el0': (10.0, 90.0, 0.0),
              'start20_az90_el0': (20.0, 90.0, 0.0), 'start10_az50_el11': (10.0, 50.0, 11.0),
              'start10_az90_el30': (10.0, 90.0, 30.0),
              # Tick-grid control: t0 mod 20 ms equals the 10-degree start's (17.2 ms; 20 deg gives 6.9 ms).
              'start19.144_az90_el0': (19.144, 90.0, 0.0),
              'start5_az50_el11': (5.0, 50.0, 11.0), 'start20_az50_el11': (20.0, 50.0, 11.0)}
SEEDS = tuple(range(970301, 970349))
CAP = 0.8
DOUBLET_INPUT_V = 0.41      # constant input per tick for a second spike within 2 ticks of a reset


def trial(session, retinas, seed, gf, row, right_cells, first, last):
    session.reset(seed)
    fly = session.world.fly
    fly.vx = fly.vy = 0.0
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    brain, encoder = session.brain, session.encoder
    original_inject, original_step = encoder.inject, brain.step
    ticks = []

    def inject(retina):
        out = original_inject(retina)
        capped = 0
        for idx, amount in out:
            if float(amount) >= CAP - 1e-6:
                capped += int(np.isin(idx, right_cells).sum())
        ticks.append({'capped_right': capped})
        return out

    def step(*args, **kwargs):
        fired = original_step(*args, **kwargs)
        ticks[-1]['dnp01_R'] = int(gf in fired)
        ticks[-1]['input_next'] = float(brain.gain * row[fired].sum())
        return fired
    encoder.inject, brain.step = inject, step
    decision = None
    try:
        for i in range(len(retinas)):
            session.tick()
            if decision is None and session.fly_loop.last_action.escape and first <= i <= last:
                decision = i
    finally:
        del session.projector.project
        del encoder.inject
        del brain.step
    return decision, ticks[first - 3:last + 1]


def trace(_args):
    import tools.m3_4_receptive_fields as RF
    M.check_provenance(OUT, '*.json')
    T.check_fields(OUT)
    config, session = B.v30_session()
    W = RF.weights().tocsr()
    gf = int(np.flatnonzero((session.brain.cell_type == 'DNp01') & (session.brain.side == 'R'))[0])
    row = W[gf].toarray().ravel()
    right_cells = np.concatenate([session.encoder._fd.cells['loom']['R'], session.encoder._fd.cells['threat']['R']])
    dt = float(config['sim']['tick_seconds'])
    for name, (start, az, el) in CONDITIONS.items():
        path = OUT / ('%s.json' % name)
        if path.exists():
            continue
        retinas, pre, t0, thetas, last = R.looming(LV_MS / 1000.0, dt, start, None, M.WINDOW_AFTER_S)
        retinas = T.placed(retinas, az, el)
        # tau at tick i: time to collision at the end of the tick, as in timed_trials.
        tau = [t0 - (i - pre + 1) * dt for i in range(len(retinas))]
        rows = []
        for seed in SEEDS:
            decision, ticks = trial(session, retinas, seed, gf, row, right_cells, pre, last)
            rows.append({'seed': seed, 'decision': decision, 'ticks': ticks})
        path.write_text(json.dumps({'lv_ms': LV_MS, 'start_deg': start, 'azimuth_deg': az, 'elevation_deg': el,
                                    'onset': pre, 'last': last, 'first_recorded': pre - 3,
                                    'tau_s': tau, 'theta_deg': [math.degrees(t) for t in thetas],
                                    'trials': rows}) + '\n', encoding='utf-8')
        print('%s: %d of %d decided' % (name, sum(r['decision'] is not None for r in rows), len(rows)), flush=True)
    session.close()


def summary(_args):
    for name in CONDITIONS:
        path = OUT / ('%s.json' % name)
        if not path.exists():
            continue
        d = json.loads(path.read_text(encoding='utf-8'))
        base = d['first_recorded']
        decided = [r for r in d['trials'] if r['decision'] is not None]
        taus = [1000 * d['tau_s'][r['decision']] for r in decided]
        sizes = [d['theta_deg'][r['decision']] for r in decided]
        print('== %s: %d of %d decided; median tau %.0f ms, median size %.1f deg' % (
            name, len(decided), len(d['trials']), statistics.median(taus), statistics.median(sizes)))
        bins = {}
        for r in decided:
            bins[r['decision']] = bins.get(r['decision'], 0) + 1
        # Per tick near collision: tau, theta, decisions, mean capped cells, mean DNp01 input, spike rate.
        for i in range(base, d['last'] + 1):
            k = i - base
            if not -0.03 <= d['tau_s'][i] <= 0.16:
                continue
            cap = [r['ticks'][k]['capped_right'] for r in d['trials'] if k < len(r['ticks'])]
            inp = [r['ticks'][k - 1]['input_next'] for r in d['trials'] if 0 < k < len(r['ticks'])]
            spk = [r['ticks'][k]['dnp01_R'] for r in d['trials'] if k < len(r['ticks'])]
            print('   tick %3d  tau %+5.0f ms  theta %5.1f  decisions %2d | capped %5.1f  DNp01 input %.3f  '
                  'spike rate %.2f' % (i, 1000 * d['tau_s'][i], d['theta_deg'][i], bins.get(i, 0),
                                        np.mean(cap), np.mean(inp), np.mean(spk)))
        # Spikes before the decision that did not pair: isolated DNp01 spikes from onset.
        lone = []
        for r in decided:
            k_dec = r['decision'] - base
            spikes = [k for k in range(3, k_dec + 1) if r['ticks'][k]['dnp01_R']]
            lone.append(max(0, len(spikes) - 2))
        print('   spikes before the decisive pair (median, max): %s, %s' % (statistics.median(lone), max(lone)))


def reach(_args):
    """The right DNp01 weight a disk reaches (coverage-weighted, no dynamics), by position."""
    import tools.m3_4_receptive_fields as RF
    from game.perception import view_direction
    W = RF.weights().tocsr()
    _, session = B.v30_session()
    drive = session.encoder._retinotopic
    gf = int(np.flatnonzero((session.brain.cell_type == 'DNp01') & (session.brain.side == 'R'))[0])
    row = W[gf].toarray().ravel()
    print('right DNp01 reach for disks of 40, 55 and 70 deg (count rule)')
    for el in (0.0, 11.0, 30.0):
        for az in (30.0, 50.0, 70.0, 90.0):
            centre = view_direction(math.radians(az), math.radians(el))
            values = []
            for size in (40.0, 55.0, 70.0):
                total = 0.0
                for ch, c in drive.channels.items():
                    on = c['side'] == 'R'
                    total += float((drive.coverage(ch, centre, size)[on] * row[c['index'][on]]).sum())
                values.append(total)
            print('  az %2g el %2g: %s' % (az, el, ' '.join('%.4f' % v for v in values)))
    session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('trace', 'summary', 'reach'))
    args = parser.parse_args()
    {'trace': trace, 'summary': summary, 'reach': reach}[args.mode](args)


if __name__ == '__main__':
    main()
