"""M1.8-N4B3 research: externally driven approach bouts in the human sessions (descriptive).

Research only; development data. Offline geometry labels bouts in which the paddle itself
closes the 3D range to the airborne fly outside a strike. The frozen N4B3 criteria
(tools/n4b3_criteria.py) are then scored on each bout. Geometry never enters a criterion.

Bout definition (fixed before scoring):
* swatter phase 'approach' (hover / chase, no strike);
* range rate caused by paddle motion <= -100 units/s (paddle closing on the fly);
* 3D range < 900 units;
* at least 10 consecutive brain-stepped samples (0.2 s); consecutive qualifying runs
  separated by < 5 samples are merged.

    python tools/n4b3_approach_bouts.py       # writes artifacts/m1_8_n4b3/approach_bouts.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from tools import n4b2_analysis as A  # noqa: E402
from tools import n4b3_analysis as B  # noqa: E402
from tools import n4b3_criteria as K  # noqa: E402

MIN_LEN, MERGE_GAP, CLOSING, MAX_RANGE = 10, 5, -100.0, 900.0


def geometry(row):
    f, sw = row['fly'], row['swatter']
    dx, dy = f['x'] - sw['x'], f['y'] - sw['y']
    rng = math.sqrt(dx * dx + dy * dy + sw['height'] ** 2)
    return rng, -(dx * sw['vx'] + dy * sw['vy']) / rng, (dx * f['vx'] + dy * f['vy']) / rng


def bouts(rows):
    ok = []
    for r in rows:
        rng, rr_pad, _ = geometry(r)
        ok.append(r['swatter']['phase'] == 'approach' and rr_pad <= CLOSING and rng < MAX_RANGE)
    runs, start = [], None
    for j, v in enumerate(ok + [False]):
        if v and start is None:
            start = j
        elif not v and start is not None:
            runs.append([start, j - 1])
            start = None
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < MERGE_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] + 1 >= MIN_LEN]


def main():
    hs, eps = B.human()
    names = K.FROZEN
    out = {'definition': {'min_samples': MIN_LEN, 'merge_gap': MERGE_GAP, 'paddle_range_rate_max': CLOSING,
                          'max_range': MAX_RANGE}, 'bouts': []}
    for (sess, ep), e in eps.items():
        for b0, b1 in bouts(e['rows']):
            s0 = max(0, b0 - 0)
            s1 = min(len(e['rows']), b1 + 11)       # score to 0.2 s after the bout ends
            seg = A.Seg('bout', 'bout', e['spikes'][s0:s1], e['tl'][s0:s1], e['tr'][s0:s1], None, None)
            seg.motion = e['motion'][s0:s1]
            g0, g1 = geometry(e['rows'][b0]), geometry(e['rows'][b1])
            row = {'session': sess, 'episode': ep, 'tick_start': e['rows'][b0]['tick'],
                   'tick_end': e['rows'][b1]['tick'], 'samples': b1 - b0 + 1,
                   'range_start': g0[0], 'range_end': g1[0],
                   'mean_forward_speed': float(np.mean(e['motion'][b0:b1 + 1, 0])),
                   'max_abs_yaw': float(np.max(np.abs(e['motion'][b0:b1 + 1, 2]))),
                   'first_firing': {}}
            for n in names:
                ev = B.events(seg, K.FAMILY[n])
                row['first_firing'][n] = None if not ev else ev[0][0]
            out['bouts'].append(row)
    summary = {}
    for n in names:
        lat = [b['first_firing'][n] for b in out['bouts']]
        d = [x for x in lat if x is not None]
        earlier = sum(1 for b in out['bouts'] if b['first_firing'][n] is not None and
                      (b['first_firing']['N4B1C (frozen runtime)'] is None or
                       b['first_firing'][n] < b['first_firing']['N4B1C (frozen runtime)']))
        summary[n] = {'detected': len(d), 'n': len(lat), 'median_s': float(np.median(d)) * 0.02 if d else None,
                      'earlier_than_n4b1c': earlier}
    out['summary'] = summary
    (ROOT / 'artifacts/m1_8_n4b3/approach_bouts.json').write_text(json.dumps(out, indent=1, default=float) + '\n',
                                                                  encoding='utf-8')
    print('bouts', len(out['bouts']))
    for n, v in summary.items():
        print('%-66s %s' % (n, v))


if __name__ == '__main__':
    main()
