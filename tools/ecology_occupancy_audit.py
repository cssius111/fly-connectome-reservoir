"""M1.8-B2b-iii design audit: where no-player ROOM flight time actually goes.

Diagnostic only. This tool changes nothing and must never be used to tune toward hit
rate, survival, escape rate or player difficulty: no player acts in any run here.

For each run it reports the ecological state occupancy (alive ticks), every state
transition, completed episode durations, and, at every entry into ALERT, whether any
looming expansion or LC4/LPLC2 drive occurred in the preceding 120 ms.

    python tools/ecology_occupancy_audit.py --report artifacts/m1_8_b2b_iii/occupancy.json
"""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.session import Session, load_config

DT = 0.02
LOOKBACK_TICKS = 6     # the ALERT entry tick and the 5 before it (120 ms)
PARKED_POINTER = (1920, 388.8)   # same parked pointer as tools/explore_speed_diagnostics.py


def closed_loop(config, seed, ticks, brain=None):
    """A long ROOM run with no player: the pointer is parked far from the fly."""
    session = Session(config, brain=brain, seed=seed, mode='evaluation')
    occupancy, transitions, episodes = {}, {}, {}
    window = deque(maxlen=LOOKBACK_TICKS)
    alert_entries = []
    previous, started = None, 0
    try:
        for tick in range(ticks):
            session.tick(pointer=PARKED_POINTER)
            if not session.world.fly.alive:
                continue
            retina = session.last_retina
            drive = session.fly_loop.encoder.last_drive
            window.append((float(retina.theta_dot), sum(abs(float(v)) for v in drive.values())))
            state = session.ecology.state
            occupancy[state] = occupancy.get(state, 0) + 1
            if state != previous:
                if previous is not None:
                    key = previous + '->' + state
                    transitions[key] = transitions.get(key, 0) + 1
                    episodes.setdefault(previous, []).append((tick-started)*DT)
                if state == 'ALERT':
                    alert_entries.append({'tick': tick,
                                          'max_theta_dot': max(t for t, _ in window),
                                          'drive_sum': sum(d for _, d in window)})
                previous, started = state, tick
        alive = sum(occupancy.values())
        minutes = alive*DT/60
        no_expansion = sum(1 for e in alert_entries if e['max_theta_dot'] <= 0.0)
        no_drive = sum(1 for e in alert_entries if e['drive_sum'] == 0.0)
        return {'seed': seed, 'ticks': ticks, 'alive_ticks': alive,
                'ecology_state_occupancy': {k: v/alive for k, v in sorted(occupancy.items())},
                'transitions': dict(sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0]))),
                'completed_episodes': {k: {'n': len(v), 'mean_seconds': sum(v)/len(v)}
                                       for k, v in sorted(episodes.items())},
                'alert_entries': len(alert_entries),
                'alert_entries_per_min': len(alert_entries)/minutes if minutes else None,
                'alert_entries_without_expansion_in_window': no_expansion,
                'alert_entries_without_lc4_lplc2_drive_in_window': no_drive}, session.brain
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path,
                        default=ROOT/'artifacts/m1_8_b2b_iii/occupancy.json')
    parser.add_argument('--ticks', type=int, default=9000)   # 180 simulated seconds
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    runs, brain = [], None
    for seed in (101, 255, 4242):    # the B2b-ii closed-loop diagnostic seeds
        run, brain = closed_loop(config, seed, args.ticks, brain)
        runs.append(run)
        print('seed', seed, 'alert entries/min', round(run['alert_entries_per_min'], 2),
              'occupancy', {k: round(v, 4) for k, v in run['ecology_state_occupancy'].items()},
              flush=True)
    result = {'label': 'simulator diagnostics; no player acts and no difficulty metric is used',
              'config_version': config['config_version'], 'lookback_ticks': LOOKBACK_TICKS,
              'runs': runs}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print('written', args.report)


if __name__ == '__main__':
    main()
