"""M1.8-N0 secondary diagnostic: one continuous no-loom brain trajectory.

The accepted fixed-fly-v2 arm divides its exposure across reset trials. This arm records
a single uninterrupted trajectory instead, so the two can be compared for any effect of
reset boundaries on the rare tail. It is a **secondary** diagnostic and does not replace
the accepted protocol.

Research only: nothing is modified, and no calibration path is written.

    python tools/no_loom_continuous_arm.py --ticks 30000
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402

from game.session import Session, load_config  # noqa: E402
from tools.calibrate_escape import RecordingPolicy  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_no_loom_calibration'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT/'game_room_config.json')
    p.add_argument('--ticks', type=int, default=30000)
    p.add_argument('--seed', type=int, default=4000)
    args = p.parse_args()

    config = load_config(args.config)
    dt = float(config['sim']['tick_seconds'])
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    session.reset(args.seed)
    fly = session.world.fly
    # Same geometry family as the accepted null arm; settle exactly as _trial does.
    pointer = (fly.x + 120.0, fly.y + 60.0)
    settle = max(40, round(config['swatter'].get('physical', {})
                           .get('calibration_settle_seconds', 0.8)/dt))
    for _ in range(settle):
        session.tick(pointer=pointer, strike=False)
    sw = session.world.swatter
    if math.hypot(sw.vx, sw.vy) > 0.1:
        raise RuntimeError('paddle did not settle')
    base = len(policy.history)
    started = time.perf_counter()
    max_drive = 0.0
    max_theta_dot = 0.0
    for i in range(args.ticks):
        session.tick(pointer=pointer, strike=False)
        drive = session.encoder.last_drive or {}
        if drive:
            max_drive = max(max_drive, max(abs(v) for v in drive.values()))
        if session.last_retina is not None:
            max_theta_dot = max(max_theta_dot, abs(session.last_retina.theta_dot))
        if (i+1) % 5000 == 0:
            print('  %d/%d ticks  %.0fs' % (i+1, args.ticks, time.perf_counter()-started),
                  flush=True)
    trace = np.array([m.dnp01_total for m in policy.history[base:]], dtype=np.float64)
    session.close()

    decay = float(np.exp(-dt/float(config['brain']['trace_tau_seconds'])))
    prev, spikes = 0.0, []
    for i, v in enumerate(trace):
        spikes.append(v - prev*decay)
        prev = v
    spikes = np.rint(np.asarray(spikes[1:]))          # drop the first, no prior sample
    counts = {int(k): int(c) for k, c in zip(*np.unique(spikes.astype(int),
                                                        return_counts=True))}
    minutes = trace.size*dt/60.0
    result = {
        'label': 'secondary continuous no-loom diagnostic; accepted protocol not replaced',
        'ticks': int(trace.size), 'minutes': minutes, 'seed': args.seed,
        'continuous': True, 'resets_during_recording': 0,
        'settle_ticks': settle,
        'max_abs_theta_dot': max_theta_dot, 'max_abs_encoder_drive': max_drive,
        'mean': float(trace.mean()), 'sd': float(trace.std(ddof=1)),
        'p95': float(np.percentile(trace, 95)), 'p99': float(np.percentile(trace, 99)),
        'p99_9': float(np.percentile(trace, 99.9)), 'max': float(trace.max()),
        'spike_tick_counts': counts,
        'spikes_total': int(spikes.sum()), 'spikes_per_second': float(spikes.sum()/(trace.size*dt)),
        'elapsed_seconds': time.perf_counter()-started,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT/'continuous.npz', trace=trace)
    (OUT/'continuous.json').write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'spike_tick_counts'}, indent=1))
    print('spike tick counts:', counts)


if __name__ == '__main__':
    main()
