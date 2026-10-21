"""M1.8-B2c: evaluation metrics for ROOM flight kinematics and the activity budget.

Diagnostic only. This tool changes nothing and must never be used to tune toward hit
rate, survival, escape rate or player difficulty: no player acts in any run, and escapes
are counted only as a safety report. It fixes, before any later M1.8-B stage changes
behaviour (game/M1_8_B_PLAN.md sections 10 and 14), what is measured:

* occupancy of ecological states and lifecycle modes (alive ticks), and the share of each
  state among the ticks on which the ecology drives locomotion;
* speed by ecological state, on ticks where the ecology drives locomotion;
* acceleration and deceleration by state, and how long the speed takes to settle within
  0.5 BL/s of the applied target after each ecological episode starts;
* turns: accepted actuator requests by kind, their amplitudes, and the intervals between
  spontaneous turns; the drift turn between pulses;
* ecological episodes by state (complete and censored) and every state transition;
* odor: detection share, encounter rate, heading relative to upwind while tracking, food
  and perch touchdowns;
* the M1.8-A lifecycle metrics (airborne, perched and feeding fractions; flight and perch
  bouts, complete and censored);
* space: visited share of a 10 BL grid and time near a wall;
* safety: policy escape onsets per alive minute.

Each run is 180 s with no player and the pointer parked, as in the occupancy audit.

    NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --lane 0 --lanes 3 --out DIR
    python tools/kinematics_sanity.py summary --out DIR
    NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --commit 6b43c0f --out DIR
    python tools/kinematics_sanity.py compare --before DIR_A --out DIR_B --stage-states ODOR_SEARCH
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.lifecycle import LifecycleMetrics  # noqa: E402
from game.session import Session, load_config  # noqa: E402

DT = 0.02
TICKS = 9000                      # 180 simulated seconds
SEEDS = (101, 255, 4242, 7, 1729, 31337)
PARKED_POINTER = (1920, 388.8)    # same parked pointer as the occupancy audit
SETTLE_BL_S = 0.5                 # settling band around the applied target
GRID_CELL_UNITS = 240.0           # 10 BL
UPWIND_DEGREES = 45.0
SPONTANEOUS = ('CORRECTION', 'SACCADE')


def quantiles(values, qs=(10, 50, 90)):
    values = sorted(values)
    if not values:
        return {'n': 0}
    out = {'n': len(values), 'mean': sum(values)/len(values)}
    if len(values) > 1:
        mean = out['mean']
        out['sd'] = math.sqrt(sum((v-mean)**2 for v in values)/(len(values)-1))
    for q in qs:
        out['p%d' % q] = values[min(len(values)-1, int(round(q/100*(len(values)-1))))]
    out['max'] = values[-1]
    return out


def wrap(angle):
    return (angle + math.pi) % (2*math.pi) - math.pi


def measure(config, seed, ticks=TICKS, brain=None):
    """One no-player run; returns raw samples and counts for pooling."""
    session = Session(config, brain=brain, seed=seed, mode='evaluation')
    world = session.world
    body = world.body_length
    turns, actions = [], []
    request = world.saccades.request

    def logged_request(kind, angle, peak_rate):
        accepted = request(kind, angle, peak_rate)
        if accepted:
            turns.append((session.ticks, kind, abs(world.saccades.angle)))
        return accepted

    world.saccades.request = logged_request
    step = session.fly_loop.step

    def logged_step(retina, motion):
        action = step(retina, motion)
        actions.append(bool(action.escape))
        return action

    session.fly_loop.step = logged_step
    lifecycle = LifecycleMetrics()
    samples = {'speed': defaultdict(list), 'accel': defaultdict(list), 'decel': defaultdict(list),
               'settle': defaultdict(list), 'unsettled': Counter(), 'episodes': defaultdict(list),
               'censored': Counter(), 'drift': []}
    counts = Counter()
    transitions = Counter()
    occupancy, lifecycle_modes, driving = Counter(), Counter(), Counter()
    cells = set()
    previous_state = previous_speed = None
    episode_start = episode_target = None
    settled = True
    had_odor = False
    first_food = None
    try:
        for tick in range(ticks):
            actions_before = len(actions)
            session.tick(pointer=PARKED_POINTER)
            fly = world.fly
            if not fly.alive:
                if previous_state is not None:
                    samples['censored'][previous_state] += 1
                break
            life = world.lifecycle
            lifecycle.capture(life, True, DT)
            counts['alive'] += 1
            if len(actions) > actions_before and actions[-1] and (len(actions) < 2 or not actions[-2]):
                counts['escape_onsets'] += 1
            lifecycle_modes[life.mode] += 1
            for event in life.events:
                if event['type'] == 'touchdown':
                    surface = world.contact_surface_id
                    counts['touchdown_food' if surface == 'surface-0' else 'touchdown_other'] += 1
                    if surface == 'surface-0' and first_food is None:
                        first_food = tick*DT
            eco = session.ecology
            state = eco.state
            occupancy[state] += 1
            airborne = not life.stationary
            ecological = world.kinematic_profile.context.startswith('ecology_')
            if ecological and airborne:
                driving[state] += 1
            speed = math.hypot(fly.vx, fly.vy)/body
            if airborne:
                counts['airborne'] += 1
                cells.add((int(fly.x // GRID_CELL_UNITS), int(fly.y // GRID_CELL_UNITS)))
                counts['near_wall'] += int(world.flight.near_wall)
            # Ecological episodes, complete and censored.
            if state != previous_state:
                if previous_state is not None:
                    transitions[previous_state + '->' + state] += 1
                    samples['episodes'][previous_state].append((tick - episode_start)*DT)
                    if not settled and episode_target is not None:
                        samples['unsettled'][previous_state] += 1
                episode_start, episode_target, settled = tick, None, False
            if ecological and airborne:
                target = world.applied_target_speed/body
                samples['speed'][state].append(speed)
                if previous_speed is not None and state == previous_state:
                    rate = (speed - previous_speed)/DT
                    (samples['accel'] if rate >= 0 else samples['decel'])[state].append(abs(rate))
                if episode_target is None:
                    episode_target = target
                if not settled and abs(speed - target) <= SETTLE_BL_S:
                    samples['settle'][state].append((tick - episode_start)*DT)
                    settled = True
                if not world.saccades.active:
                    samples['drift'].append(world.yaw_rate)
            previous_speed = speed if (ecological and airborne) else None
            # Odor.
            if eco.has_odor:
                counts['odor_detected'] += 1
                if not had_odor:
                    counts['odor_encounters'] += 1
            had_odor = eco.has_odor
            if state == 'ODOR_TRACK' and ecological and airborne:
                wx, wy = world.room.wind(world.time_seconds)
                upwind = math.atan2(-wy, -wx)
                counts['odor_track_airborne'] += 1
                counts['odor_track_upwind'] += int(abs(wrap(fly.heading - upwind)) <= math.radians(UPWIND_DEGREES))
            previous_state = state
        else:
            samples['censored'][previous_state] += 1
    finally:
        session.close()
    alive_minutes = counts['alive']*DT/60
    airborne_minutes = counts['airborne']*DT/60
    by_kind = defaultdict(list)
    for t, kind, angle in turns:
        by_kind[kind].append(math.degrees(angle))
    spontaneous = [t for t, kind, _ in turns if kind in SPONTANEOUS]
    intervals = [(b - a)*DT for a, b in zip(spontaneous, spontaneous[1:])]
    grid = (math.ceil(world.width/GRID_CELL_UNITS), math.ceil(world.height/GRID_CELL_UNITS))
    lifecycle.end_episode()
    report = lifecycle.report()
    return {
        'seed': seed, 'config_version': config['config_version'], 'ticks_run': counts['alive'],
        'alive_minutes': alive_minutes, 'airborne_minutes': airborne_minutes,
        'occupancy': {k: v/counts['alive'] for k, v in sorted(occupancy.items())},
        'ecology_driving_ticks': dict(sorted(driving.items())),
        'lifecycle_modes': {k: v/counts['alive'] for k, v in sorted(lifecycle_modes.items())},
        'transitions': dict(sorted(transitions.items())),
        'raw': {'speed': samples['speed'], 'accel': samples['accel'], 'decel': samples['decel'],
                'settle': samples['settle'], 'episodes': samples['episodes'],
                'turn_degrees': by_kind, 'spontaneous_intervals': intervals, 'drift': samples['drift']},
        'unsettled_episodes': dict(samples['unsettled']), 'censored_episodes': dict(samples['censored']),
        'counts': dict(counts), 'cells_visited': len(cells), 'grid_cells': grid[0]*grid[1],
        'first_food_touchdown_seconds': first_food,
        'lifecycle': {k: report[k] for k in ('fractions', 'events', 'median_perch_seconds',
                                              'median_flight_bout_seconds', 'complete_perches',
                                              'complete_flights')},
        'lifecycle_bouts': {'perches': lifecycle.perches, 'flights': lifecycle.flights,
                            'censored': len(lifecycle.censored)},
    }, session.brain


def pooled(runs):
    """Pool raw samples across runs; distributions, rates and shares."""
    def merge(key):
        out = defaultdict(list)
        for run in runs:
            for state, values in run['raw'][key].items():
                out[state] += values
        return out
    alive = sum(r['alive_minutes'] for r in runs)
    airborne = sum(r['airborne_minutes'] for r in runs)
    counts = Counter()
    transitions = Counter()
    for run in runs:
        counts.update(run['counts'])
        transitions.update(run['transitions'])
    turns = merge('turn_degrees')
    drift = [v for r in runs for v in r['raw']['drift']]
    perches = [v for r in runs for v in r['lifecycle_bouts']['perches']]
    flights = [v for r in runs for v in r['lifecycle_bouts']['flights']]
    states = sorted({s for r in runs for s in r['occupancy']})
    return {
        'label': 'simulator diagnostics; no player acts and no difficulty metric is used',
        'config_versions': sorted({r['config_version'] for r in runs}),
        'seeds': [r['seed'] for r in runs], 'alive_minutes': alive, 'airborne_minutes': airborne,
        'occupancy': {s: sum(r['occupancy'].get(s, 0)*r['alive_minutes'] for r in runs)/alive for s in states},
        'ecology_driving_share': {s: sum(r['ecology_driving_ticks'].get(s, 0) for r in runs)
                                  / max(1, sum(sum(r['ecology_driving_ticks'].values()) for r in runs))
                                  for s in states},
        'lifecycle_fractions': {k: sum((r['lifecycle']['fractions'][k] or 0)*r['alive_minutes'] for r in runs)/alive
                                for k in ('airborne', 'perched', 'feeding')},
        'speed_bl_s': {s: quantiles(v) for s, v in sorted(merge('speed').items())},
        'acceleration_bl_s2': {s: quantiles(v, (50, 90, 99)) for s, v in sorted(merge('accel').items())},
        'deceleration_bl_s2': {s: quantiles(v, (50, 90, 99)) for s, v in sorted(merge('decel').items())},
        'settle_seconds': {s: quantiles(v) for s, v in sorted(merge('settle').items())},
        'unsettled_episodes': dict(sum((Counter(r['unsettled_episodes']) for r in runs), Counter())),
        'episode_seconds': {s: quantiles(v) for s, v in sorted(merge('episodes').items())},
        'censored_episodes': dict(sum((Counter(r['censored_episodes']) for r in runs), Counter())),
        'transitions': dict(sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0]))),
        'turns_per_airborne_min': {k: len(v)/airborne for k, v in sorted(turns.items())},
        'turn_degrees': {k: quantiles(v) for k, v in sorted(turns.items())},
        'spontaneous_interval_seconds': quantiles([v for r in runs for v in r['raw']['spontaneous_intervals']]),
        'drift_rad_s': {'n': len(drift), 'mean_abs': sum(abs(v) for v in drift)/len(drift) if drift else None,
                        'sd': quantiles(drift).get('sd')},
        'odor': {'detected_share_of_alive': counts['odor_detected']/counts['alive'],
                 'encounters_per_alive_min': counts['odor_encounters']/alive,
                 'odor_track_upwind_share': (counts['odor_track_upwind']/counts['odor_track_airborne']
                                             if counts['odor_track_airborne'] else None),
                 'food_touchdowns': counts['touchdown_food'], 'other_touchdowns': counts['touchdown_other'],
                 'first_food_touchdown_seconds': [r['first_food_touchdown_seconds'] for r in runs]},
        'lifecycle_bouts': {'perch_seconds': quantiles(perches), 'flight_seconds': quantiles(flights),
                            'censored': sum(r['lifecycle_bouts']['censored'] for r in runs)},
        'space': {'visited_cell_share': sum(r['cells_visited'] for r in runs)/sum(r['grid_cells'] for r in runs),
                  'near_wall_share_of_airborne': counts['near_wall']/counts['airborne']},
        'safety': {'escape_onsets': counts['escape_onsets'],
                   'escape_onsets_per_alive_min': counts['escape_onsets']/alive},
    }


def screen(before, after, stage_states=()):
    """The preregistered pathology screen (game/M1_8_B_COMPLETION_DESIGN.md section 1, check 5).

    Fails on: chatter (a state outside `stage_states` whose median completed episode falls
    below 0.5 s where it was at least 1 s), a visited-cell share below half, no touchdown
    where there were some, or a perched share more than doubled.
    """
    failures = []
    for state, b in before['episode_seconds'].items():
        a = after['episode_seconds'].get(state, {})
        if state in stage_states or b.get('n', 0) == 0 or a.get('n', 0) == 0:
            continue
        if b['p50'] >= 1.0 and a['p50'] < 0.5:
            failures.append('chatter in %s: median episode %.2f s -> %.2f s' % (state, b['p50'], a['p50']))
    if after['space']['visited_cell_share'] < 0.5*before['space']['visited_cell_share']:
        failures.append('visited-cell share halved')
    touchdowns = lambda s: s['odor']['food_touchdowns'] + s['odor']['other_touchdowns']
    if touchdowns(before) > 0 and touchdowns(after) == 0:
        failures.append('no touchdown')
    if after['lifecycle_fractions']['perched'] > 2*before['lifecycle_fractions']['perched']:
        failures.append('perched share more than doubled')
    return failures


def compare(before, after, stage_states=()):
    def mean(block, state):
        return block.get(state, {}).get('mean')
    rows = []
    for state in sorted(set(before['occupancy']) | set(after['occupancy'])):
        rows.append((state, before['ecology_driving_share'].get(state), after['ecology_driving_share'].get(state),
                     mean(before['speed_bl_s'], state), mean(after['speed_bl_s'], state),
                     mean(before['episode_seconds'], state), mean(after['episode_seconds'], state),
                     before['episode_seconds'].get(state, {}).get('p50'),
                     after['episode_seconds'].get(state, {}).get('p50')))
    return {'per_state': [dict(zip(('state', 'driving_share_before', 'driving_share_after', 'speed_mean_before',
                                    'speed_mean_after', 'episode_mean_before', 'episode_mean_after',
                                    'episode_median_before', 'episode_median_after'), r)) for r in rows],
            'lifecycle_fractions': {'before': before['lifecycle_fractions'], 'after': after['lifecycle_fractions']},
            'odor': {'before': before['odor'], 'after': after['odor']},
            'space': {'before': before['space'], 'after': after['space']},
            'safety': {'before': before['safety'], 'after': after['safety']},
            'pathology_screen_failures': screen(before, after, stage_states)}


def load_arm(commit):
    if commit is None:
        return load_config(ROOT/'game_room_config.json')
    return json.loads(subprocess.check_output(['git', 'show', commit + ':game_room_config.json'],
                                              cwd=ROOT, text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary', 'compare'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--before', type=Path, help='compare: the previous stage output directory')
    parser.add_argument('--stage-states', default='', help='compare: states the stage targets (comma list)')
    parser.add_argument('--commit', help='read game_room_config.json from this commit')
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    parser.add_argument('--ticks', type=int, default=TICKS)
    args = parser.parse_args()
    if args.mode == 'run':
        config = load_arm(args.commit)
        args.out.mkdir(parents=True, exist_ok=True)
        brain = None
        for seed in SEEDS[args.lane::args.lanes]:
            started = time.perf_counter()
            run, brain = measure(config, seed, args.ticks, brain)
            run['numba_threads'] = int(os.environ['NUMBA_NUM_THREADS'])
            (args.out/('seed%d.json' % seed)).write_text(json.dumps(run)+'\n', encoding='utf-8')
            print('seed', seed, 'config', config['config_version'],
                  '%.0f s' % (time.perf_counter() - started), flush=True)
        return
    if args.mode == 'compare':
        load = lambda d: json.loads((d/'summary.json').read_text(encoding='utf-8'))
        result = compare(load(args.before), load(args.out), tuple(filter(None, args.stage_states.split(','))))
        (args.out/'compare.json').write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
        print(json.dumps(result, indent=1))
        return
    runs = [json.loads((args.out/('seed%d.json' % s)).read_text(encoding='utf-8')) for s in SEEDS]
    summary = pooled(runs)
    (args.out/'summary.json').write_text(json.dumps(summary, indent=1)+'\n', encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
