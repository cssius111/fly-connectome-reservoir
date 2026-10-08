"""Offline escape/cruise compatibility analysis for M1.8-B2b-R0.

Analysis only. This tool changes no configuration, no runtime behavior and no
parameter. It evaluates the *accepted* escape mechanics at hypothetical pre-escape
speeds that the current ecological cap does not currently permit, in order to separate
the neural escape semantics from the legacy engineering ceiling.

The no-cap counterfactual is computed analytically rather than by mutating max_speed,
and the analytic model is validated against the real World on every case where the cap
does not bind.

    python tools/escape_cruise_study.py --report artifacts/m1_8_b2b_r0/escape-cruise.json
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
from game.session import load_config
from game.world import Fly, World

DT = 0.02
PRE_SPEEDS_BL_S = (10.0, 20.0, 30.0, 40.0, 60.0, 80.0)
STRENGTHS = (0.25, 0.5, 1.0)
# `forward` is the policy's fixed escape_forward_bias; `lateral` is the DNp01 asymmetry.
DIRECTIONS = {'forward_dominant': (0.0, 0.35),
              'combined': (0.5, 0.35),
              'lateral_dominant': (1.0, 0.35)}


def analytic_tick(pre_speed, heading, lateral, forward, strength, body, impulse,
                  damping, baseline, cap):
    """Reproduce the accepted per-tick escape arithmetic, cap optional.

    Sideslip rescales the velocity to the same magnitude, so it does not alter speed.
    """
    vx, vy = pre_speed*math.cos(heading), pre_speed*math.sin(heading)
    hx, hy = math.cos(heading), math.sin(heading)
    rx, ry = -hy, hx
    ix, iy = rx*lateral + hx*forward, ry*lateral + hy*forward
    mag = math.hypot(ix, iy)
    if mag > 0.0:
        vx += impulse*strength*ix/mag
        vy += impulse*strength*iy/mag
    raw = math.hypot(vx, vy)
    ax = damping*(baseline*math.cos(heading) - vx)
    ay = damping*(baseline*math.sin(heading) - vy)
    vx += ax*DT
    vy += ay*DT
    damped = math.hypot(vx, vy)
    return {'raw_units': raw, 'after_damping_units': damped,
            'after_cap_units': min(damped, cap) if cap is not None else damped}


def run_case(config, pre_bl, name, lateral, forward, strength):
    body = config['fly']['body_length_px']
    cap = config['fly']['max_speed']
    impulse = config['fly']['escape_impulse']
    damping = config['fly']['damping_per_second']
    baseline = config['fly']['baseline_speed']
    pre_units = pre_bl*body

    # Ground truth: the real accepted code path, one tick, mid-arena.
    world = World(config, 4242)
    world.fly = Fly(world.width*0.5, world.height*0.5, pre_units, 0.0, 0.0)
    heading_before = world.fly.heading
    world.tick(DT, Action(escape=True, lateral=lateral, forward=forward,
                          strength=strength, turn=0.0, saccade=0.0))
    post_units = math.hypot(world.fly.vx, world.fly.vy)
    heading_after = world.fly.heading
    contact = bool(world.wall_contact or world.object_contact)

    model = analytic_tick(pre_units, heading_before, lateral, forward, strength,
                          body, impulse, damping, baseline, cap)
    no_cap = analytic_tick(pre_units, heading_before, lateral, forward, strength,
                           body, impulse, damping, baseline, None)
    turn = (heading_after - heading_before + math.pi) % (2*math.pi) - math.pi
    return {
        'pre_speed_bl_s': pre_bl,
        'direction': name, 'lateral': lateral, 'forward': forward, 'strength': strength,
        'impulse_delta_v_bl_s': impulse*strength/body,
        'raw_post_impulse_bl_s': model['raw_units']/body,
        'post_escape_bl_s_current': post_units/body,
        'post_escape_bl_s_uncapped': no_cap['after_cap_units']/body,
        'delta_speed_bl_s': (post_units-pre_units)/body,
        'percent_speed_change': 100.0*(post_units-pre_units)/pre_units if pre_units else None,
        'heading_change_deg': math.degrees(turn),
        'cap_binds': model['after_damping_units'] > cap,
        'cap_reduces_speed': post_units < pre_units - 1e-9,
        'model_matches_runtime': abs(model['after_cap_units'] - post_units) < 1e-6,
        'world_contact_during_tick': contact,
    }


def run_bout(config, pre_bl, lateral, forward, strength, ticks=30):
    """Multi-tick escape bout under current semantics.

    The policy emits the impulse on one tick only, plus a saccade request equal to
    asymmetry*strength. Direction change is therefore delivered by the saccade actuator,
    a separate channel from the translational impulse, and plays out over several ticks.
    """
    body = config['fly']['body_length_px']
    world = World(config, 4242)
    world.fly = Fly(world.width*0.5, world.height*0.5, pre_bl*body, 0.0, 0.0)
    x0, y0, h0 = world.fly.x, world.fly.y, world.fly.heading
    speeds, peak = [], 0.0
    for tick in range(ticks):
        if tick == 0:
            action = Action(escape=True, lateral=lateral, forward=forward,
                            strength=strength, turn=0.0, saccade=lateral*strength)
        else:
            action = Action()
        world.tick(DT, action)
        speed = math.hypot(world.fly.vx, world.fly.vy)/body
        speeds.append(speed)
        peak = max(peak, speed)
    dx, dy = world.fly.x-x0, world.fly.y-y0
    forward_disp = (dx*math.cos(h0) + dy*math.sin(h0))/body
    lateral_disp = (-dx*math.sin(h0) + dy*math.cos(h0))/body
    turn = (world.fly.heading - h0 + math.pi) % (2*math.pi) - math.pi
    return {'pre_speed_bl_s': pre_bl, 'lateral': lateral, 'strength': strength,
            'ticks': ticks, 'peak_speed_bl_s': peak,
            'final_speed_bl_s': speeds[-1],
            'total_heading_change_deg': math.degrees(turn),
            'forward_displacement_bl': forward_disp,
            'lateral_displacement_bl': lateral_disp,
            'peak_is_below_pre_speed': peak < pre_bl - 1e-9,
            'contact': bool(world.wall_contact or world.object_contact)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path,
                        default=ROOT/'artifacts/m1_8_b2b_r0/escape-cruise.json')
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    body, cap = config['fly']['body_length_px'], config['fly']['max_speed']
    rows = []
    for pre in PRE_SPEEDS_BL_S:
        for name, (lateral, forward) in DIRECTIONS.items():
            for strength in STRENGTHS:
                rows.append(run_case(config, pre, name, lateral, forward, strength))
    bouts = [run_bout(config, pre, lateral, 0.35, strength)
             for pre in PRE_SPEEDS_BL_S
             for lateral, strength in ((1.0, 1.0), (0.0, 1.0), (1.0, 0.5))]
    mismatches = [r for r in rows if not r['model_matches_runtime']]
    contacts = [r for r in rows if r['world_contact_during_tick']]
    reducing = [r for r in rows if r['cap_reduces_speed']]
    result = {
        'label': 'offline analysis of the accepted escape mechanics; no runtime or config change',
        'constants': {'escape_impulse_units_s': config['fly']['escape_impulse'],
                      'escape_impulse_bl_s': config['fly']['escape_impulse']/body,
                      'escape_forward_bias': config['fly']['escape_forward_bias'],
                      'max_speed_units_s': cap, 'max_speed_bl_s': cap/body,
                      'baseline_speed_bl_s': config['fly']['baseline_speed']/body,
                      'damping_per_second': config['fly']['damping_per_second'],
                      'body_length_units': body, 'tick_seconds': DT},
        'validation': {'cases': len(rows), 'analytic_model_mismatches': len(mismatches),
                       'cases_with_world_contact': len(contacts)},
        'cases_where_escape_reduces_speed': len(reducing),
        'lowest_pre_speed_bl_s_that_is_reduced': min((r['pre_speed_bl_s'] for r in reducing),
                                                     default=None),
        'rows': rows,
        'bouts': bouts,
        'bout_note': ('Direction change is delivered by the saccade actuator, a separate '
                      'channel from the translational impulse. The no-cap counterfactual '
                      'for displacement was not computed, because heading is driven by the '
                      'seeded saccade actuator and is not reproducible analytically.'),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    header = ('pre BL/s', 'dir', 'str', 'dV BL/s', 'raw', 'post(now)', 'post(uncapped)',
              '%chg', 'dHdg', 'cap binds', 'slower')
    print('%-9s %-17s %-5s %-8s %-8s %-10s %-15s %-8s %-7s %-10s %s' % header)
    for r in rows:
        print('%-9.0f %-17s %-5.2f %-8.1f %-8.1f %-10.2f %-15.2f %-8.1f %-7.2f %-10s %s' % (
            r['pre_speed_bl_s'], r['direction'], r['strength'], r['impulse_delta_v_bl_s'],
            r['raw_post_impulse_bl_s'], r['post_escape_bl_s_current'],
            r['post_escape_bl_s_uncapped'], r['percent_speed_change'],
            r['heading_change_deg'], r['cap_binds'], r['cap_reduces_speed']))
    print()
    bh = ('pre BL/s', 'lat', 'str', 'peak', 'final', 'dHdg deg', 'fwd BL', 'lat BL', 'peak<pre')
    print('%-9s %-5s %-5s %-8s %-8s %-10s %-9s %-9s %s' % bh)
    for b in bouts:
        print('%-9.0f %-5.1f %-5.2f %-8.2f %-8.2f %-10.2f %-9.2f %-9.2f %s' % (
            b['pre_speed_bl_s'], b['lateral'], b['strength'], b['peak_speed_bl_s'],
            b['final_speed_bl_s'], b['total_heading_change_deg'],
            b['forward_displacement_bl'], b['lateral_displacement_bl'],
            b['peak_is_below_pre_speed']))
    print('\nanalytic model mismatches:', len(mismatches), '| world contacts:', len(contacts))
    print('cases where entering ESCAPE reduces speed:', len(reducing), 'of', len(rows))


if __name__ == '__main__':
    main()
