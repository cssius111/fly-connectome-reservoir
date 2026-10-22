"""Diagnose the causal provenance of escape takeoffs in no-player ROOM runs.

Diagnosis only. This tool changes no runtime code, configuration or parameter. The
B2b-i comparison arm is produced by disabling the EXPLORE sampler in memory on an
otherwise identical session, which reproduces the committed B2b-i behaviour exactly
without touching the working tree.

    python tools/escape_provenance.py --report artifacts/m1_8_b2b_ii/escape-provenance.json
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.session import Session, load_config

DT = 0.02
PARKED_POINTER = (1920.0, 388.8)          # the swatter's own spawn position
BEFORE_TICKS, AFTER_TICKS = 50, 25        # 1.0 s before, 0.5 s after


def snapshot(session, tick):
    w = session.world
    f, sw = w.fly, w.swatter
    retina = session.last_retina
    drive = session.encoder.last_drive or {}
    motor = session.fly_loop.last_motor
    action = session.fly_loop.last_action
    diag = session.policy_diagnostics
    life = w.lifecycle
    return {
        'tick': tick, 'time_s': round((tick+1)*DT, 3),
        'lifecycle_mode': life.mode, 'lifecycle_phase': life.phase,
        'feeding': life.feeding, 'contact_surface_id': w.contact_surface_id,
        'ecology_state': session.ecology.state if session.ecology else None,
        'swatter_phase': sw.phase.value, 'strike_id': w.stats.strikes,
        'strikes': w.stats.strikes,
        'swatter_x': sw.x, 'swatter_y': sw.y, 'swatter_vx': sw.vx, 'swatter_vy': sw.vy,
        'swatter_speed': math.hypot(sw.vx, sw.vy), 'swatter_height': sw.height,
        'fly_x': f.x, 'fly_y': f.y, 'fly_vx': f.vx, 'fly_vy': f.vy,
        'fly_speed_bl_s': w.body_lengths_per_second,
        'fly_to_swatter_distance': math.hypot(sw.x-f.x, sw.y-f.y),
        'theta': 0.0 if retina is None else retina.theta,
        'theta_dot': 0.0 if retina is None else retina.theta_dot,
        'azimuth': 0.0 if retina is None else retina.azimuth,
        'loomL': drive.get('loomL', 0.0), 'loomR': drive.get('loomR', 0.0),
        'threatL': drive.get('threatL', 0.0), 'threatR': drive.get('threatR', 0.0),
        'dnp01_total': 0.0 if motor is None else motor.dnp01_total,
        'dnp01_left': 0.0 if motor is None else motor.dnp01_left,
        'dnp01_right': 0.0 if motor is None else motor.dnp01_right,
        'threshold': diag.get('escape_threshold'),
        'behavior_state': diag.get('behavior_state'),
        'action_escape': bool(action.escape), 'action_strength': float(action.strength),
        'refractory_remaining_ticks': session.fly_loop.policy.refractory_remaining,
        'events': [dict(e) for e in life.events],
    }


def run(config, seed, ticks, sampling, brain):
    session = Session(config, brain=brain, seed=seed, mode='evaluation')
    if not sampling:
        # Reproduce the committed B2b-i behaviour: sampler present but inert.
        session.world.kinematic_sampler.explore = None
    history, events = [], []
    try:
        for tick in range(ticks):
            session.tick(pointer=PARKED_POINTER)
            snap = snapshot(session, tick)
            history.append(snap)
            for event in snap['events']:
                events.append({'tick': tick, 'time_s': snap['time_s'], **event})
    finally:
        session.close()
    return history, events, session.brain


def windows(history, events, kind):
    out = []
    for event in events:
        if event['type'] != kind:
            continue
        centre = event['tick']
        lo, hi = max(0, centre-BEFORE_TICKS), min(len(history), centre+AFTER_TICKS+1)
        window = history[lo:hi]
        peak = max(window, key=lambda r: r['dnp01_total'])
        moving = [r for r in window if r['swatter_speed'] > 1e-9]
        out.append({
            'event': event,
            'window_ticks': [lo, hi-1],
            'swatter_ever_moved_in_window': bool(moving),
            'max_swatter_speed_in_window': max(r['swatter_speed'] for r in window),
            'strikes_in_window': sorted({r['strikes'] for r in window}),
            'swatter_phases_in_window': sorted({r['swatter_phase'] for r in window}),
            'min_distance_in_window': min(r['fly_to_swatter_distance'] for r in window),
            'max_theta_dot_in_window': max(r['theta_dot'] for r in window),
            'peak_dnp01': peak['dnp01_total'], 'peak_dnp01_tick': peak['tick'],
            'rows': window,
        })
    return out


def perched_hold(config, seed, settle_ticks, hold_ticks, brain):
    """Hold a naturally perched fly with a stationary swatter and no input."""
    session = Session(config, brain=brain, seed=seed, mode='evaluation')
    try:
        perched_at = None
        for tick in range(settle_ticks):
            session.tick(pointer=PARKED_POINTER)
            if session.world.lifecycle.stationary and perched_at is None:
                perched_at = tick
            if perched_at is not None and tick - perched_at > 5:
                break
        if not session.world.lifecycle.stationary:
            return {'perched': False, 'note': 'fly did not perch within the settle window'}
        pose = (session.world.fly.x, session.world.fly.y, session.world.fly.heading)
        sw = session.world.swatter
        swatter_pose = (sw.x, sw.y)
        stats = {'max_dnp01': 0.0, 'max_theta_dot': 0.0, 'max_theta': 0.0,
                 'escape_actions': 0, 'escape_takeoffs': 0, 'left_perch': False,
                 'events': [], 'max_swatter_speed': 0.0}
        for tick in range(hold_ticks):
            session.tick(pointer=PARKED_POINTER)
            w = session.world
            r = session.last_retina
            motor = session.fly_loop.last_motor
            stats['max_dnp01'] = max(stats['max_dnp01'], 0.0 if motor is None else motor.dnp01_total)
            if r is not None:
                stats['max_theta_dot'] = max(stats['max_theta_dot'], r.theta_dot)
                stats['max_theta'] = max(stats['max_theta'], r.theta)
            stats['max_swatter_speed'] = max(stats['max_swatter_speed'],
                                             math.hypot(w.swatter.vx, w.swatter.vy))
            if session.fly_loop.last_action.escape:
                stats['escape_actions'] += 1
            for e in w.lifecycle.events:
                stats['events'].append({'tick': tick, **e})
                if e['type'] == 'escape_takeoff':
                    stats['escape_takeoffs'] += 1
            if not w.lifecycle.stationary:
                stats['left_perch'] = True
                stats['left_perch_tick'] = tick
                break
        return {'perched': True, 'perched_at_tick': perched_at, 'hold_ticks': hold_ticks,
                'pose': pose, 'swatter_pose': swatter_pose, 'threshold': 1.45, **stats}
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path,
                        default=ROOT/'artifacts/m1_8_b2b_ii/escape-provenance.json')
    parser.add_argument('--ticks', type=int, default=9000)
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    brain = None
    runs = []
    for seed in (101, 255, 4242):
        for sampling in (True, False):
            history, events, brain = run(config, seed, args.ticks, sampling, brain)
            kinds = {}
            for e in events:
                kinds[e['type']] = kinds.get(e['type'], 0) + 1
            escapes = windows(history, events, 'escape_takeoff')
            runs.append({'seed': seed, 'stage': 'B2b-ii' if sampling else 'B2b-i',
                         'explore_sampling': sampling, 'ticks': args.ticks,
                         'event_counts': kinds,
                         'escape_takeoffs': len(escapes),
                         'strikes_total': history[-1]['strikes'],
                         'swatter_ever_moved': any(r['swatter_speed'] > 1e-9 for r in history),
                         'max_swatter_speed': max(r['swatter_speed'] for r in history),
                         'swatter_phases': sorted({r['swatter_phase'] for r in history}),
                         'windows': escapes})
            print('seed', seed, 'stage', runs[-1]['stage'], 'escape_takeoffs',
                  len(escapes), 'strikes', runs[-1]['strikes_total'],
                  'swatter moved', runs[-1]['swatter_ever_moved'], flush=True)
    hold, _ = perched_hold(config, 255, 400, 6000, brain), None
    print('perched hold:', {k: v for k, v in hold.items() if k != 'events'}, flush=True)
    result = {'label': 'diagnosis only; no runtime, configuration or parameter changed',
              'pointer': list(PARKED_POINTER),
              'pointer_note': ('The swatter spawns at (width*0.5, height*0.18) = this exact '
                               'point, so parking the pointer here means the paddle never '
                               'receives a movement command.'),
              'window_ticks_before_after': [BEFORE_TICKS, AFTER_TICKS],
              'runs': runs, 'perched_hold': hold}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print('written', args.report)


if __name__ == '__main__':
    main()
