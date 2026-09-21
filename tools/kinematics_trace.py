"""Capture a full-precision deterministic ROOM trace for M1.8-B1 refactor comparison.

Every recorded number is stored as an exact float hex string, so a pre-B1 and post-B1
capture can be compared bit-for-bit and the first divergence located precisely. Every
random stream's final state is captured too, so a change in RNG call order is detected
even when it does not immediately move the fly.

    python tools/kinematics_trace.py --out artifacts/m1_8_b1/pre-b1-trace.json
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.session import Session, load_config

# Fields captured per tick. Order is part of the comparison contract.
FIELDS = ('x', 'y', 'vx', 'vy', 'heading', 'yaw_rate', 'applied_target_speed',
          'wander_turn', 'flight_time', 'dnp01_total', 'action_turn')


def _hex(value):
    return float(value).hex()


def _rng_states(world, session):
    """Final bit-generator states for every seeded stream the tick path touches."""
    states = {'world': world.rng.bit_generator.state,
              'spawn': world._spawn_rng.bit_generator.state,
              'flight': world.flight.rng.bit_generator.state}
    if session.ecology is not None:
        states['ecology'] = session.ecology.rng.bit_generator.state
    if world.lifecycle is not None:
        states['lifecycle'] = world.lifecycle.rng.bit_generator.state
    return json.loads(json.dumps(states, default=str))


def scenario(name, config, seed, ticks, chase_from=None, ecology=None, brain=None):
    session = Session(config, brain=brain, seed=seed, mode='evaluation', ecology_enabled=ecology)
    rows = []
    try:
        for tick in range(ticks):
            fly = session.world.fly
            chasing = chase_from is not None and tick >= chase_from
            pointer = (fly.x, fly.y) if chasing else (1920, 388.8)
            session.tick(pointer=pointer)
            world = session.world
            motor = session.fly_loop.last_motor
            row = {'x': fly.x, 'y': fly.y, 'vx': fly.vx, 'vy': fly.vy, 'heading': fly.heading,
                   'yaw_rate': world.yaw_rate, 'applied_target_speed': world.applied_target_speed,
                   'wander_turn': world._wander_turn, 'flight_time': world._flight_time,
                   'dnp01_total': 0.0 if motor is None else motor.dnp01_total,
                   'action_turn': session.fly_loop.last_action.turn}
            entry = [_hex(row[key]) for key in FIELDS]
            if world.lifecycle is not None:
                entry.append(world.lifecycle.mode + '/' + world.lifecycle.phase)
                entry.append(str(world.contact_surface_id))
            entry.append(session.policy_diagnostics.get('behavior_state', 'UNSPECIFIED'))
            entry.append(world.saccades.kind)
            if session.ecology is not None:
                entry.append(session.ecology.state)
            rows.append(entry)
        states = _rng_states(session.world, session)
    finally:
        session.close()
    payload = json.dumps(rows, sort_keys=True, separators=(',', ':'))
    return {'scenario': name, 'seed': seed, 'ticks': ticks, 'chase_from': chase_from,
            'ecology_enabled': ecology, 'fields': list(FIELDS),
            'rows': rows, 'rng_final_states': states,
            'trace_sha256': hashlib.sha256(payload.encode('ascii')).hexdigest()}, session.brain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts/m1_8_b1/trace.json')
    args = parser.parse_args()
    room = load_config(ROOT/'game_room_config.json')
    play = load_config(ROOT/'game_play_config.json')
    lab = load_config(ROOT/'game_config.json')
    plan = [
        # ROOM with the full lifecycle: land, perch, feed, voluntary takeoff.
        ('room_quiet', room, 255, 1200, None, None),
        # ROOM perched fly launched by a real approaching paddle.
        ('room_perched_threat', room, 255, 340, 240, None),
        # ROOM landing approach interrupted by a real neural escape.
        ('room_approach_threat', room, 255, 120, 10, None),
        # A different seed, for more ordinary airborne ecological flight.
        ('room_airborne_seed101', room, 101, 900, None, None),
        # Ecology disabled: the baseline-speed airborne path with no command.
        ('room_no_ecology', room, 255, 600, None, False),
        # Frozen presets, which must have no lifecycle and no ecology changes.
        ('game_preset', play, 7, 500, 200, None),
        ('lab_preset', lab, 7, 400, 150, None),
    ]
    brain = None
    scenarios = []
    for name, config, seed, ticks, chase, ecology in plan:
        result, brain = scenario(name, config, seed, ticks, chase, ecology, brain)
        scenarios.append(result)
        print(name, 'ticks', result['ticks'], 'sha256', result['trace_sha256'][:16], flush=True)
    combined = hashlib.sha256(''.join(s['trace_sha256'] for s in scenarios).encode('ascii')).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'scenarios': scenarios, 'combined_sha256': combined},
                                   indent=1)+'\n', encoding='utf-8')
    print('combined', combined)
    print('written', args.out)


if __name__ == '__main__':
    main()
