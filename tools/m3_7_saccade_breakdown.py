"""M3.7 research: where the model's spontaneous saccades come from (read-only).

Exploratory. No runtime file changes. M3.0 (results/game/M3_0_FIDELITY_SCORECARD.md, protocol S)
found 0.34 spontaneous events per airborne second against 1.37 for real flies (E12), with a median
of 57° in 80 ms against about 90° in under 100 ms (E10).

This tool reads the M3.0 protocol-S raw data (artifacts/m3_0/saccades/, seeds 9501-9520). It uses
the M3.0 detector unchanged: runs of at least 450°/s of one sign, threat-evoked runs excluded. It
reports:
- **By kind.** The detected events by the actuator kind that produced them:
  - SACCADE and CORRECTION, from the free-flight clock;
  - AVOID and DEPART, from the wall cue.
- **Pulse geometry.** For the half-sine pulse of game/saccade.py, the share of a pulse's angle and
  duration that the 450°/s detector sees, by peak rate. This links the generator's parameters to
  the measured amplitude and duration.

    python tools/m3_7_saccade_breakdown.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.m3_0_scorecard as M  # noqa: E402

DATA = ROOT / 'artifacts/m3_0/saccades'


def breakdown():
    M.recorded_provenance(DATA)
    by_kind, airborne_s = defaultdict(list), 0.0
    for path in sorted(DATA.glob('seed*.npz')):
        z = np.load(path)
        rows, kinds, dt = z['rows'], z['kinds'], float(z['dt'])
        airborne, yaw, esc = rows[:, 0] > 0, rows[:, 2], rows[:, 3] > 0
        post = np.zeros(len(rows), bool)
        for i in np.flatnonzero(esc):
            post[i:i + int(round(M.POST_ESCAPE_S / dt)) + 1] = True
        airborne_s += float((airborne & ~post).sum()) * dt
        t, n = 0, len(rows)
        while t < n:
            if airborne[t] and abs(yaw[t]) >= M.SACCADE_THRESHOLD:
                start, sign = t, np.sign(yaw[t])
                while (t + 1 < n and airborne[t + 1] and abs(yaw[t + 1]) >= M.SACCADE_THRESHOLD
                       and np.sign(yaw[t + 1]) == sign):
                    t += 1
                ks = [str(k) for k in kinds[start:t + 1]]
                if not (any(k in ('ESCAPE', 'ALERT') for k in ks) or post[start]):
                    common = Counter(k for k in ks if k != 'NONE').most_common(1)
                    by_kind[common[0][0] if common else 'NONE'].append(
                        (abs(math.degrees(float(yaw[start:t + 1].sum()) * dt)), (t - start + 1) * dt))
            t += 1
    total = sum(len(v) for v in by_kind.values())
    print('usable airborne time %.0f s; %d spontaneous events, %.3f per s' % (airborne_s, total, total / airborne_s))
    for kind, events in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        amp = [e[0] for e in events]
        dur = [e[1] for e in events]
        print('  %-10s %4d events, %.3f per s; amplitude median %.0f deg (IQR %.0f-%.0f); duration median %.0f ms' % (
            kind, len(events), len(events) / airborne_s, np.median(amp), *np.percentile(amp, [25, 75]),
            1000 * np.median(dur)))


def pulse_geometry():
    """Half-sine yaw-rate pulse: w(t) = P sin(pi t / T), angle A = 2 P T / pi."""
    thr = math.degrees(M.SACCADE_THRESHOLD)
    print('half-sine pulse seen by the %.0f deg/s detector (continuous time; the 20 ms tick adds rounding):' % thr)
    for peak in (700.0, 1000.0, 1200.0, 1400.0, 1500.0):
        if peak <= thr:
            continue
        phase = math.asin(thr / peak)                       # where the rate crosses the threshold
        share_angle = math.cos(phase)
        share_time = 1.0 - 2.0 * phase / math.pi
        cells = []
        for angle in (45.0, 65.0, 90.0, 105.0):
            duration = math.pi * angle / (2.0 * peak)
            cells.append('%g deg: %.0f ms total, seen %.0f deg in %.0f ms' % (
                angle, 1000 * duration, share_angle * angle, 1000 * share_time * duration))
        print('  peak %4.0f deg/s: %s' % (peak, ' | '.join(cells)))


if __name__ == '__main__':
    breakdown()
    pulse_geometry()
