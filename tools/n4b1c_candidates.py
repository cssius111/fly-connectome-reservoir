"""M1.8-N4B1C research: frozen candidate definitions (combined lateral + summed DNp01).

Research only. This module defines the decoders compared in M1.8-N4B1C. Its sha256 is
recorded in artifacts/m1_8_n4b1c/frozen_candidates.json BEFORE the new N0 holdout is
generated, and every later step refuses to run if this file has changed. No production
runtime, configuration, calibration record or policy observation is modified.

It must be imported with the rejected-N2b archival worktree first on sys.path (see
tools/n4b1c_combined.py): the N2b summed path is the archived runtime FixedEscapePolicy
with the archived ROOM v15 decoder parameters, unchanged.

Candidates

1. legacy summed single-sample: DNp01 L+R >= 1.45 (ROOM config at 76806f0).
2. strict N2: FAST L+R >= 2.20 OR L+R >= 1.45 on 3 consecutive samples.
3. N2b: FAST L+R >= 2.10 OR (current L+R >= 1.45 AND >= 3 of the last 5 samples,
   current included, are >= 1.45). Archived runtime implementation.
4. Rule A alone: two inferred DNp01 spikes on the SAME side, the second at most 3 samples
   (60 ms) after the first (N4B1 frozen rule A_spike).
5. Rule B alone: the same with at most 4 samples (80 ms) (N4B1 frozen rule B_spike).
6. A OR N2b (primary).
7. B OR N2b.

Combined-decoder semantics (6 and 7)

* Inputs: dnp01_left and dnp01_right only (already in the policy observation). The summed
  path uses their sum exactly as the archived N2b runtime does; the lateral path uses each
  side separately.
* Lateral path: per side, the spike count of each sample is s_t = trace_t - 0.81873 *
  trace_{t-1} (flybrain.Trace, +1 per spike). A side qualifies on a sample that holds a new
  spike on that side while that same side's previous spike, after the last escape or reset,
  is at most `max_gap` samples earlier. A left spike followed by a right spike never
  qualifies.
* Summed path: the archived N2b rule, unchanged (FixedEscapePolicy._trigger_channel with
  fast_threshold 2.10, persistence 3, window 5, current sample must qualify).
* Escape when EITHER path qualifies on the current sample and the policy is not
  refractory. One shared 0.4 s (20-sample) refractory. The channel string lists every path
  that qualified on the firing sample, lateral first: e.g. "LATERAL_L", "FAST",
  "SUSTAINED", "LATERAL_R+FAST".
* Every sample, refractory samples included: the N2b 5-sample window and streak are
  updated (archived runtime semantics) and the lateral spike memory is updated.
* On an escape: the N2b window and streak are cleared (archived runtime), and the lateral
  last-spike memory of both sides is cleared, so spikes before an escape never pair with
  spikes after it. The per-side previous trace value used for spike inference is kept,
  because it is an observation, not evidence.
* On reset: all of the above plus the previous trace values (no spike is inferred on the
  first observed sample, whose predecessor is unknown) and all runtime policy state.
* Strength, escape side, steering, alert state and saccades: unchanged runtime code.
* No geometry, Retina, encoder, distance or contact value is read.
"""
from __future__ import annotations

DT = 0.02


def specs():
    return [
        {'key': 'legacy', 'name': 'legacy summed single-sample 1.45'},
        {'key': 'strict_n2', 'name': 'strict N2: FAST 2.20 OR 1.45 x3'},
        {'key': 'n2b', 'name': 'N2b: FAST 2.10 OR current-H + 3-of-5'},
        {'key': 'A', 'name': 'Rule A alone: same side twice within 60 ms', 'max_gap': 3},
        {'key': 'B', 'name': 'Rule B alone: same side twice within 80 ms', 'max_gap': 4},
        {'key': 'A_or_n2b', 'name': 'A OR N2b', 'max_gap': 3, 'combined': True},
        {'key': 'B_or_n2b', 'name': 'B OR N2b', 'max_gap': 4, 'combined': True},
    ]


def combined_class():
    from game.action import FixedEscapePolicy
    from tools import n4b1_lateral as L

    class CombinedPolicy(FixedEscapePolicy):
        """Research-only: archived N2b summed path OR a same-side DNp01 path."""

        def __init__(self, spec):
            self.spec = dict(spec, form='spike')
            base = L.fresh_base()          # archived runtime N2b (ROOM v15)
            if base.sustained_window_samples is None:
                raise RuntimeError('the archived N2b runtime is not on sys.path')
            super().__init__(base.threshold, 0.4, DT, fast_threshold=base.fast_threshold,
                             persistence_samples=base.persistence_samples,
                             sustained_window_samples=base.sustained_window_samples,
                             require_current_qualifying=True)
            L.copy_base_params(self, base)

        def reset(self):
            super().reset()
            self._prev = {'L': None, 'R': None}
            self._last = {'L': None, 'R': None}
            self._pair = {'L': None, 'R': None}
            self._now = {'L': False, 'R': False}
            self._sample = 0
            self._paths = []
            self.last_trigger = None

        def _observe(self, motor):
            for side, v in (('L', motor.dnp01_left), ('R', motor.dnp01_right)):
                prev = self._prev[side]
                spike = prev is not None and v - L.DECAY * prev >= 0.5
                self._now[side] = False
                if spike:
                    last = self._last[side]
                    self._now[side] = last is not None and self._sample - last <= self.spec['max_gap']
                    if self._now[side]:
                        self._pair[side] = (last, self._sample)
                    self._last[side] = self._sample
                self._prev[side] = v

        def _trigger_channel(self, total):
            paths = []
            lateral = [s for s in 'LR' if self._now[s]]
            if lateral:
                paths.append('LATERAL_' + ''.join(lateral))
            summed = super()._trigger_channel(total)      # archived N2b: FAST / SUSTAINED / None
            if summed is not None:
                paths.append(summed)
            self._paths = paths
            return '+'.join(paths) if paths else None

        def decide(self, motor):
            self._observe(motor)
            action = super().decide(motor)
            if action.escape:
                self.last_trigger = {'sample': self._sample, 'channel': self._channel,
                                     'paths': list(self._paths),
                                     'pair': {s: self._pair[s] for s in 'LR' if self._now[s]}}
                self._last = {'L': None, 'R': None}
            self._sample += 1
            return action

    return CombinedPolicy


def factories():
    from tools import n4b1_lateral as L
    refs = L.reference_policies()
    lateral = L.lateral_class()
    combined = combined_class()
    out = {}
    for s in specs():
        if s['key'] == 'legacy':
            out[s['name']] = refs['legacy summed single-sample 1.45']
        elif s['key'] == 'strict_n2':
            out[s['name']] = refs['strict N2: FAST 2.20 OR 1.45 x3']
        elif s['key'] == 'n2b':
            out[s['name']] = refs['N2b: FAST 2.10 OR current-H + 3-of-5']
        elif s.get('combined'):
            out[s['name']] = (lambda s=s: combined(s))
        else:
            out[s['name']] = (lambda s=s: lateral({'key': s['key'] + '_spike', 'form': 'spike',
                                                   'max_gap': s['max_gap']}))
    return out
