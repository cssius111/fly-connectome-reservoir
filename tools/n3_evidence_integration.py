"""M1.8-N3 research: neural evidence integration and threat-acquisition latency.

Research only. No runtime file, configuration or calibration record is changed, and no
brain is run: every result is a replay of already-recorded DNp01 traces.

Inputs
* N0: the accepted 210,000-tick no-loom arm (150 x 1400 ticks, reset per trial) and the
  secondary 30,000-tick continuous arm;
* N1: all 300 loom-robustness trials (physical swatter -> Retina -> LC4/LPLC2 ->
  MaleCNS -> DNp01), with their recorded Retina, encoder and distance traces;
* two human ROOM sessions: the strict-N2 session and the N2b second-acceptance session.

Neural-only rule
Every candidate trigger is a function of the summed DNp01 trace history only. The trace
the policy observes is an exponentially decaying spike trace (tau = trace_tau_seconds,
+1 per spike), so the DNp01 spike count of each sample is recovered exactly from two
consecutive trace samples (trace_t - decay * trace_{t-1}); that is a function of the
policy's own neural observation history, not a new input. Retina, encoder drive and
distance are used OFFLINE ONLY, to label and explain recorded situations.

Candidate semantics
* candidates are a subclass of the runtime FixedEscapePolicy, so strength, side,
  steering, alert state, saccades and the 0.4 s refractory rule are the unchanged runtime
  code; only the escape trigger differs;
* the evidence statistic is updated on every sample, refractory samples included, is
  cleared when an escape fires and on reset, and cannot fire during refractory;
* dual candidates fire on FAST (one sample >= 2.10) OR the integrated statistic; FAST
  wins the channel label.

Thresholds are study values. Each integrated threshold is set from the maximum of its
statistic on the first half of N0 (trials 0-74, the selection half) plus a fixed margin,
then evaluated on the full N0, on the held-out half (trials 75-149) and on the
continuous arm. The full-N0 count is therefore partly in-sample; the held-out half is
not.

Human replay is open-loop. Each episode is cut into segments that begin at the episode
start or on the sample after a recorded escape, where every decoder's evidence is empty.
The candidate takes the recorded policy's exact state at the segment start and receives
the recorded neural stream, which is exactly what it would have received until its first
decision that differs from the recorded one. A candidate's first firing inside a segment
is therefore exact; anything after a recorded escape the candidate did not make is
post-divergence and labelled as such.

    python tools/n3_evidence_integration.py
"""
from __future__ import annotations

import argparse
from collections import deque
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.action import FixedEscapePolicy, MotorState  # noqa: E402
from game.session import build_policy, load_config  # noqa: E402
from tools.n2_decoder_replay import N0, N1, n1, no_loom  # noqa: E402

DT = 0.02
LOW = 1.45
FAST = 2.10
BASELINE_COMMIT = '76806f0'
SESSIONS = {
    'strict_n2': ROOT / 'results/game/sessions/20260923T005351.731330Z-38255ec8',
    'n2b': ROOT / 'results/game/sessions/20260924T000111.561327Z-c337a721',
}
# The slow, close, non-strike interval reported from the N2b human session.
SLOW_CLOSE = {'session': 'n2b', 'episode': 5, 'first_tick': 610, 'last_tick': 669}
BODY_LENGTH_UNITS = 24.0
ZERO = np.zeros(1)
SELECTION_TRIALS = 75
MARGIN = 0.02
BOUT_GAP_TICKS = 10


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def trace_decay():
    tau = float(load_config(ROOT / 'game_room_config.json')['brain']['trace_tau_seconds'])
    # flybrain.Trace stores the trace in float32 with a float32 decay factor.
    return float(np.float32(np.exp(-DT / tau)))


DECAY = trace_decay()


# --------------------------------------------------------------- statistics ---
class Statistic:
    """Incremental DNp01 evidence statistic; update(total) is called on every sample."""
    memory = 0

    def __init__(self):
        self._prev_total = 0.0
        self.reset()

    def reset(self):
        self._prev_total = 0.0
        self.clear()

    def clear(self):
        """Forget evidence; the spike deconvolution keeps its previous trace sample."""

    def spikes(self, total):
        s = max(0, int(round(total - DECAY * self._prev_total)))
        self._prev_total = total
        return s

    def update(self, total):
        raise NotImplementedError


class Instant(Statistic):
    name = 'instantaneous trace'

    def clear(self):
        self.value = 0.0

    def update(self, total):
        self.spikes(total)
        self.value = total
        return total


class WindowSum(Statistic):
    def __init__(self, w, mean=False):
        self.w, self.mean = int(w), bool(mean)
        self.memory = self.w
        self.name = '%s of trace over %d samples (%d ms)' % ('mean' if mean else 'sum',
                                                             self.w, self.w * 20)
        super().__init__()

    def clear(self):
        self._buf = deque(maxlen=self.w)

    def update(self, total):
        self.spikes(total)
        self._buf.append(total)
        s = float(sum(self._buf))
        return s / self.w if self.mean else s


class Leaky(Statistic):
    """Normalised leaky accumulator of the trace: E = a E + (1 - a) trace."""

    def __init__(self, tau_ms):
        self.tau_ms = float(tau_ms)
        self.a = math.exp(-DT / (self.tau_ms / 1000.0))
        self.memory = int(math.ceil(5 * self.tau_ms / 20))
        self.name = 'leaky accumulator of trace, tau %d ms' % self.tau_ms
        super().__init__()

    def clear(self):
        self.value = 0.0

    def update(self, total):
        self.spikes(total)
        self.value = self.a * self.value + (1.0 - self.a) * total
        return self.value


class SpikeCount(Statistic):
    """DNp01 spikes (both sides) in the last w samples, deconvolved from the trace."""

    def __init__(self, w):
        self.w = int(w)
        self.memory = self.w
        self.name = 'DNp01 spike count over %d samples (%d ms)' % (self.w, self.w * 20)
        super().__init__()

    def clear(self):
        self._buf = deque(maxlen=self.w)

    def update(self, total):
        self._buf.append(self.spikes(total))
        return float(sum(self._buf))


class HCount(Statistic):
    """Binary counting reference: samples >= 1.45 among the last w."""

    def __init__(self, w=5):
        self.w = int(w)
        self.memory = self.w
        self.name = 'count of samples >= 1.45 in last %d' % self.w
        super().__init__()

    def clear(self):
        self._buf = deque(maxlen=self.w)

    def update(self, total):
        self.spikes(total)
        self._buf.append(total >= LOW)
        return float(sum(self._buf))


def series(stat, trace):
    stat.reset()
    return np.array([stat.update(float(v)) for v in trace])


# ------------------------------------------------------------------ policies ---
_RUNTIME = []


def runtime_kwargs():
    """A fresh copy of the working-tree ROOM runtime policy (built once)."""
    if not _RUNTIME:
        _RUNTIME.append(build_policy(load_config(ROOT / 'game_room_config.json'), ROOT)[0])
    p = copy.deepcopy(_RUNTIME[0])
    p.reset()
    return p


def copy_base_params(dst, src):
    for name in ('refractory_ticks', 'tick_seconds', 'forward_bias', 'turn_gain',
                 'alert_threshold', 'steering_alpha', 'alert_saccade_strength',
                 'saccade_interval_ticks', 'alert_dwell_ticks'):
        setattr(dst, name, getattr(src, name))


class EvidencePolicy(FixedEscapePolicy):
    """Runtime policy whose escape trigger is `stat >= theta` (OR FAST when dual)."""

    def __init__(self, stat, theta, fast=None, guard_spike=False):
        self.stat, self.theta = stat, float(theta)
        self.fast, self.guard_spike = fast, bool(guard_spike)
        self._value, self._spiked = 0.0, False
        base = runtime_kwargs()
        super().__init__(base.threshold, 0.4, DT)
        copy_base_params(self, base)

    def reset(self):
        super().reset()
        self.stat.reset()
        self._value = 0.0

    def _trigger_channel(self, total):
        if self.fast is not None and total >= self.fast:
            return 'FAST'
        if self._value >= self.theta and (self._spiked or not self.guard_spike):
            return 'INTEGRATED'
        return None

    def decide(self, motor):
        before = self.stat._prev_total
        self._value = self.stat.update(motor.dnp01_total)
        self._spiked = motor.dnp01_total - DECAY * before >= 0.5
        action = super().decide(motor)
        if action.escape:
            self.stat.clear()
        return action

    def criterion_diagnostics(self):
        return {'escape_trigger_channel': self._channel}


def legacy_policy():
    text = subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                   cwd=ROOT, text=True)
    return build_policy(json.loads(text), ROOT)[0]


def strict_n2_policy():
    base = runtime_kwargs()
    p = FixedEscapePolicy(base.threshold, 0.4, DT, fast_threshold=2.20, persistence_samples=3)
    copy_base_params(p, base)
    return p


def n2b_policy():
    return runtime_kwargs()


def make(spec):
    kind = spec['kind']
    if kind == 'legacy':
        return legacy_policy()
    if kind == 'strict_n2':
        return strict_n2_policy()
    if kind == 'n2b':
        return n2b_policy()
    return EvidencePolicy(make_stat(spec['stat']), spec['theta'], spec.get('fast'),
                          spec.get('guard_spike', False))


def make_stat(s):
    kind = s[0]
    if kind == 'sum':
        return WindowSum(s[1])
    if kind == 'mean':
        return WindowSum(s[1], mean=True)
    if kind == 'leaky':
        return Leaky(s[1])
    if kind == 'spikes':
        return SpikeCount(s[1])
    if kind == 'hcount':
        return HCount(s[1])
    if kind == 'instant':
        return Instant()
    raise ValueError(s)


STATS = ([('sum', w) for w in (3, 5, 8, 10)] + [('mean', w) for w in (3, 5, 8, 10)]
         + [('leaky', t) for t in (60, 100, 160, 200)]
         + [('spikes', w) for w in (3, 5, 8, 10, 15, 20, 25)])


# ----------------------------------------------------------------------- data ---
def load_n0():
    raw = np.load(N0 / 'raw.npz')
    per = json.loads((N0 / 'study.json').read_text(encoding='utf-8'))['no_loom']['ticks_per_trial']
    null = raw['null']
    trials = [null[i:i + per] for i in range(0, null.size, per)]
    continuous = [np.load(N0 / 'continuous.npz')['trace']]
    return trials, continuous, raw


def load_session(path):
    rows = [json.loads(line) for line in (path / 'ticks.jsonl').open(encoding='utf-8')]
    episodes = {}
    for row in rows:
        episodes.setdefault(row['episode'], []).append(row)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    return episodes, manifest


def motor_of(row):
    n = row['neural']
    return MotorState(n['dnp01_left'], n['dnp01_right'], n['dna02_left'], n['dna02_right'], ZERO)


def drive(row):
    v = row['visual_input']
    return v['loomL'] + v['loomR'] + v['threatL'] + v['threatR']


def distance(row):
    return math.hypot(row['fly']['x'] - row['swatter']['x'], row['fly']['y'] - row['swatter']['y'])


def row_spikes(rows):
    """Deconvolved DNp01 spike count per row (the trace resets with the episode)."""
    out, prev = [], 0.0
    for r in rows:
        t = r['neural']['dnp01_total']
        out.append(max(0, int(round(t - DECAY * prev))))
        prev = t
    return out


# ------------------------------------------------------------------------- N0 ---
def n0_stat_summary(trials, stat):
    vals = np.concatenate([series(stat, t) for t in trials])
    return {'max': float(vals.max()),
            'p99_9': float(np.quantile(vals, 0.999)),
            'p99_99': float(np.quantile(vals, 0.9999))}


def n0_spike_structure(trials):
    counts = np.concatenate([np.array(row_spikes([{'neural': {'dnp01_total': float(v)}}
                                                   for v in t])) for t in trials])
    out = {'spikes_per_sample_histogram': np.bincount(counts).tolist(),
           'spike_rate_hz': float(counts.sum() / (counts.size * DT)),
           'max_spikes_in_window': {}, 'windows_with_at_least': {}}
    for w in (3, 5, 8, 10, 12, 15, 20, 25, 30):
        mx, ge = 0, {}
        for t in trials:
            k = np.array(row_spikes([{'neural': {'dnp01_total': float(v)}} for v in t]))
            cs = np.convolve(k, np.ones(w, int), 'valid')
            mx = max(mx, int(cs.max()))
            for v in (3, 4):
                ge[v] = ge.get(v, 0) + int((cs >= v).sum())
        out['max_spikes_in_window']['%d ms' % (w * 20)] = mx
        out['windows_with_at_least']['%d ms' % (w * 20)] = ge
    return out


def n0_eval(spec, trials, continuous):
    full = no_loom(make(spec), trials, 'accepted 150 x 1400-tick arm')
    held = no_loom(make(spec), trials[SELECTION_TRIALS:], 'held-out half, trials 75-149')
    cont = no_loom(make(spec), continuous, 'secondary continuous 30000-tick arm')
    return {'full': full, 'held_out': held, 'continuous': cont}


def select_theta(stat_spec, trials):
    mx = max(series(make_stat(stat_spec), t).max() for t in trials[:SELECTION_TRIALS])
    if stat_spec[0] == 'spikes':
        return float(mx + 1), float(mx)
    return float(math.ceil(mx * (1 + MARGIN) * 1000) / 1000), float(mx)


# ------------------------------------------------------------------------- N1 ---
def n1_marks(data, meta):
    """Offline timeline of every N1 trial (ticks); geometry is diagnostic only."""
    out = []
    for m in meta['trials']:
        i = m['index']
        tr, th, td = data['%d_dnp01' % i], data['%d_theta' % i], data['%d_theta_dot' % i]
        enc = data['%d_loomL' % i] + data['%d_loomR' % i] + data['%d_threatL' % i] + data['%d_threatR' % i]
        spk = np.array(row_spikes([{'neural': {'dnp01_total': float(v)}} for v in tr]))
        # The paddle is settled before the stimulus. Committed strikes start on the click
        # and approach mostly vertically, so the approach starts at the click; scripted
        # no-click classes start at their labelled expansion onset.
        approach = m['click_tick'] if m['click_tick'] is not None else m['window_start']

        def first(mask, start):
            if start is None:
                return None
            idx = np.flatnonzero(mask[start:])
            return int(idx[0] + start) if idx.size else None

        e0 = first(enc > 0, approach)
        spikes_after = [j for j in range(e0, tr.size) for _ in range(spk[j])] if e0 is not None else []
        # Offline closest approach: the peak retinal angular size after the approach start;
        # reversal: the first sample after that peak whose theta_dot is negative.
        closest = int(approach + np.argmax(th[approach:]))
        reversal = first(td < 0, closest)
        # The N0-safe spike floor: first sample holding >= 3 DNp01 spikes in 200 ms.
        cs = np.convolve(spk, np.ones(10, int))[:tr.size]
        floor = first(cs >= 3, e0)
        out.append({
            'index': i, 'kind': m['kind'], 'click': m['click_tick'],
            'window_start': m['window_start'], 'window_end': m['window_end'],
            'approach_start': approach,
            'theta_dot_onset': first(td > 0, approach),
            'encoder_onset': e0,
            'first_dnp01_spike': spikes_after[0] if len(spikes_after) > 0 else None,
            'second_dnp01_spike': spikes_after[1] if len(spikes_after) > 1 else None,
            'third_dnp01_spike': spikes_after[2] if len(spikes_after) > 2 else None,
            'first_trace_ge_1_45': first(tr >= LOW, e0),
            'first_trace_ge_2_10': first(tr >= FAST, e0),
            'closest_approach': closest, 'reversal': reversal,
            'three_spikes_in_200ms': floor,
            'third_spike_within_200ms_of_first': (len(spikes_after) > 2
                                                  and spikes_after[2] - spikes_after[0] < 10)})
    return out


def first_fire_from(fires, start):
    for f in fires:
        if start is not None and f[0] >= start:
            return f[0], f[1]
    return None, None


def n1_latency_table(marks, per_trial_by_candidate, kinds=('strong_direct', 'medium_committed', 'weak_approach',
                                                                 'glancing_pass', 'aborted_approach')):
    """Median / p95 of each chain component, in seconds, per class."""
    rows = {}
    for kind in kinds:
        ms = [m for m in marks if m['kind'] == kind]

        def stat(vals):
            vals = [v for v in vals if v is not None]
            if not vals:
                return None
            return {'n': len(vals), 'median_s': float(np.median(vals)) * DT,
                    'p95_s': float(np.percentile(vals, 95)) * DT,
                    'min_s': float(min(vals)) * DT, 'max_s': float(max(vals)) * DT}

        def diff(a, b):
            return [None if (m[a] is None or m[b] is None) else m[b] - m[a] for m in ms]

        entry = {
            'approach_start_to_approach_start': stat(diff('approach_start', 'approach_start')),
            'sensory: approach_start_to_encoder_onset': stat(diff('approach_start', 'encoder_onset')),
            'theta_dot_onset_to_encoder_onset': stat(diff('theta_dot_onset', 'encoder_onset')),
            'malecns: encoder_onset_to_first_dnp01_spike': stat(diff('encoder_onset', 'first_dnp01_spike')),
            'first_to_second_dnp01_spike': stat(diff('first_dnp01_spike', 'second_dnp01_spike')),
            'first_to_third_dnp01_spike': stat(diff('first_dnp01_spike', 'third_dnp01_spike')),
            'approach_start_to_third_dnp01_spike': stat(diff('approach_start', 'third_dnp01_spike')),
            'approach_start_to_first_trace_ge_1_45': stat(diff('approach_start', 'first_trace_ge_1_45')),
            'approach_start_to_first_trace_ge_2_10': stat(diff('approach_start', 'first_trace_ge_2_10')),
            'approach_start_to_three_spikes_in_200ms': stat(diff('approach_start', 'three_spikes_in_200ms')),
            'approach_start_to_closest_approach': stat(diff('approach_start', 'closest_approach')),
            'approach_start_to_reversal': stat(diff('approach_start', 'reversal')),
            'third_spike_within_200ms_of_first': sum(m['third_spike_within_200ms_of_first'] for m in ms),
            'decoder': {}}
        for name, per_trial in per_trial_by_candidate.items():
            by_index = {t['index']: t for t in per_trial}
            fire = [first_fire_from(by_index[m['index']]['fires'], m['approach_start'])[0] for m in ms]
            entry['decoder'][name] = {
                'approach_start_to_fire': stat([None if f is None else f - m['approach_start'] for f, m in zip(fire, ms)]),
                'three_spikes_in_200ms_to_fire': stat([None if (f is None or m['three_spikes_in_200ms'] is None)
                                                       else f - m['three_spikes_in_200ms']
                                                       for f, m in zip(fire, ms)]),
                'fires_before_closest_approach': sum(1 for f, m in zip(fire, ms)
                                                     if f is not None and f <= m['closest_approach']),
                'first_dnp01_spike_to_fire': stat([None if (f is None or m['first_dnp01_spike'] is None)
                                                   else f - m['first_dnp01_spike']
                                                   for f, m in zip(fire, ms)]),
                'third_dnp01_spike_to_fire': stat([None if (f is None or m['third_dnp01_spike'] is None)
                                                   else f - m['third_dnp01_spike']
                                                   for f, m in zip(fire, ms)])}
        rows[kind] = entry
    return rows


def n1_distributions(data, meta, stat_spec, n0_max):
    """Per-trial peak of a statistic inside the labelled window and the first tick at
    which it exceeds the N0 maximum (the earliest a zero-N0 threshold could fire)."""
    out = {}
    for m in meta['trials']:
        i = m['index']
        tr, w = data['%d_dnp01' % i], data['%d_window' % i]
        v = series(make_stat(stat_spec), tr)
        c = out.setdefault(m['kind'], {'peaks': [], 'exceed_click_latency_ticks': []})
        c['peaks'].append(float(v[w].max()) if w.any() else 0.0)
        idx = np.flatnonzero((v > n0_max) & w)
        if idx.size and m['click_tick'] is not None:
            c['exceed_click_latency_ticks'].append(int(idx[0] - m['click_tick']))
    summary = {}
    for kind, c in out.items():
        p, lat = np.array(c['peaks']), np.array(c['exceed_click_latency_ticks'])
        summary[kind] = {'median_peak': float(np.median(p)), 'p10_peak': float(np.percentile(p, 10)),
                         'trials_exceeding_n0_max': int((p > n0_max).sum()), 'trials': int(p.size),
                         'median_exceed_latency_from_click_s': float(np.median(lat)) * DT if lat.size else None,
                         'p95_exceed_latency_from_click_s': float(np.percentile(lat, 95)) * DT if lat.size else None}
    return summary


# ---------------------------------------------------------------------- human ---
def recorded_policy(manifest):
    return build_policy(manifest['config'], ROOT)[0]


def reproduce(episodes, manifest):
    """Replay the recorded decoder on the recorded stream; every decision must match."""
    mismatches, snapshots = 0, {}
    for ep, rows in episodes.items():
        p = recorded_policy(manifest)
        p.reset()
        snaps = {0: copy.deepcopy(p)}
        for i, row in enumerate(rows):
            if row['neural']['brain_stepped']:
                a = p.decide(motor_of(row))
                if a.escape != row['action']['escape'] or not math.isclose(
                        a.turn, row['action']['turn'], rel_tol=0, abs_tol=1e-12):
                    mismatches += 1
                if a.escape:
                    snaps[i + 1] = copy.deepcopy(p)
        snapshots[ep] = snaps
    return mismatches, snapshots


def segments(episodes):
    out = []
    for ep, rows in episodes.items():
        start = 0
        for i, row in enumerate(rows):
            if row['action']['escape'] and row['neural']['brain_stepped']:
                out.append((ep, start, i))
                start = i + 1
        if start < len(rows):
            out.append((ep, start, None))
    return out


DECODER_STATE = ('threshold', 'fast_threshold', 'persistence_samples', 'dual_path',
                 'sustained_window_samples', '_window', '_streak', '_channel',
                 'stat', 'theta', 'fast', 'guard_spike', '_value', '_spiked')


def synced(spec, snapshot, rows, start):
    p = make(spec)
    state = {k: copy.deepcopy(v) for k, v in snapshot.__dict__.items() if k not in DECODER_STATE}
    p.__dict__.update(state)
    # Every decoder's evidence is empty at a segment start (reset or just after an
    # escape); only the spike deconvolution needs the previous trace sample.
    if isinstance(p, EvidencePolicy):
        p.stat.reset()
        p.stat._prev_total = rows[start - 1]['neural']['dnp01_total'] if start > 0 else 0.0
    elif p.sustained_window_samples is not None:
        p._window.clear()
    p._streak = 0
    return p


def human_segments(spec, episodes, snapshots):
    out = []
    for ep, a, e in segments(episodes):
        rows = episodes[ep]
        p = synced(spec, snapshots[ep][a], rows, a)
        stop = e if e is not None else len(rows) - 1
        fire = None
        for i in range(a, stop + 1):
            if rows[i]['neural']['brain_stepped'] and p.decide(motor_of(rows[i])).escape:
                fire = (i, p.criterion_diagnostics()['escape_trigger_channel'])
                break
        out.append({'episode': ep, 'start': a, 'recorded_escape': e,
                    'fire': None if fire is None else fire[0],
                    'channel': None if fire is None else fire[1]})
    return out


def bout_onset(rows, spk, e, gap=BOUT_GAP_TICKS, floor=0):
    """Offline: start of the visual/neural bout that ends at escape index e.

    encoder onset: first drive > 0 after the last run of >= gap drive-free ticks;
    neural onset: first DNp01 spike after the last run of >= gap spike-free ticks.
    """
    def onset(active):
        i, quiet = e, 0
        first = None
        while i >= floor:
            if active(i):
                first, quiet = i, 0
            else:
                quiet += 1
                if quiet >= gap and first is not None:
                    break
            i -= 1
        return first
    return (onset(lambda i: drive(rows[i]) > 0), onset(lambda i: spk[i] > 0))


def human_events(episodes, manifest, strikes):
    """Offline timeline of every recorded escape and every strike."""
    spk = {ep: row_spikes(rows) for ep, rows in episodes.items()}
    escapes = []
    for ep, a, e in segments(episodes):
        if e is None:
            continue
        rows = episodes[ep]
        enc0, neu0 = bout_onset(rows, spk[ep], e, floor=a)
        j = e + 1
        moved = None
        while j < len(rows):
            if math.hypot(rows[j]['fly']['x'] - rows[e]['fly']['x'],
                          rows[j]['fly']['y'] - rows[e]['fly']['y']) >= BODY_LENGTH_UNITS:
                moved = j
                break
            j += 1
        prev_speed = rows[e - 1]['fly']['speed'] if e > 0 else 0.0
        escapes.append({
            'episode': ep, 'segment_start': a, 'escape': e,
            'time_s': rows[e]['session_simulation_time'],
            'lifecycle_mode_before': rows[e - 1]['lifecycle']['mode'] if e > 0 else None,
            'lifecycle_mode_at': rows[e]['lifecycle']['mode'],
            'encoder_bout_onset': enc0, 'neural_bout_onset': neu0,
            'strike_active_or_commit': rows[e]['swatter']['phase'],
            'distance_at_escape': distance(rows[e]),
            'theta_dot_at_escape': rows[e]['retina']['theta_dot'],
            'fly_speed_before': prev_speed, 'fly_speed_at_escape_row': rows[e]['fly']['speed'],
            'ticks_to_one_body_length_displacement': None if moved is None else moved - e})
    strike_rows = []
    for s in strikes:
        rows = episodes[s['episode']]
        idx = {r['tick']: k for k, r in enumerate(rows)}
        c, r = idx[s['start_tick']], idx[s['resolved_tick']]
        esc = idx.get(s['escape_tick']) if s.get('escape_tick') is not None else None
        onset = idx.get(s['threat_onset_tick']) if s.get('threat_onset_tick') is not None else None
        strike_rows.append({'episode': s['episode'], 'click': c, 'resolved': r,
                            'recorded_escape': esc, 'escape_preexisting': s.get('escape_preexisting'),
                            'recorded_threat_onset': onset, 'outcome': s['outcome']})
    return escapes, strike_rows


def human_escape_summary(escapes):
    """Recorded-escape timing chain in ticks (offline bout onsets; see bout_onset)."""
    out = {}
    for x in escapes:
        key = 'strike' if x['strike_active_or_commit'] in ('commit', 'fast_swing', 'active_contact')             else 'hover_or_approach'
        c = out.setdefault(key, {'encoder_to_neural_onset': [], 'neural_onset_to_escape': [],
                                 'encoder_onset_to_escape': []})
        if x['encoder_bout_onset'] is not None and x['neural_bout_onset'] is not None:
            c['encoder_to_neural_onset'].append(x['neural_bout_onset'] - x['encoder_bout_onset'])
        if x['neural_bout_onset'] is not None:
            c['neural_onset_to_escape'].append(x['escape'] - x['neural_bout_onset'])
        if x['encoder_bout_onset'] is not None:
            c['encoder_onset_to_escape'].append(x['escape'] - x['encoder_bout_onset'])
    return {k: {kk: {'n': len(v), 'median_s': float(np.median(v)) * DT if v else None,
                     'p90_s': float(np.percentile(v, 90)) * DT if v else None}
                for kk, v in c.items()} for k, c in out.items()}


def motor_latency(escapes):
    ok = [x for x in escapes if x['ticks_to_one_body_length_displacement'] is not None]
    by = {}
    for x in ok:
        key = 'perched' if x['lifecycle_mode_before'] == 'PERCHED' else 'airborne'
        by.setdefault(key, []).append(x['ticks_to_one_body_length_displacement'])
    return {k: {'n': len(v), 'median_ticks': float(np.median(v)), 'max_ticks': int(max(v)),
                'impulse_applied_on_escape_tick': True} for k, v in by.items()}


def slow_close(episodes, rows_ep):
    rows = rows_ep
    idx = {r['tick']: k for k, r in enumerate(rows)}
    a, b = idx[SLOW_CLOSE['first_tick']], idx[SLOW_CLOSE['last_tick']]
    spk = row_spikes(rows)
    d = [distance(rows[i]) for i in range(a, b + 1)]
    closest = a + int(np.argmin(d))
    # Final loom reversal: first tick after the interval whose theta_dot turns negative.
    rev = next(i for i in range(b, len(rows)) if rows[i]['retina']['theta_dot'] < 0)
    first_evidence = next(i for i in range(a, b + 1) if drive(rows[i]) > 0)
    tot = [rows[i]['neural']['dnp01_total'] for i in range(a, b + 1)]
    return {'rows': (a, b), 'first_positive_encoder_drive': first_evidence,
            'closest_center_approach': closest, 'min_distance': float(min(d)),
            'median_distance': float(np.median(d)),
            'final_loom_reversal_theta_dot_negative': rev,
            'recorded_escape': next(i for i in range(a, len(rows)) if rows[i]['action']['escape']),
            'spike_ticks': [rows[i]['tick'] for i in range(a, rev + 1) for _ in range(spk[i])],
            'encoder_positive_ticks': sum(drive(rows[i]) > 0 for i in range(a, b + 1)),
            'dnp01_mean': float(np.mean(tot)), 'dnp01_max': float(max(tot)),
            'swatter_phase_at_reversal': rows[rev]['swatter']['phase']}


def far_perched_approach(episodes):
    """The strict-N2 session perched approach whose DNp01 peaked near 2.0557."""
    best = None
    for ep, rows in episodes.items():
        for i, r in enumerate(rows):
            if r['lifecycle']['attached'] and abs(r['neural']['dnp01_total'] - 2.0557) < 5e-4:
                best = (ep, i, r['neural']['dnp01_total'], distance(r))
    # Offline bout: contiguous rows around the peak with encoder drive or DNp01 > 0.3.
    rows = episodes[best[0]]

    def active(k):
        return drive(rows[k]) > 0 or rows[k]['neural']['dnp01_total'] > 0.3
    a = b = best[1]
    while a > 0 and active(a - 1):
        a -= 1
    while b < len(rows) - 1 and active(b + 1):
        b += 1
    return best + (a, b)


def classify_fire(rows, i, segment_start=None):
    """Offline context of a candidate firing: was there looming drive just before?"""
    recent = max(drive(rows[j]) for j in range(max(0, i - 5), i + 1))
    longer = max(drive(rows[j]) for j in range(max(0, i - 15), i + 1))
    return {'max_encoder_drive_last_6_ticks': recent, 'max_encoder_drive_last_16_ticks': longer,
            'ticks_after_segment_start': None if segment_start is None else i - segment_start,
            'distance': distance(rows[i]),
            'swatter_phase': rows[i]['swatter']['phase'],
            'lifecycle_mode': rows[i]['lifecycle']['mode']}


# ------------------------------------------------------------------------ main ---
def candidates(trials):
    """Reference decoders, then each family at its N0 selection-half threshold."""
    out = [('legacy 1.45 single-sample', {'kind': 'legacy'}),
           ('strict N2: FAST 2.20 OR 1.45 x3', {'kind': 'strict_n2'}),
           ('N2b: FAST 2.10 OR current-H + 3-of-5', {'kind': 'n2b'})]
    thetas = {}
    for s in STATS:
        theta, mx = select_theta(s, trials)
        if s[0] == 'mean':
            # Same decision as the window sum: mean >= theta / w  <=>  sum >= theta.
            theta = thetas[('sum', s[1])]['theta'] / s[1]
        thetas[s] = {'theta': theta, 'selection_half_max': mx}
        label = make_stat(s).name
        out.append(('%s >= %g' % (label, theta), {'kind': 'evidence', 'stat': s, 'theta': theta}))
        if s[0] != 'mean':
            out.append(('FAST 2.10 OR %s >= %g' % (label, theta),
                        {'kind': 'evidence', 'stat': s, 'theta': theta, 'fast': FAST}))
    return out, thetas


def summarise_human(spec_results, escapes_by_session, slow, far):
    out = {}
    for sess, segs in spec_results.items():
        leads, later, extra, per = [], 0, [], []
        for seg in segs:
            e, f = seg['recorded_escape'], seg['fire']
            if e is not None:
                per.append(None if f is None or f > e else e - f)
            if e is not None and f is not None and f <= e:
                leads.append(e - f)
            elif e is not None:
                later += 1
            if e is None and f is not None:
                extra.append(seg)
        out[sess] = {'segments_with_recorded_escape': sum(s['recorded_escape'] is not None for s in segs),
                     'fired_at_or_before_recorded_escape': len(leads),
                     'lead_ticks_median': float(np.median(leads)) if leads else None,
                     'lead_ticks_mean': float(np.mean(leads)) if leads else None,
                     'lead_ticks_max': int(max(leads)) if leads else None,
                     'later_than_recorded_escape': later,
                     'fires_in_segments_without_recorded_escape': len(extra),
                     'per_recorded_escape_lead_ticks': per}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'artifacts/m1_8_n3/evidence_integration.json')
    args = ap.parse_args()

    trials, continuous, raw = load_n0()
    data = np.load(N1 / 'trials.npz')
    meta = json.loads((N1 / 'trials_meta.json').read_text(encoding='utf-8'))

    result = {'label': 'M1.8-N3 neural evidence integration study; research only; runtime unchanged',
              'decay_per_tick': DECAY, 'selection_trials': SELECTION_TRIALS, 'margin': MARGIN,
              'inputs': {k: {'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha256(p)}
                         for k, p in (('n0_raw', N0 / 'raw.npz'), ('n0_continuous', N0 / 'continuous.npz'),
                                      ('n1_trials', N1 / 'trials.npz'), ('n1_meta', N1 / 'trials_meta.json'))}}
    for name, path in SESSIONS.items():
        result['inputs']['session_' + name] = {'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                                               'ticks_sha256': sha256(path / 'ticks.jsonl')}

    # ---- N0 structure and statistic envelopes
    result['n0_spike_structure'] = n0_spike_structure(trials)
    print('N0 spike rate %.3f Hz; max spikes per window %s' % (
        result['n0_spike_structure']['spike_rate_hz'],
        result['n0_spike_structure']['max_spikes_in_window']), flush=True)
    envelopes = {}
    for s in [('instant', 0), ('hcount', 5)] + STATS:
        envelopes[str(s)] = n0_stat_summary(trials, make_stat(s))
    result['n0_statistic_envelopes'] = envelopes

    # ---- candidates
    cands, thetas = candidates(trials)
    result['thresholds'] = {str(k): v for k, v in thetas.items()}

    # ---- human sessions
    human = {}
    for sess, path in SESSIONS.items():
        episodes, manifest = load_session(path)
        mism, snaps = reproduce(episodes, manifest)
        strikes = json.loads((path / 'strikes.json').read_text(encoding='utf-8'))
        escapes, strike_rows = human_events(episodes, manifest, strikes)
        human[sess] = {'episodes': episodes, 'snapshots': snaps, 'escapes': escapes,
                       'strikes': strike_rows, 'reproduction_mismatches': mism}
        print('session %s: %d episodes, %d recorded escapes, %d strikes, reproduction mismatches %d'
              % (sess, len(episodes), len(escapes), len(strike_rows), mism), flush=True)
    slow = slow_close(human['n2b']['episodes'], human['n2b']['episodes'][SLOW_CLOSE['episode']])
    far = far_perched_approach(human['strict_n2']['episodes'])
    result['slow_close'] = {k: v for k, v in slow.items() if k != 'rows'}
    result['far_perched_approach'] = {'episode': far[0], 'row': far[1], 'dnp01': far[2],
                                      'center_distance': far[3], 'bout_rows': [far[4], far[5]]}
    result['motor_latency'] = {s: motor_latency(h['escapes']) for s, h in human.items()}
    result['human_escape_chain'] = {s: human_escape_summary(h['escapes']) for s, h in human.items()}
    result['human_escapes'] = {s: h['escapes'] for s, h in human.items()}
    result['human_strikes'] = {s: h['strikes'] for s, h in human.items()}
    result['reproduction_mismatches'] = {s: h['reproduction_mismatches'] for s, h in human.items()}

    # ---- evaluate every candidate
    marks = n1_marks(data, meta)
    result['n1_marks'] = marks
    rows_out, per_trial_ref = {}, {}
    ep5 = human['n2b']['episodes'][SLOW_CLOSE['episode']]
    for name, spec in cands:
        n0 = n0_eval(spec, trials, continuous)
        summary, per_trial = n1(make(spec), data, meta)
        if spec['kind'] != 'evidence' or spec['stat'] in (('sum', 5), ('leaky', 100), ('spikes', 10)):
            per_trial_ref[name] = per_trial
        segs = {s: human_segments(spec, h['episodes'], h['snapshots']) for s, h in human.items()}
        # Slow-close interval: the segment that contains it.
        seg = next(x for x in segs['n2b'] if x['episode'] == SLOW_CLOSE['episode']
                   and x['start'] <= slow['rows'][0] and (x['recorded_escape'] or 10 ** 9) >= slow['rows'][0])
        sc_fire = seg['fire']
        sc = {'fire_row': sc_fire, 'fire_tick': None if sc_fire is None else ep5[sc_fire]['tick'],
              'channel': seg['channel'], 'segment_start_tick': ep5[seg['start']]['tick'],
              'context': None if sc_fire is None else classify_fire(ep5, sc_fire)}
        if sc_fire is not None:
            for key in ('first_positive_encoder_drive', 'closest_center_approach',
                        'final_loom_reversal_theta_dot_negative'):
                sc['ticks_after_' + key] = sc_fire - slow[key]
        # Far perched approach: does any firing land inside that perched stretch?
        fe, frow = far[0], far[1]
        fseg = next(x for x in segs['strict_n2'] if x['episode'] == fe and x['start'] <= frow
                    and (x['recorded_escape'] or 10 ** 9) >= frow)
        f_rows = human['strict_n2']['episodes'][fe]
        far_fire = {'segment_fire_row': fseg['fire'], 'peak_row': frow, 'bout_rows': [far[4], far[5]],
                    'fires_near_peak_while_perched': fseg['fire'] is not None
                    and far[4] <= fseg['fire'] <= far[5]
                    and bool(f_rows[fseg['fire']]['lifecycle']['attached'])}
        # Slow-close interval, clean start: evidence empty and no refractory at the first
        # interval tick, so only the interval's own neural evidence can fire. This is a
        # constructed counterfactual (it ignores the chase before tick 610), labelled so.
        a0, b0 = slow['rows']
        p = make(spec)
        if isinstance(p, EvidencePolicy):
            p.stat._prev_total = ep5[a0 - 1]['neural']['dnp01_total']
        clean = None
        for i in range(a0, slow['recorded_escape'] + 1):
            if p.decide(motor_of(ep5[i])).escape:
                clean = i
                break
        sc['clean_start_fire_tick'] = None if clean is None else ep5[clean]['tick']
        if clean is not None:
            for key in ('first_positive_encoder_drive', 'closest_center_approach',
                        'final_loom_reversal_theta_dot_negative'):
                sc['clean_start_ticks_after_' + key] = clean - slow[key]
        # Strikes: latency from click to first firing (exact) in the click's segment.
        strikes_eval = {}
        for sess, h in human.items():
            lat = []
            for st in h['strikes']:
                sg = next(x for x in segs[sess] if x['episode'] == st['episode'] and x['start'] <= st['click']
                          and (x['recorded_escape'] is None or x['recorded_escape'] >= st['click']))
                if st['escape_preexisting']:
                    continue
                if sg['fire'] is not None and st['click'] <= sg['fire'] <= st['resolved']:
                    lat.append({'latency_s': (sg['fire'] - st['click']) * DT, 'exact': True})
                elif sg['fire'] is not None and sg['fire'] < st['click']:
                    lat.append({'latency_s': (sg['fire'] - st['click']) * DT, 'exact': True,
                                'note': 'fires before click (hover approach)'})
                else:
                    lat.append({'latency_s': None, 'exact': sg['recorded_escape'] is None
                                or sg['recorded_escape'] > st['resolved']})
            strikes_eval[sess] = lat
        # Extra fires relative to recorded (segments without recorded escape), with context.
        extra = []
        for sess, sg in segs.items():
            for x in sg:
                if x['fire'] is not None and (x['recorded_escape'] is None or x['fire'] < x['recorded_escape']):
                    rows = human[sess]['episodes'][x['episode']]
                    ctx = classify_fire(rows, x['fire'], x['start'])
                    if ctx['max_encoder_drive_last_6_ticks'] == 0:
                        extra.append({'session': sess, 'episode': x['episode'], 'row': x['fire'], **ctx})
        entry = {'spec': {k: (list(v) if isinstance(v, tuple) else v) for k, v in spec.items()},
                 'n0': {k: {kk: v[kk] for kk in ('ticks', 'minutes', 'policy_firings', 'by_channel',
                                                 'upper95_one_sided_per_minute')} for k, v in n0.items()},
                 'n1': summary, 'human': summarise_human(segs, None, slow, far),
                 'human_strikes': strikes_eval, 'slow_close': sc,
                 'far_perched_approach_fires': far_fire,
                 'human_fires_without_recent_encoder_drive': extra}
        rows_out[name] = entry
        s, m = summary['strong_direct'], summary['medium_committed']
        print('%-62s N0 %2d (held %d, cont %d) up95 %.3f | S %2d/60 %.2f/%.2f | M %2d/60 %.2f/%.2f | '
              'w %2d g %2d a %2d | slow %s (rev %s) clean %s | far %s | h-lead %s | nodrive %d' % (
                  name[:62], n0['full']['policy_firings'], n0['held_out']['policy_firings'],
                  n0['continuous']['policy_firings'], n0['full']['upper95_one_sided_per_minute'],
                  s['fired_in_window'], s['median_latency_from_click_s'] or -1, s['p95_latency_from_click_s'] or -1,
                  m['fired_in_window'], m['median_latency_from_click_s'] or -1, m['p95_latency_from_click_s'] or -1,
                  summary['weak_approach']['fired_in_window'], summary['glancing_pass']['fired_in_window'],
                  summary['aborted_approach']['fired_in_window'], sc['fire_tick'],
                  sc.get('ticks_after_final_loom_reversal_theta_dot_negative'),
                  sc['clean_start_fire_tick'], far_fire['fires_near_peak_while_perched'],
                  entry['human']['n2b']['lead_ticks_median'], len(extra)), flush=True)
    result['candidates'] = rows_out
    result['n1_latency_decomposition'] = n1_latency_table(marks, per_trial_ref)

    # ---- distributions: per-class peaks versus the N0 maximum of each statistic
    dist = {}
    for s in [('instant', 0), ('hcount', 5), ('sum', 5), ('sum', 10), ('leaky', 100), ('leaky', 200),
              ('spikes', 5), ('spikes', 10), ('spikes', 20)]:
        mx = envelopes[str(s)]['max']
        d = {'n0_max': mx, 'n1': n1_distributions(data, meta, s, mx)}
        # Human: slow-close interval and far perched approach.
        v = series(make_stat(s), [r['neural']['dnp01_total'] for r in ep5])
        a, b = slow['rows']
        over = np.flatnonzero(v[a:slow['final_loom_reversal_theta_dot_negative'] + 1] > mx)
        d['slow_close_peak_before_reversal'] = float(v[a:slow['final_loom_reversal_theta_dot_negative']].max())
        d['slow_close_first_exceed_tick'] = None if not over.size else ep5[a + int(over[0])]['tick']
        f_rows = human['strict_n2']['episodes'][far[0]]
        fv = series(make_stat(s), [r['neural']['dnp01_total'] for r in f_rows])
        d['far_perched_peak_near'] = float(fv[max(0, far[1] - 10):far[1] + 10].max())
        dist[str(s)] = d
    result['distributions'] = dist

    # ---- threshold sweep for the integrated families: margin to the N0 envelope
    sweep = {}
    for s in [('sum', 5), ('sum', 10), ('leaky', 100), ('leaky', 200), ('spikes', 10), ('spikes', 20)]:
        theta0 = thetas[s]['theta']
        rows = []
        for f in (1.0, 0.95, 0.9, 0.85, 0.8):
            th = theta0 * f if s[0] != 'spikes' else theta0 - (0 if f == 1.0 else 1 if f >= 0.9 else 2)
            if s[0] == 'spikes' and f in (0.95, 0.85):
                continue
            spec = {'kind': 'evidence', 'stat': s, 'theta': th, 'fast': FAST}
            n0 = no_loom(make(spec), trials, 'full')
            summ, _ = n1(make(spec), data, meta)
            segs = human_segments(spec, {5: ep5}, {5: human['n2b']['snapshots'][5]})
            sg = next(x for x in segs if x['start'] <= slow['rows'][0]
                      and (x['recorded_escape'] or 10 ** 9) >= slow['rows'][0])
            rows.append({'theta': th, 'n0_firings': n0['policy_firings'],
                         'n0_upper95_per_min': n0['upper95_one_sided_per_minute'],
                         'medium_median_s': summ['medium_committed']['median_latency_from_click_s'],
                         'strong_median_s': summ['strong_direct']['median_latency_from_click_s'],
                         'weak_fired': summ['weak_approach']['fired_in_window'],
                         'slow_close_fire_tick': None if sg['fire'] is None else ep5[sg['fire']]['tick']})
        sweep[str(s)] = rows
        print('sweep', s, [(round(r['theta'], 3), r['n0_firings'], r['medium_median_s'], r['slow_close_fire_tick'])
                           for r in rows], flush=True)
    result['dual_threshold_sweep'] = sweep

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, default=str) + '\n', encoding='utf-8')
    print('written', args.out)


if __name__ == '__main__':
    main()
