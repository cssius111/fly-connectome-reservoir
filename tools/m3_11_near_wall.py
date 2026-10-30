"""M3.11 follow-up: near-wall time of the upwind surge across seed sets (read-only).

Exploratory, after the M3.11 result (results/game/M3_11_UPWIND_SURGE_RETEST.md, section 6). It
reads existing run outputs only and changes no runtime file.

**Near-wall share across seed sets.** Five paired seed sets of the same no-player protocol record the
flight generator's perimeter flag, under v32 and the surge candidate (v34 or v35, the same
configuration):
- M3.10 P7 and its replication, `tools/m3_10_saccade_loss.py` (artifacts/m3_10/saccade_loss/);
- M3.10 and M3.11 P6 wall runs, `tools/m3_9_checks.py` walls (artifacts/m3_10/walls/,
  artifacts/m3_11/walls/);
- M3.11 P7, `tools/m3_11_checks.py` factors (artifacts/m3_11/factors/).
For each set and for all five pooled, it prints the near-wall share of airborne time per arm and
the difference with a seed-bootstrap 95 % interval. Cochran's Q, from the bootstrap standard
errors, tests whether the sets agree.

**Where the time goes.** The odor runs (`tools/m3_10_checks.py` and `tools/m3_11_checks.py`
odor) record every tick's ecology state and wall clearance. A clearance under 3.4 BL stands in for
the perimeter flag. It prints the near-wall share by ecology state and within 5 s after an
ODOR_TRACK bout.

    python tools/m3_11_near_wall.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / 'artifacts'
ARMS = ('baseline', 'candidate')
STATES = ('EXPLORE', 'TRANSIT', 'ODOR_SEARCH', 'ODOR_TRACK', 'LAND_OR_PERCH', 'ALERT', 'ESCAPE', 'RECOVER')
TRACK = STATES.index('ODOR_TRACK')
NEAR_BL = 3.4
AFTER_TICKS = 250
BOOTSTRAP = 5000


def from_loss(directory, seeds):
    """Rows of (baseline airborne s, baseline near s, candidate airborne s, candidate near s)."""
    out = []
    for seed in seeds:
        row = []
        for arm in ARMS:
            z = np.load(directory / arm / ('seed%d.npz' % seed))
            rows, dt = z['rows'], float(z['dt'])
            air, near = rows[:, 0] > 0, rows[:, 3] > 0
            row += [air.sum() * dt, (air & near).sum() * dt]
        out.append(row)
    return np.array(out)


def from_walls(directory, seeds):
    out = []
    for seed in seeds:
        row = []
        for arm in ARMS:
            j = json.loads((directory / arm / ('seed%d.json' % seed)).read_text(encoding='utf-8'))
            c = j['counts']
            row += [c['airborne_ticks'] * j['dt'], c['near_wall_ticks'] * j['dt']]
        out.append(row)
    return np.array(out)


def difference(v):
    return v[:, 3].sum() / v[:, 2].sum() - v[:, 1].sum() / v[:, 0].sum()


def seed_sets():
    print('== near-wall share of airborne time, surge candidate minus v32')
    sets = {'M3.10 P7': from_loss(A / 'm3_10/saccade_loss', range(975501, 975521)),
            'M3.10 replication': from_loss(A / 'm3_10/saccade_loss/replication', range(976001, 976041)),
            'M3.10 P6 walls': from_walls(A / 'm3_10/walls', range(975101, 975125)),
            'M3.11 P6 walls': from_walls(A / 'm3_11/walls', range(977101, 977125)),
            'M3.11 P7': from_loss(A / 'm3_11/factors', range(977501, 977541))}
    rng = np.random.default_rng(3)
    estimates = []
    for name, v in list(sets.items()) + [('all five', np.concatenate(list(sets.values())))]:
        boots = np.array([difference(v[rng.integers(0, len(v), len(v))]) for _ in range(BOOTSTRAP)])
        d = difference(v)
        print('   %-18s %3d seeds: v32 %.3f, surge %.3f, difference %+.3f [%+.3f, %+.3f]' % (
            name, len(v), v[:, 1].sum() / v[:, 0].sum(), v[:, 3].sum() / v[:, 2].sum(), d,
            *np.percentile(boots, [2.5, 97.5])))
        if name != 'all five':
            estimates.append((d, boots.std()))
    d, se = np.array(estimates).T
    w = 1.0 / se ** 2
    mean = (w * d).sum() / w.sum()
    q = float((w * (d - mean) ** 2).sum())
    print('   inverse-variance mean %+.3f; Cochran Q %.1f on %d degrees of freedom' % (mean, q, len(d) - 1))


def odor_runs():
    runs = {'M3.10 odor': (A / 'm3_10/odor', range(975401, 975441)),
                 'M3.11 odor': (A / 'm3_11/odor', range(977401, 977441))}
    rng = np.random.default_rng(1)
    for name, (directory, seeds) in runs.items():
        print('== %s: near-wall share (clearance under %.1f BL) of airborne time' % (name, NEAR_BL))
        per = {}
        for arm in ARMS:
            by_state = np.zeros((len(STATES), 2))
            after = np.zeros(2)
            seed_rows = []
            for seed in seeds:
                rows = np.load(directory / arm / ('seed%d.npz' % seed))['rows']
                rows = rows[~np.isnan(rows[:, 1])]
                state, air, near = rows[:, 0].astype(int), rows[:, 1] > 0, rows[:, 5] < NEAR_BL
                post = np.zeros(len(rows), bool)
                last = -AFTER_TICKS
                for i, s in enumerate(state):
                    if s == TRACK:
                        last = i
                    elif i - last < AFTER_TICKS:
                        post[i] = True
                for k in range(len(STATES)):
                    m = air & (state == k)
                    by_state[k] += (m.sum(), (m & near).sum())
                after += ((air & post).sum(), (air & post & near).sum())
                seed_rows.append((air.sum(), (air & near).sum()))
            v = np.array(seed_rows, float)
            per[arm] = v
            total = v[:, 0].sum()
            print('   %s: %.3f overall; within %.0f s after an ODOR_TRACK bout %.3f' % (
                arm, v[:, 1].sum() / total, AFTER_TICKS * 0.02, after[1] / max(after[0], 1)))
            print('      by state (share of airborne time / near-wall share): ' + '; '.join(
                '%s %.3f / %.3f' % (STATES[k], by_state[k, 0] / total, by_state[k, 1] / by_state[k, 0])
                for k in range(len(STATES)) if by_state[k, 0] > 0))
        v = np.hstack([per['baseline'], per['candidate']])
        boots = [difference(v[rng.integers(0, len(v), len(v))]) for _ in range(BOOTSTRAP)]
        print('   difference %+.3f [%+.3f, %+.3f]' % (difference(v), *np.percentile(boots, [2.5, 97.5])))


def main():
    seed_sets()
    odor_runs()


if __name__ == '__main__':
    main()
