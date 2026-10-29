"""M3.5 research: the decision time of the M3.4 candidate across the visual field (read-only).

Exploratory. No runtime file changes. game/M3_5_STRIKE_ESCAPE_RESEARCH.md (section 14) found that
the v30 decision time depends on the loom's position. At l/v 40 ms it decides 77 ms before
collision at the calibration position (azimuth 50°, elevation 11°) and 37 ms before at V2's
(azimuth 90°, elevation 0°), where a disk reaches 27 % less DNp01 weight. This tool maps that
dependence:
- **Grid.** Right azimuth 0, 30, 50, 70, 90, 110, 130 and 150°, by elevation 0, 25, 50 and 70°
  (the game's paddle hovers at about 20-70°).
- **Stimulus.** V2's loom from 10° (tools/m3_2_escape_roles.looming) at l/v 40 and 80 ms, decided
  by the v30 doublet decoder from its own record. Seeds 970401-970424.
- **Reach.** The static right-side and total DNp01 weight a 55° disk reaches at each position.

The comparator is the real-fly timing law X16 (game/M3_0_ESCAPE_EVIDENCE.md): takeoff
2.0 × l/v - 6 ms before collision (slope SD 0.2, intercept SD 11 ms), that is 74 ms at l/v 40 ms
and 154 ms at l/v 80 ms. Jang et al. 2023 found no difference in the GF's peak latency between
-45°, 0° and +45° azimuth on the horizon.

Outputs go to artifacts/m3_5/timing_map/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    NUMBA_NUM_THREADS=1 python tools/m3_5_timing_map.py trials --lane K --lanes 4   (K = 0-3)
    python tools/m3_5_timing_map.py reach
    python tools/m3_5_timing_map.py summary
"""
from __future__ import annotations

import argparse
import itertools
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

OUT = ROOT / 'artifacts/m3_5/timing_map'
AZIMUTHS = (0.0, 30.0, 50.0, 70.0, 90.0, 110.0, 130.0, 150.0)
ELEVATIONS = (0.0, 25.0, 50.0, 70.0)
LV_MS = (40, 80)
START_DEG = 10.0
SEEDS = tuple(range(970401, 970425))
REACH_SIZE_DEG = 55.0


def law_ms(lv_ms):
    """X16: real-fly takeoff time before collision, ms."""
    return 2.0 * lv_ms - 6.0


def conditions():
    return list(itertools.product(LV_MS, AZIMUTHS, ELEVATIONS))


def trials(args):
    M.check_provenance(OUT, 'lv*.json')
    T.check_fields(OUT)
    config, session = B.v30_session()
    dt = float(config['sim']['tick_seconds'])
    for k, (lv_ms, az, el) in enumerate(conditions()):
        if k % args.lanes != args.lane:
            continue
        path = OUT / ('lv%03d_az%03d_el%02d.json' % (lv_ms, az, el))
        if path.exists():
            continue
        retinas, pre, t0, thetas, last = R.looming(lv_ms / 1000.0, dt, START_DEG, None, M.WINDOW_AFTER_S)
        retinas = T.placed(retinas, az, el)
        rows = []
        for seed in SEEDS:
            escapes = R.run_trial(session, retinas, seed)
            first = next((e for e in escapes if pre <= e[0] <= last), None)
            row = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
                   'escaped': first is not None}
            if first is not None:
                row.update({'tick': first[0], 'tau_ms': 1000 * (t0 - (first[0] - pre + 1) * dt),
                            'theta_deg': math.degrees(thetas[first[0]])})
            rows.append(row)
        path.write_text(json.dumps({'lv_ms': lv_ms, 'azimuth_deg': az, 'elevation_deg': el,
                                    'trials': rows}, indent=1) + '\n', encoding='utf-8')
        print('lv %d az %g el %g: %d of %d escaped' % (lv_ms, az, el, sum(r['escaped'] for r in rows),
                                                       len(rows)), flush=True)
    session.close()


def reach(_args):
    import tools.m3_4_receptive_fields as RF
    from game.perception import view_direction
    M.check_provenance(OUT, 'lv*.json')
    T.check_fields(OUT)
    W = RF.weights().tocsr()
    _, session = B.v30_session()
    drive = session.encoder._retinotopic
    dn = B.dn_index(session.brain)
    rows = {s: W[dn['DNp01_' + s]].toarray().ravel() for s in 'LR'}
    out = {}
    for az, el in itertools.product(AZIMUTHS, ELEVATIONS):
        centre = view_direction(math.radians(az), math.radians(el))
        side = {'L': 0.0, 'R': 0.0}
        for ch, c in drive.channels.items():
            cov = drive.coverage(ch, centre, REACH_SIZE_DEG)
            for s in 'LR':
                on = c['side'] == s
                side[s] += float((cov[on] * rows[s][c['index'][on]]).sum())
        out['az%03d_el%02d' % (az, el)] = side
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'reach.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print('DNp01 reach of a %g deg disk, right / left side' % REACH_SIZE_DEG)
    for el in ELEVATIONS:
        print('  el %2g: %s' % (el, '  '.join('az %3g %.3f/%.3f' % (az, out['az%03d_el%02d' % (az, el)]['R'],
                                                                    out['az%03d_el%02d' % (az, el)]['L'])
                                            for az in AZIMUTHS)))


def cell(path):
    rows = json.loads(path.read_text(encoding='utf-8'))['trials']
    hit = [r for r in rows if r['escaped']]
    return {'n': len(rows), 'escaped': len(hit), 'before': sum(1 for r in hit if r['tau_ms'] > 0),
            'tau_ms': statistics.median(r['tau_ms'] for r in hit) if hit else None,
            'theta_deg': statistics.median(r['theta_deg'] for r in hit) if hit else None}


def summary(_args):
    reach_map = json.loads((OUT / 'reach.json').read_text(encoding='utf-8')) if (OUT / 'reach.json').exists() else {}
    pairs = []
    for lv_ms in LV_MS:
        print('== l/v %d ms: median decision time before collision, ms (escaped of 24); real-fly law %g ms'
              % (lv_ms, law_ms(lv_ms)))
        print('   el \\ az ' + ''.join('%11g' % az for az in AZIMUTHS))
        for el in ELEVATIONS:
            parts = []
            for az in AZIMUTHS:
                path = OUT / ('lv%03d_az%03d_el%02d.json' % (lv_ms, az, el))
                if not path.exists():
                    parts.append('%11s' % '-')
                    continue
                c = cell(path)
                parts.append('%11s' % ('%s (%d)' % ('%.0f' % c['tau_ms'] if c['tau_ms'] is not None else '-',
                                                    c['escaped'])))
                key = 'az%03d_el%02d' % (az, el)
                if c['tau_ms'] is not None and key in reach_map:
                    pairs.append((lv_ms, max(reach_map[key].values()), sum(reach_map[key].values()), c['tau_ms']))
            print('   %8g ' % el + ''.join(parts))
        print('   median size at decision, deg:')
        for el in ELEVATIONS:
            parts = []
            for az in AZIMUTHS:
                path = OUT / ('lv%03d_az%03d_el%02d.json' % (lv_ms, az, el))
                c = cell(path) if path.exists() else None
                parts.append('%11s' % ('%.0f' % c['theta_deg'] if c and c['theta_deg'] is not None else '-'))
            print('   %8g ' % el + ''.join(parts))
    for lv_ms in LV_MS:
        sel = [p for p in pairs if p[0] == lv_ms]
        if len(sel) > 2:
            larger = np.array([p[1] for p in sel])
            tau = np.array([p[3] for p in sel])
            r = np.corrcoef(larger, tau)[0, 1]
            print('l/v %d ms: correlation of decision time with the larger side\'s reach r = %.2f (n = %d)'
                  % (lv_ms, r, len(sel)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('trials', 'reach', 'summary'))
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    {'trials': trials, 'reach': reach, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
