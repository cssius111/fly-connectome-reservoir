"""M1.8-N2b: diagnose pre-click escapes in the closed-loop system-test scenarios.

Diagnosis only; nothing is injected and no runtime file is changed. Each scenario is run
through the real chain with the working-tree (N2b) decoder, and for every tick before the
click the retina, encoder drive (LPLC2 = loom, LC4 = threat), DNp01, rolling window and
decoder state are recorded. For the first pre-click escape, the tick itself and the ten
preceding neural samples are reported, together with zero-loom checks over the hold.

    python tools/n2b_preclick_diagnosis.py --out artifacts/m1_8_n2b/preclick_diagnosis.json
"""
from __future__ import annotations

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

from game.session import build_policy, load_config  # noqa: E402
from tools.n2_closed_loop import PARKED, Run, settle_to_perch  # noqa: E402

LOW = 1.45


def sample(run, tick, fixture_tick, click_tick):
    s = run.s
    r, d, m = s.last_retina, s.encoder.last_drive or {}, s.fly_loop.last_motor
    sw = s.world.swatter
    c = s.policy.criterion_diagnostics()
    total = m.dnp01_total
    window = ''.join('H' if v else 'L' for v in s.policy._window)
    return {
        'tick': tick,
        'time_from_fixture_s': None if fixture_tick is None else round((tick - fixture_tick) * .02, 3),
        'time_to_click_s': round((click_tick - tick) * .02, 3),
        'lifecycle': s.world.lifecycle.mode if s.world.lifecycle else None,
        'swatter_xy': [sw.x, sw.y], 'swatter_v': [sw.vx, sw.vy],
        'swatter_speed': math.hypot(sw.vx, sw.vy), 'swatter_phase': sw.phase.value,
        'fly_to_swatter': math.hypot(sw.x - s.world.fly.x, sw.y - s.world.fly.y),
        'theta': r.theta, 'theta_dot': r.theta_dot,
        'LC4_L': d.get('threatL', 0.0), 'LC4_R': d.get('threatR', 0.0),
        'LPLC2_L': d.get('loomL', 0.0), 'LPLC2_R': d.get('loomR', 0.0),
        'dnp01_L': m.dnp01_left, 'dnp01_R': m.dnp01_right, 'dnp01_total': total,
        'window': window, 'qualifying': c['escape_window_qualifying'],
        'fast_state': total >= s.policy.fast_threshold,
        'sustained_state': total >= LOW and (c['escape_window_qualifying'] or 0) >= 3,
        'escape': bool(s.fly_loop.last_action.escape),
        'channel': c['escape_trigger_channel'] if s.fly_loop.last_action.escape else None,
        'refractory_ticks': s.policy.refractory_remaining}


def perched_case(policy, brain, seed, offset, hold, projector_reset):
    run = Run(ROOM, policy, seed, brain)
    rows = []
    try:
        settle_to_perch(run)
        fixture = run.tick
        fly, sw = run.fly, run.s.world.swatter
        target = (fly.x + offset[0], fly.y + offset[1])
        sw.x, sw.y = target
        sw.target_x, sw.target_y = target
        sw.vx = sw.vy = 0.0
        if projector_reset in ('projector', 'settled'):
            run.s.projector.reset()
        if projector_reset == 'settled':
            # The frozen swatter's own reset: placement is not an observed pointer movement.
            run.s.world.physical_swatter.reset()
        click = fixture + hold
        for _ in range(hold):
            run.step(target)
            rows.append(sample(run, run.tick - 1, fixture, click))
        perched = run.s.world.lifecycle.stationary
    finally:
        run.close()
    return rows, {'fixture_tick': fixture, 'click_tick': click, 'perched_at_click': perched}


def airborne_case(policy, brain, seed, offset, lead=90):
    run = Run(ROOM, policy, seed, brain, ecology=False)
    rows = []
    try:
        for _ in range(40):
            run.step(PARKED)
        start = run.tick
        click = start + lead
        for _ in range(lead):
            run.step((run.fly.x + offset[0], run.fly.y + offset[1]))
            rows.append(sample(run, run.tick - 1, start, click))
    finally:
        run.close()
    return rows, {'tracking_start_tick': start, 'click_tick': click}


def summarise(rows, meta, settle_from=None):
    first = next((i for i, r in enumerate(rows) if r['escape']), None)
    out = {**meta, 'pre_click_escapes': sum(r['escape'] for r in rows)}
    if first is not None:
        out['first_escape'] = rows[first]
        out['previous_10'] = [{k: r[k] for k in ('tick', 'theta_dot', 'LC4_L', 'LC4_R', 'LPLC2_L',
                                                 'LPLC2_R', 'dnp01_total', 'window', 'qualifying')}
                              for r in rows[max(0, first - 10):first]]
        drive_ticks = [r['tick'] for r in rows[:first]
                       if r['LC4_L'] + r['LC4_R'] + r['LPLC2_L'] + r['LPLC2_R'] > 0]
        out['last_nonzero_drive_before_escape_tick'] = drive_ticks[-1] if drive_ticks else None
    if settle_from is not None:
        hold = rows[settle_from:]
        out['hold_zero_loom_check_after_%d_samples' % settle_from] = {
            'max_swatter_speed': max(r['swatter_speed'] for r in hold),
            'max_abs_theta_dot': max(abs(r['theta_dot']) for r in hold),
            'max_encoder_drive': max(r['LC4_L'] + r['LC4_R'] + r['LPLC2_L'] + r['LPLC2_R'] for r in hold),
            'max_dnp01': max(r['dnp01_total'] for r in hold)}
    out['first_samples'] = [{k: r[k] for k in ('tick', 'theta', 'theta_dot', 'LC4_L', 'LC4_R',
                                               'LPLC2_L', 'LPLC2_R', 'dnp01_total')}
                            for r in rows[:5]]
    return out


ROOM = load_config(ROOT / 'game_room_config.json')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=ROOT / 'artifacts/m1_8_n2b/preclick_diagnosis.json')
    args = p.parse_args()
    make = lambda: build_policy(ROOM, ROOT)[0]
    from game.session import Session
    probe = Session(ROOM, policy=make(), seed=1, mode='evaluation')
    brain = probe.brain
    probe.close()
    out = {}
    for label, reset in (('A_seed255_offset0_original_fixture', None),
                         ('A_seed255_offset0_projector_reset_only', 'projector'),
                         ('A_seed255_offset0_settled_fixture', 'settled')):
        rows, meta = perched_case(make(), brain, 255, (0.0, 0.0), 100, reset)
        out[label] = summarise(rows, meta, settle_from=5)
    rows, meta = airborne_case(make(), brain, 11, (20.0, 10.0))
    out['B_seed11_offset_20_10_airborne_tracking'] = summarise(rows, meta)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    for k, v in out.items():
        print('==', k, {kk: v[kk] for kk in v if kk not in ('previous_10', 'first_escape', 'first_samples')})
        if 'first_escape' in v:
            print('   first escape:', v['first_escape'])
            for r in v['previous_10']:
                print('     ', r)
        print('   first samples:', v['first_samples'])
    print('written', args.out)


if __name__ == '__main__':
    main()
