"""M3.5 research: the posterior blind spot of the M3.4 retinotopic encoder (read-only).

Exploratory, descriptive. No runtime file changes. Under v30 rear looms escaped rarely and only
after collision (results/game/M3_4_RETINOTOPIC_DRIVE.md, V1), and rear strikes were rarely escaped
(game/M3_5_STRIKE_ESCAPE_RESEARCH.md). The M3.0 protocol-E rear loom sits on the horizon straight
behind the fly. The real-fly rear data come from elevated threats: a disk falling along a 50°
downward trajectory (Card and Dickinson 2008), or FlyPEZ looms at 45° elevation (Dombrovski et al.
2023).

Subcommands:
- `coverage`: the coverage-weighted DNp01, DNp02 and DNp11 input weight (both sides summed) of
  disks centred at azimuth 90-180° and elevation 0°, 30° and 50°, for sizes 20-120°. No dynamics.
- `trials --rule R`: protocol-E looms (l/v 40 and 80 ms, from 10°) at four positions, decided by
  the v30 doublet decoder:
  - lateral on the horizon (az 90°, el 0°);
  - lateral elevated (az 90°, el 50°);
  - rear on the horizon (az 180°, el 0°);
  - rear elevated (az 180°, el 50°).
  Seeds 970101-970124. The rule is the encoder cell selection of tools/m3_5_side_balance.py.

Outputs go to artifacts/m3_5/rear_field/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    python tools/m3_5_rear_field.py coverage
    NUMBA_NUM_THREADS=1 python tools/m3_5_rear_field.py trials --rule count
    python tools/m3_5_rear_field.py summary
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

from game.perception import view_direction  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.m3_4_retinotopic as T  # noqa: E402
import tools.m3_5_side_balance as B  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/rear_field'
POSITIONS = {'lateral_el0': (90.0, 0.0), 'lateral_el50': (90.0, 50.0),
             'rear_el0': (180.0, 0.0), 'rear_el50': (180.0, 50.0)}
LV_MS = (40, 80)
SEEDS = tuple(range(970101, 970125))
COVERAGE_AZIMUTHS = (90.0, 135.0, 150.0, 165.0, 180.0)
COVERAGE_ELEVATIONS = (0.0, 30.0, 50.0)
COVERAGE_SIZES = (20.0, 40.0, 60.0, 90.0, 120.0)


def coverage(_args):
    import tools.m3_4_receptive_fields as RF
    W = RF.weights().tocsr()
    _, session = B.v30_session()
    dn = B.dn_index(session.brain)
    out = {}
    for rule in ('count', 'all'):
        B.install(session, rule, W)
        drive = session.encoder._retinotopic
        rows = {}
        for el in COVERAGE_ELEVATIONS:
            for az in COVERAGE_AZIMUTHS:
                centre = view_direction(math.radians(az), math.radians(el))
                for size in COVERAGE_SIZES:
                    reach = {d: 0.0 for d in ('DNp01', 'DNp02', 'DNp11')}
                    for ch, c in drive.channels.items():
                        cov = drive.coverage(ch, centre, size)
                        for s in 'LR':
                            on = c['side'] == s
                            for d in reach:
                                reach[d] += float((cov[on] * W[dn['%s_%s' % (d, s)]][:, c['index'][on]]
                                                   .toarray().ravel()).sum())
                    rows['az%g_el%g_%g' % (az, el, size)] = reach
        out[rule] = rows
        print('== %s: DNp01 reach (both sides) by disk size %s' % (rule, COVERAGE_SIZES))
        for el in COVERAGE_ELEVATIONS:
            for az in COVERAGE_AZIMUTHS:
                print('  az %3g el %2g: %s' % (az, el, ' '.join(
                    '%.4f' % rows['az%g_el%g_%g' % (az, el, size)]['DNp01'] for size in COVERAGE_SIZES)))
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'coverage.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')


def trials(args):
    out = OUT / args.rule
    M.check_provenance(out, '*.json')
    T.check_fields(out)
    config, session = B.v30_session()
    B.install(session, args.rule)
    dt = float(config['sim']['tick_seconds'])
    for lv_ms in LV_MS:
        for name, (az, el) in POSITIONS.items():
            path = out / ('lv%03d_%s.json' % (lv_ms, name))
            if path.exists():
                continue
            retinas, pre, t0, thetas = M.stimulus(lv_ms / 1000.0, 0.5, dt)
            retinas = T.placed(retinas, az, el)
            last = pre + int(math.floor((t0 + M.WINDOW_AFTER_S) / dt + 1e-9)) - 1
            rows = []
            for seed in SEEDS:
                escapes = R.run_trial(session, retinas, seed)
                first = next((e for e in escapes if pre <= e[0] <= last), None)
                row = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
                       'escaped': first is not None}
                if first is not None:
                    row.update({'tick': first[0], 't_before': t0 - (first[0] - pre + 1) * dt,
                                'theta_deg': math.degrees(thetas[first[0]])})
                rows.append(row)
            path.write_text(json.dumps({'lv_ms': lv_ms, 'position': name, 'azimuth_deg': az,
                                        'elevation_deg': el, 't0': t0, 'trials': rows}, indent=1)
                            + '\n', encoding='utf-8')
            print('%s lv %d ms %s: %d of %d escaped' % (args.rule, lv_ms, name,
                                                       sum(r['escaped'] for r in rows), len(rows)), flush=True)
    session.close()


def summary(_args):
    for rule in B.RULES:
        out = OUT / rule
        if not out.exists():
            continue
        print('== %s: escaped, before collision, median t_before, median theta' % rule)
        for lv_ms in LV_MS:
            for name in POSITIONS:
                path = out / ('lv%03d_%s.json' % (lv_ms, name))
                if not path.exists():
                    continue
                rows = json.loads(path.read_text(encoding='utf-8'))['trials']
                hit = [r for r in rows if r['escaped']]
                before = sum(1 for r in hit if r['t_before'] > 0)
                print('  lv %2d %-13s %2d/%d, %2d before, %s' % (
                    lv_ms, name, len(hit), len(rows), before,
                    '%+5.0f ms, %5.1f deg' % (1000 * statistics.median(r['t_before'] for r in hit),
                                              statistics.median(r['theta_deg'] for r in hit)) if hit else '-'))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('coverage', 'trials', 'summary'))
    parser.add_argument('--rule', choices=B.RULES)
    args = parser.parse_args()
    if args.mode == 'trials' and args.rule is None:
        parser.error('trials needs --rule')
    {'coverage': coverage, 'trials': trials, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
