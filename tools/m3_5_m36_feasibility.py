"""M3.5 research: could an M3.6 candidate pass V2 and V3 together? (read-only)

Exploratory. Nothing in the runtime, the configuration or data/ changes. Every change below is
applied in one research process's memory only.

**The candidate explored.** The M3.4 retinotopic encoder with:
- **cells.** Every LPLC2 and LC4 cell (rule `all`, game/M3_5_STRIKE_ESCAPE_RESEARCH.md
  section 10);
- **commissural gain.** g = 10 on the PVLP151, AMMC-A1 and DNp11 weights onto the opposite DNp01
  (section 17);
- **scale.** One value per run: 40, 71.3 (the v30 value), 140, 280, 560 or 1120 V/mV.

**Measurements per scale.** All use the v30 doublet decoder.
- **Lateral calibration.** M3.4's calibration stimulus (10° to 90°, l/v 10, 20, 40 and 80 ms),
  moved to the lateral horizon (azimuth 90°, elevation 0°), where the behavioural comparators
  were measured. Two target sets are scored:
  - the Ache et al. 2019 GF-model peaks: -2.3, -29.7, -81.3 and -183.8 ms;
  - the real-fly law X16 (2.0 × l/v - 6 ms): -14, -34, -74 and -154 ms.
  Loss and admissibility (at least 50 % escapes at every l/v) follow
  tools/m3_2_escape_roles.calibration_choice. Seeds 971001-971024.
- **V2.** Start-size invariance as preregistered for M3.4: l/v 40, 80 and 160 ms from 5°, 10°
  and 20°, right azimuth, elevation 0. It passes when at each l/v the median sizes at escape lie
  within 10° of each other.
- **V3.** Held-out l/v 15, 30 and 60 ms on the M3.4 calibration stimulus at azimuth 50°,
  elevation 11°. It passes when every median escape time lies within 30 ms of the GF-model peak
  (-16.4, -55.7, -132.6 ms).
- **Seeds.** V2 and V3 use seeds 971101-971124.

**Reference.** `--variant v30` runs the v30 candidate unchanged (count rule, g = 1) at 71.3
V/mV on the same seeds.

Outputs go to artifacts/m3_5/m36_feasibility/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    NUMBA_NUM_THREADS=1 python tools/m3_5_m36_feasibility.py run --scale S          (each S)
    NUMBA_NUM_THREADS=1 python tools/m3_5_m36_feasibility.py run --scale 71.3 --variant v30
    python tools/m3_5_m36_feasibility.py summary
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

import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_ache_targets as A  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.m3_4_retinotopic as T  # noqa: E402
import tools.m3_5_bilateral_gain as G  # noqa: E402
import tools.m3_5_side_balance as B  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/m36_feasibility'
SCALES = (40.0, 71.3, 140.0, 280.0, 560.0, 1120.0)
GAIN = 10.0
CAL_SEEDS = tuple(range(971001, 971025))
CHECK_SEEDS = tuple(range(971101, 971125))
LATERAL = (90.0, 0.0)
V2_LV_MS, V2_START_DEG, V2_TOLERANCE_DEG = (40, 80, 160), (5.0, 10.0, 20.0), 10.0
V3_TOLERANCE_MS = 30.0


def gf_targets(lvs):
    return {r['lv_ms']: r['peak_time_ms'] for r in A.targets(lvs)}


def law_targets(lvs):
    return {lv: -(2.0 * lv - 6.0) for lv in lvs}


def placed_trials(session, lv_ms, start_deg, stop_deg, end_after_s, seeds, dt, az, el):
    retinas, pre, t0, thetas, last = R.looming(lv_ms / 1000.0, dt, start_deg, stop_deg, end_after_s)
    retinas = T.placed(retinas, az, el)
    rows = []
    for seed in seeds:
        escapes = R.run_trial(session, retinas, seed)
        first = next((e for e in escapes if pre <= e[0] <= last), None)
        row = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
               'escaped': first is not None}
        if first is not None:
            row.update({'t_rel_ms': 1000 * ((first[0] - pre + 1) * dt - t0),
                        'theta_deg': math.degrees(thetas[first[0]])})
        rows.append(row)
    return rows


def run(args):
    out = OUT / ('%s_s%07.2f' % (args.variant, args.scale))
    M.check_provenance(out, 'result.json')
    T.check_fields(out)
    if (out / 'result.json').exists():
        return
    config, session = B.v30_session()
    if args.variant == 'm36':
        B.install(session, 'all')
        G.apply_gain(session.brain, GAIN)
    session.encoder._retinotopic.scale = float(args.scale)
    dt = float(config['sim']['tick_seconds'])
    result = {'variant': args.variant, 'scale': args.scale, 'calibration': {}, 'v2': {}, 'v3': {}}
    worst = max(max(gf_targets(A.CALIBRATION_LV_MS).values()), max(law_targets(A.CALIBRATION_LV_MS).values()))
    for lv_ms in A.CALIBRATION_LV_MS:
        result['calibration'][str(lv_ms)] = placed_trials(
            session, lv_ms, 10.0, 90.0, worst / 1000.0 + R.WINDOW_AFTER_TARGET_S, CAL_SEEDS, dt, *LATERAL)
    print('%s %g: lateral calibration done' % (args.variant, args.scale), flush=True)
    goal = gf_targets(A.HELD_OUT_LV_MS)
    for lv_ms in A.HELD_OUT_LV_MS:
        result['v3'][str(lv_ms)] = placed_trials(
            session, lv_ms, 10.0, 90.0, goal[lv_ms] / 1000.0 + R.WINDOW_AFTER_TARGET_S, CHECK_SEEDS, dt,
            T.ACHE_AZIMUTH_DEG, T.ACHE_ELEVATION_DEG)
    print('%s %g: V3 done' % (args.variant, args.scale), flush=True)
    for lv_ms in V2_LV_MS:
        for start in V2_START_DEG:
            result['v2']['%d_%g' % (lv_ms, start)] = placed_trials(
                session, lv_ms, start, None, M.WINDOW_AFTER_S, CHECK_SEEDS, dt, *LATERAL)
    print('%s %g: V2 done' % (args.variant, args.scale), flush=True)
    session.close()
    (out / 'result.json').write_text(json.dumps(result) + '\n', encoding='utf-8')


def med(rows, key):
    hit = [r[key] for r in rows if r['escaped']]
    return statistics.median(hit) if hit else None


def score(rows_by_lv, targets):
    per, admissible = {}, True
    for lv_ms, rows in rows_by_lv.items():
        frac = sum(r['escaped'] for r in rows) / len(rows)
        admissible &= frac >= R.ADMISSIBLE_FRACTION
        per[int(lv_ms)] = (frac, med(rows, 't_rel_ms'))
    loss = sum((t - targets[lv]) ** 2 for lv, (_, t) in per.items()) if admissible else None
    return per, loss


def summary(_args):
    gf, law = gf_targets(A.CALIBRATION_LV_MS), law_targets(A.CALIBRATION_LV_MS)
    v3_goal = gf_targets(A.HELD_OUT_LV_MS)
    rows = []
    for path in sorted(OUT.glob('*/result.json')):
        r = json.loads(path.read_text(encoding='utf-8'))
        per, loss_gf = score(r['calibration'], gf)
        _, loss_law = score(r['calibration'], law)
        v3 = {int(lv): med(rows_, 't_rel_ms') for lv, rows_ in r['v3'].items()}
        v3_ok = all(v is not None and abs(v - v3_goal[lv]) <= V3_TOLERANCE_MS for lv, v in v3.items())
        v2 = {}
        for lv_ms in V2_LV_MS:
            sizes = [med(r['v2']['%d_%g' % (lv_ms, s)], 'theta_deg') for s in V2_START_DEG]
            v2[lv_ms] = (sizes, max(sizes) - min(sizes) if None not in sizes else None)
        v2_ok = all(spread is not None and spread <= V2_TOLERANCE_DEG for _, spread in v2.values())
        rows.append((r['variant'], r['scale'], loss_gf, loss_law, v2_ok, v3_ok))
        print('== %s, scale %g' % (r['variant'], r['scale']))
        print('   lateral calibration (escape fraction, median t ms): %s | loss vs GF model %s, vs X16 law %s' % (
            ', '.join('%d ms %.2f %s' % (lv, f, '-' if t is None else '%+.0f' % t) for lv, (f, t) in sorted(per.items())),
            '-' if loss_gf is None else '%.0f' % loss_gf, '-' if loss_law is None else '%.0f' % loss_law))
        print('   V3 (Ache position): %s -> %s' % (', '.join(
            '%d ms %s (target %.1f)' % (lv, '-' if v is None else '%+.1f' % v, v3_goal[lv]) for lv, v in sorted(v3.items())),
            'pass' if v3_ok else 'FAIL'))
        print('   V2 (lateral): %s -> %s' % ('; '.join(
            '%d ms %s spread %s' % (lv, '/'.join('-' if x is None else '%.1f' % x for x in sizes),
                                    '-' if spread is None else '%.1f' % spread)
            for lv, (sizes, spread) in sorted(v2.items())), 'pass' if v2_ok else 'FAIL'))
    m36 = [x for x in rows if x[0] == 'm36']
    for label, k in (('GF-model targets', 2), ('X16 law targets', 3)):
        ok = [x for x in m36 if x[k] is not None]
        if ok:
            best = min(ok, key=lambda x: (x[k], x[1]))
            print('lateral calibration on %s chooses scale %g: V2 %s, V3 %s' % (
                label, best[1], 'pass' if best[4] else 'FAIL', 'pass' if best[5] else 'FAIL'))
    both = [x[1] for x in m36 if x[4] and x[5]]
    print('scales where V2 and V3 both pass: %s' % (both or 'none'))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary'))
    parser.add_argument('--scale', type=float)
    parser.add_argument('--variant', choices=('m36', 'v30'), default='m36')
    args = parser.parse_args()
    if args.mode == 'run' and args.scale is None:
        parser.error('run needs --scale')
    {'run': run, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
