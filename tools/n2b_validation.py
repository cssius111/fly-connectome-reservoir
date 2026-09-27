"""M1.8-N2b validation: exact runtime replays and comparison with the research study.

Every policy here is built by `game.session.build_policy` from a real configuration:

* legacy: the N1 baseline ROOM configuration (76806f0), scalar single-sample decoder;
* strict: the superseded M1.8-N2 ROOM configuration v14 (FAST 2.20, 3 consecutive),
  preserved in artifacts/m1_8_n2b/, which still resolves the unmodified N2 record;
* n2b: the working-tree ROOM configuration (dual_path_window_v1).

Outputs artifacts/m1_8_n2b/validation.json. Research results for comparison come from
artifacts/m1_8_n2/temporal_study.json, criterion 'C* 3-of-5 + current qualifies, FAST 2.10'.

    python tools/n2b_validation.py --session results/game/sessions/<id>
"""
from __future__ import annotations

import argparse
import copy
from collections import deque
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.action import MotorState  # noqa: E402
from game.session import build_policy, load_config  # noqa: E402
from tools.n2_decoder_replay import N0, N1, n0_loom, n1, no_loom  # noqa: E402
from tools.n2_fast_threshold_study import load_session, motor_of  # noqa: E402

DT = 0.02
LOW = 1.45
OUT = ROOT / 'artifacts/m1_8_n2b'
RESEARCH = 'C* 3-of-5 + current qualifies, FAST 2.10'
STATE_FIELDS = ('_cooldown', '_turn', '_side_left', '_side_right', '_state', '_escape_strength',
                '_alert_ticks', '_saccade_cooldown', '_streak', '_channel')


def configs():
    legacy = json.loads(subprocess.check_output(
        ['git', 'show', '76806f0:game_room_config.json'], cwd=ROOT, text=True))
    strict = load_config(OUT / 'strict_n2_room_config_v14.json')
    return {'legacy': legacy, 'strict': strict, 'n2b': load_config(ROOT / 'game_room_config.json')}


def policy(name):
    return build_policy(configs()[name], ROOT)[0]


# ---------------------------------------------------------------- human session ---
def synced(snapshot, rows, index):
    """Runtime N2b policy carrying the recorded policy's exact state at `index`.

    Motor/refractory state is copied field by field. The rolling window is rebuilt from
    the recorded neural stream: the last five brain-stepped samples since the recorded
    policy's last escape (an escape clears the window).
    """
    p = policy('n2b')
    for field in STATE_FIELDS:
        setattr(p, field, copy.deepcopy(getattr(snapshot, field)))
    stepped = [i for i in range(index) if rows[i]['neural']['brain_stepped']]
    last_escape = max((i for i in stepped if rows[i]['action']['escape']), default=-1)
    recent = [i for i in stepped[-p.sustained_window_samples:] if i > last_escape]
    p._window = deque((rows[i]['neural']['dnp01_total'] >= LOW for i in recent),
                      maxlen=p.sustained_window_samples)
    return p


def human(path):
    episodes = load_session(path)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    recorded_config = manifest['config']
    # Harness: the recorded (strict) policy rebuilt from the recorded config reproduces
    # every recorded action.
    mismatches = checked = 0
    strikes, perches = [], []
    snapshots = {}
    for ep, rows in episodes.items():
        rec = build_policy(recorded_config, ROOT)[0]
        rec.reset()
        prev, click = 0, None
        wanted = set()
        for i, row in enumerate(rows):
            f = row['event_flags']
            if f['strike_start']:
                click = i
            if click is not None and (f['hit'] or f['miss']):
                strikes.append((ep, prev, click, i))
                wanted |= {prev, click}
                prev, click = i + 1, None
        attached = [bool(r['lifecycle']['attached']) for r in rows]
        i = 0
        while i < len(rows):
            if attached[i]:
                j = i
                while j + 1 < len(rows) and attached[j + 1]:
                    j += 1
                perches.append((ep, i, j))
                wanted.add(i)
                i = j + 1
            else:
                i += 1
        for i, row in enumerate(rows):
            if i in wanted:
                snapshots[(ep, i)] = copy.deepcopy(rec)
            if row['neural']['brain_stepped']:
                a = rec.decide(motor_of(row))
                r = row['action']
                checked += 1
                mismatches += (a.escape, a.lateral, a.forward, a.turn, a.strength, a.saccade) != (
                    r['escape'], r['lateral'], r['forward'], r['turn'], r['strength'], r['saccade'])

    def first_fire(p, rows, start, stop):
        for i in range(start, stop):
            if rows[i]['neural']['brain_stepped'] and p.decide(motor_of(rows[i])).escape:
                return i, p.criterion_diagnostics()['escape_trigger_channel']
        return None

    s_rows, p_rows = [], []
    for ep, seg, click, resolve in strikes:
        rows = episodes[ep]
        post = first_fire(synced(snapshots[(ep, click)], rows, click), rows, click, resolve + 1)
        pre = first_fire(synced(snapshots[(ep, seg)], rows, seg), rows, seg, click)
        s_rows.append({'episode': ep, 'click_time_s': rows[click]['session_simulation_time'],
                       'hit': bool(rows[resolve]['event_flags']['hit']),
                       'latency_s': None if post is None else round((post[0] - click) * DT, 6),
                       'channel': None if post is None else post[1],
                       'pre_click_escape': pre is not None})
    for ep, a, b in perches:
        rows = episodes[ep]
        fire = first_fire(synced(snapshots[(ep, a)], rows, a), rows, a, b + 1)
        peak = max(range(a, b + 1), key=lambda i: rows[i]['neural']['dnp01_total'])
        p_rows.append({'episode': ep, 'start_s': rows[a]['session_simulation_time'],
                       'end_s': rows[b]['session_simulation_time'],
                       'peak_dnp01': rows[peak]['neural']['dnp01_total'],
                       'peak_time_s': rows[peak]['session_simulation_time'],
                       'fire': None if fire is None else {
                           'time_s': rows[fire[0]]['session_simulation_time'],
                           'channel': fire[1]}})
    lat = [r['latency_s'] for r in s_rows if r['latency_s'] is not None]
    channels = {}
    for r in s_rows:
        if r['channel']:
            channels[r['channel']] = channels.get(r['channel'], 0) + 1
    return {'harness_check': {'ticks_checked': checked, 'action_mismatches': mismatches},
            'strikes': s_rows, 'perches': p_rows,
            'summary': {'fired': len(lat), 'strikes': len(s_rows),
                        'median_s': float(np.median(lat)), 'mean_s': float(np.mean(lat)),
                        'p95_s': float(np.percentile(lat, 95)), 'channels': channels,
                        'pre_click_segments_with_escape': sum(r['pre_click_escape'] for r in s_rows)}}


# ------------------------------------------------------------ first divergence ---
def first_divergence(pre_trace, reference):
    out = []
    for s in json.loads(Path(pre_trace).read_text(encoding='utf-8'))['scenarios']:
        i = s['fields'].index('dnp01_total')
        totals = [float.fromhex(r[i]) for r in s['rows']]
        ref, new = policy(reference), policy('n2b')
        if s['scenario'] in ('game_preset', 'lab_preset'):
            out.append({'scenario': s['scenario'], 'note': 'single-sample decoder; unchanged'})
            continue
        found = None
        for t, v in enumerate(totals):
            m = MotorState(v / 2, v / 2, 0.0, 0.0, np.zeros(1))
            a, b = ref.decide(m), new.decide(m)
            if a.escape != b.escape:
                c = new.criterion_diagnostics()
                found = {'tick': t, 'dnp01_total': v,
                         'reference_escape': a.escape, 'n2b_escape': b.escape,
                         'n2b_channel': c['escape_trigger_channel'] if b.escape else None,
                         'last_5_samples': ''.join('H' if x >= LOW else 'L'
                                                   for x in totals[max(0, t - 4):t + 1]),
                         'reference_refractory_ticks': ref.refractory_remaining,
                         'reference_streak': ref.criterion_diagnostics()['escape_sustained_streak']}
                break
        out.append({'scenario': s['scenario'], 'first_decision_divergence': found})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--out', type=Path, default=OUT / 'validation.json')
    args = p.parse_args()
    raw = np.load(N0 / 'raw.npz')
    per = json.loads((N0 / 'study.json').read_text(encoding='utf-8'))['no_loom']['ticks_per_trial']
    null = raw['null']
    null_trials = [null[i:i + per] for i in range(0, null.size, per)]
    continuous = [np.load(N0 / 'continuous.npz')['trace']]
    data = np.load(N1 / 'trials.npz')
    meta = json.loads((N1 / 'trials_meta.json').read_text(encoding='utf-8'))
    research = json.loads((ROOT / 'artifacts/m1_8_n2/temporal_study.json').read_text(encoding='utf-8'))
    rc = research['candidates'][RESEARCH]

    out = {'label': 'M1.8-N2b exact runtime validation', 'policies': {}}
    for name in ('legacy', 'strict', 'n2b'):
        summary, per_trial = n1(policy(name), data, meta)
        out['policies'][name] = {
            'criterion': policy(name).criterion_diagnostics(),
            'n0_no_loom_primary': no_loom(policy(name), null_trials, 'accepted 150 x 1400-tick arm'),
            'n0_no_loom_continuous': no_loom(policy(name), continuous, 'continuous 30000 ticks'),
            'n0_loom_150': n0_loom(policy(name), raw['loom'], raw['committed']),
            'n1_per_class': summary}
        if name == 'n2b':
            out['n1_trials_match_research'] = ([t['fires'] for t in per_trial]
                                               == [t['fires'] for t in rc['n1_trials']])
            out['n0_matches_research'] = (out['policies']['n2b']['n0_no_loom_primary']['policy_firings']
                                          == rc['n0']['policy_firings'])
    h = human(args.session)
    rh = research['human']['per_candidate'][RESEARCH]
    h['strikes_match_research'] = ([(r['latency_s'], r['channel'], r['pre_click_escape'])
                                    for r in h['strikes']]
                                   == [(r['latency_s'], r['channel'], r['pre_click_escape'])
                                       for r in rh['strikes']])
    h['perches_match_research'] = ([None if r['fire'] is None else (r['fire']['time_s'], r['fire']['channel'])
                                    for r in h['perches']]
                                   == [None if r['fire'] is None else (r['fire']['time_s'], r['fire']['channel'])
                                       for r in rh['perches']])
    out['human'] = h
    out['first_divergence_vs_76806f0'] = first_divergence(ROOT / 'artifacts/m1_8_n2/pre-trace.json',
                                                          'legacy')
    out['first_divergence_vs_strict_n2'] = first_divergence(OUT / 'pre-strict-trace.json', 'strict')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')

    for name, e in out['policies'].items():
        a = e['n0_no_loom_primary']
        print('[%s] N0 %d %s %.4f/min upper95 %.4f | continuous %d | N0 loom %d/150 %s' % (
            name, a['policy_firings'], a['by_channel'], a['events_per_minute_observed'],
            a['upper95_one_sided_per_minute'], e['n0_no_loom_continuous']['policy_firings'],
            e['n0_loom_150']['fired_in_committed_window'], e['n0_loom_150']['first_in_window_by_channel']))
        for cls, s in e['n1_per_class'].items():
            print('   %-17s %2d  F%2d S%2d  med %s p95 %s | onset med %s p95 %s' % (
                cls, s['fired_in_window'], s['fast_count'], s['sustained_count'],
                s['median_latency_from_click_s'], s['p95_latency_from_click_s'],
                s['median_latency_from_onset_s'], s['p95_latency_from_onset_s']))
    print('N1 trials match research:', out['n1_trials_match_research'],
          '| N0 matches research:', out['n0_matches_research'])
    print('human harness', h['harness_check'], 'summary', h['summary'])
    print('human strikes match research:', h['strikes_match_research'],
          '| perches match:', h['perches_match_research'], '| perches', h['perches'])
    for key in ('first_divergence_vs_76806f0', 'first_divergence_vs_strict_n2'):
        print(key)
        for row in out[key]:
            print('  ', row)
    print('written', args.out)


if __name__ == '__main__':
    main()
