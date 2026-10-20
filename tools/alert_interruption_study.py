"""M1.8 research: how the ecology consumes the policy's ALERT state (research only).

No runtime file, configuration, calibration record, policy or recorder is changed. Each
counterfactual mapping exists only inside this tool: it wraps `session.ecology.step` on a
live session and changes the ThreatState handed to the ecology alone. The fixed policy,
the N4B1C decoder, the lifecycle (which still receives the accepted threat) and the world
run unchanged. No player acts and no difficulty metric is computed.

Mappings compared (all apply to the ecology only):

* accepted: the session's mapping. The ecology sees ALERT whenever the policy reports
  ALERT, an alert saccade is requested, or an ALERT saccade is executing.
* executed_response: the ecology sees ALERT only while the fly executes or requests a
  saccade; the policy's ALERT state alone (for example after one spontaneous DNp01 spike)
  no longer interrupts the ecological state.
* sustained_alert: the ecology also sees ALERT once the policy's ALERT state has lasted
  for the policy's own alert-saccade dwell (`policy.alert_saccade_dwell_seconds`).

ESCAPE is never altered.

    python tools/alert_interruption_study.py --report artifacts/m1_8_alert/study.json
"""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.ecology import ThreatState
from game.session import Session, load_config
from tools.explore_speed_diagnostics import describe

DT = 0.02
PARKED_POINTER = (1920, 388.8)
MAPPINGS = ('accepted', 'executed_response', 'sustained_alert')


def install(session, mapping, dwell_ticks, log):
    """Wrap the ecology's step so that only the ecology sees the counterfactual threat."""
    ecology = session.ecology
    original = ecology.step
    run = {'alert_ticks': 0}

    def step(sense, threat, dt):
        neural = session.policy_diagnostics.get('behavior_state', 'CALM')
        run['alert_ticks'] = run['alert_ticks'] + 1 if neural == 'ALERT' else 0
        executed = (session.fly_loop.last_action.saccade != 0
                    or session.world.saccades.kind in ('ALERT', 'ESCAPE'))
        log['threat_not_calm_while_perched'] += (threat is not ThreatState.CALM
                                                 and session.world.lifecycle.stationary)
        log['perched_ticks'] += session.world.lifecycle.stationary
        seen = threat
        if threat is ThreatState.ALERT and not executed:
            if mapping == 'executed_response' or (mapping == 'sustained_alert'
                                                  and run['alert_ticks'] < dwell_ticks):
                seen = ThreatState.CALM
        if seen is ThreatState.ALERT and ecology.state not in ('ALERT', 'ESCAPE', 'RECOVER'):
            log['alert_entries_from_policy_state_only'] += not executed
        return original(sense, seen, dt)

    ecology.step = step


def closed_loop(config, seed, ticks, mapping, brain=None):
    session = Session(config, brain=brain, seed=seed, mode='evaluation')
    dwell_ticks = max(1, int(round(config['policy']['alert_saccade_dwell_seconds'] / DT)))
    log = {'threat_not_calm_while_perched': 0, 'perched_ticks': 0,
           'alert_entries_from_policy_state_only': 0}
    install(session, mapping, dwell_ticks, log)
    policy = session.fly_loop.policy
    occupancy, transitions, episodes, events = {}, {}, {}, {}
    escapes = 0
    previous, started = None, 0
    try:
        for tick in range(ticks):
            session.tick(pointer=PARKED_POINTER)
            world = session.world
            if not world.fly.alive:
                continue
            diag = policy.criterion_diagnostics()
            escapes += (diag['escape_trigger_channel'] != 'NONE'
                        and policy.refractory_remaining == policy.refractory_ticks)
            state = session.ecology.state
            occupancy[state] = occupancy.get(state, 0) + 1
            if state != previous:
                if previous is not None:
                    key = previous + '->' + state
                    transitions[key] = transitions.get(key, 0) + 1
                    episodes.setdefault(previous, []).append((tick-started)*DT)
                previous, started = state, tick
            for event in world.lifecycle.events:
                events[event['type']] = events.get(event['type'], 0) + 1
        alive = sum(occupancy.values())
        minutes = alive*DT/60
        result = {'seed': seed, 'mapping': mapping, 'ticks': ticks, 'alive_ticks': alive,
                  'ecology_state_occupancy': {k: v/alive for k, v in sorted(occupancy.items())},
                  'alert_entries_per_min': transitions_into(transitions, 'ALERT')/minutes,
                  'transit_entries': transitions_into(transitions, 'TRANSIT'),
                  'episode_seconds': {k: describe(v) for k, v in sorted(episodes.items())},
                  'transitions': dict(sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0]))),
                  'policy_escapes': escapes,
                  'lifecycle_events': dict(sorted(events.items())),
                  'perched_fraction': log['perched_ticks']/alive,
                  'perched_ticks_with_threat_not_calm': log['threat_not_calm_while_perched'],
                  'alert_entries_from_policy_state_only': log['alert_entries_from_policy_state_only']}
    finally:
        session.close()
    return result, session.brain


def transitions_into(transitions, state):
    return sum(v for k, v in transitions.items() if k.endswith('->' + state))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT/'artifacts/m1_8_alert/study.json')
    parser.add_argument('--ticks', type=int, default=9000)   # 180 simulated seconds
    parser.add_argument('--seeds', type=int, nargs='+', default=[101, 255, 4242])
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    runs, brain = [], None
    for mapping in MAPPINGS:
        for seed in args.seeds:
            run, brain = closed_loop(config, seed, args.ticks, mapping, brain)
            runs.append(run)
            print(mapping, seed, 'alert entries/min', round(run['alert_entries_per_min'], 1),
                  'transit entries', run['transit_entries'], 'escapes', run['policy_escapes'],
                  'events', run['lifecycle_events'], flush=True)
    result = {'label': 'research counterfactual; no runtime change; no player; no difficulty metric',
              'config_version': config['config_version'], 'mappings': list(MAPPINGS),
              'seeds': args.seeds, 'runs': runs}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print('written', args.report)


if __name__ == '__main__':
    main()
