"""Audit the ROOM max_speed ceiling and quantify the M1.8-B2b saturation problem.

Documentation only: this tool changes nothing. It records which code paths the cap
actually binds, and at what room_kinematic_scale each ecological speed context would
begin to truncate against the unchanged cap.

    python tools/max_speed_audit.py --report artifacts/m1_8_b2a/max-speed-audit.json
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

from game.action import Action
from game.ecology import EcologicalCommand
from game.session import load_config
from game.world import Fly, World

# R0 nominal body-length convention, with its documented sensitivity bracket.
MM_PER_BL = 2.5
BRACKET_MM = (3.0, 2.0)
# Context-matched references from the accepted R0 evidence lock, in m/s.
REFERENCES = {'E03 steady groundspeed': (0.15, 0.20),
              'E02 intersaccadic (two backgrounds)': (0.267, 0.381),
              'E06 landing approach at 10 cm': (0.37, 0.37),
              'E05 airspeed near plume': (0.55, 0.59)}


def empirical_paths(config):
    """Which runtime paths the cap actually binds, measured rather than asserted."""
    cap = config['fly']['max_speed']
    results = {}

    # 1. Ordinary airborne ecological locomotion.
    w = World(config, 101)
    w.ecological_command = EcologicalCommand('TRANSIT', 1e6, 0.0, 1.0)
    w.tick(.02, Action())
    results['ecological_target_capped'] = w.applied_target_speed == cap

    # 2. Neural escape impulse: applied before the executor, then clamped by it.
    w = World(config, 101)
    w.fly = Fly(w.width*.5, w.height*.5, cap*.9, 0.0, 0.0)
    w.tick(.02, Action(escape=True, forward=1.0, lateral=0.0, strength=1.0))
    speed = math.hypot(w.fly.vx, w.fly.vy)
    results['escape_speed_after_tick'] = speed
    results['escape_is_capped'] = speed <= cap + 1e-6

    # 3. Lifecycle voluntary launch target.
    launch_bl = config['lifecycle']['voluntary_launch_speed_bl_s']
    body = config['fly']['body_length_px']
    results['voluntary_launch_units'] = min(cap, launch_bl*body)
    results['voluntary_launch_capped'] = launch_bl*body > cap

    # 4. Lifecycle landing approach target.
    contact_bl = config['lifecycle']['contact_speed_bl_s']
    results['landing_contact_units'] = min(cap, contact_bl*body)
    results['landing_contact_capped'] = contact_bl*body > cap
    return results


def saturation(config):
    body, cap = config['fly']['body_length_px'], config['fly']['max_speed']
    cap_bl = cap/body
    rows = []
    for state, (low, high) in sorted(config['ecology']['speed_bl_s'].items()):
        rows.append({'context': state, 'envelope_bl_s': [low, high],
                     'scale_where_top_saturates': cap_bl/high if high else None,
                     'scale_where_whole_band_saturates': cap_bl/low if low else None})
    needed = {}
    for name, (low, high) in REFERENCES.items():
        needed[name] = {'m_s': [low, high],
                        'bl_s_at_2p5mm': [low*1000/MM_PER_BL, high*1000/MM_PER_BL],
                        'bl_s_bracket_3mm_2mm': [low*1000/BRACKET_MM[0], high*1000/BRACKET_MM[1]],
                        'exceeds_cap': high*1000/MM_PER_BL > cap_bl}
    return {'cap_units_per_s': cap, 'cap_bl_s': cap_bl,
            'body_length_units': body, 'per_context': rows, 'references': needed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path,
                        default=ROOT/'artifacts/m1_8_b2a/max-speed-audit.json')
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    result = {
        'label': 'documentation audit; no parameter was changed',
        'parameter': 'fly.max_speed',
        'value_units_per_s': config['fly']['max_speed'],
        'r0_classification': 'C - physical speed cap, not a species flight maximum',
        'r0_source': 'game/M1_8_EVIDENCE.md parameter inventory',
        'shared_by_presets': {name: load_config(ROOT/name)['fly']['max_speed']
                              for name in ('game_config.json', 'game_play_config.json',
                                           'game_room_config.json')},
        'room_kinematic_scale': config['kinematics']['room_kinematic_scale'],
        'binding_paths': empirical_paths(config),
        'saturation': saturation(config),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
