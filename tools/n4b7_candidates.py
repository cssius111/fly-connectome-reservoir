"""M1.8-N4B7 research: preregistered long-timescale DNp01 readout candidates.

Research only. Nothing here is imported by the runtime and no readout defined here is a policy
input of the accepted game. `tools/n4b7_long_readout.py freeze` records this module's sha256
before any fresh holdout seed is simulated; the holdout modes refuse to run if it changes.

Candidate family (kept deliberately small; fixed before any fresh holdout exists):

* L1 (primary): same-side >= 4 inferred DNp01 spikes within the trailing 1.0 s (50 samples).
  Motivation (development evidence, N4B6 section 6.3): in the stored 840-min N0 record a
  per-side count of >= 4 in 1 s occurs in 11 of 4.86 million sliding windows, while 130
  units/s controlled approaches reach it in 65-75 % of seeds in the 1 s window ending 0.26 s
  before closest approach.
* L2 (robustness comparison): same-side >= 5 spikes within 1.0 s. The development N0 maximum
  per side in any 1 s window is 4; L2 is the smallest rule that is outside that envelope.
* L3 (latency comparison): same-side >= 4 spikes within 0.8 s (40 samples). It asks whether
  the same count in a shorter window keeps the N0 margin with less delay.

The decision (section DECISION_RULE) is taken on L1 alone. L2 and L3 are reported only.

All parameters are Class C simulator-derived engineering values. They are not biological
constants and are not a claim that a fly counts DNp01 spikes.
"""
from __future__ import annotations

from collections import deque

DT = 0.02

FAMILY = {
    'L1': {'k': 4, 'window_samples': 50, 'role': 'primary'},
    'L2': {'k': 5, 'window_samples': 50, 'role': 'robustness comparison (reported only)'},
    'L3': {'k': 4, 'window_samples': 40, 'role': 'latency comparison (reported only)'},
}
PRIMARY = 'L1'

SEMANTICS = (
    'LONG_DNP01 path, evaluated beside the frozen N4B1C decoder (lateral_dual_path_v1), whose '
    'LATERAL, FAST and SUSTAINED paths, thresholds, refractory and motor output are unchanged. '
    '(1) Spike inference: exactly the N4B1C lateral inference, per side from that side\'s own '
    'DNp01 trace: spike_t = trace_t - trace_decay * trace_{t-1} >= 0.5; no spike is inferred on '
    'the first sample after reset. (2) Sides are independent: a left spike never counts toward '
    'the right window and vice versa. (3) Trailing window: the window at sample t holds the '
    'samples t - W + 1 .. t inclusive (W = window_samples), i.e. exactly W samples. (4) The path '
    'qualifies on sample t for a side when that side has an inferred spike ON sample t and at '
    'least k inferred spikes in its window (the current spike included). The qualifying spike '
    'must be current, as for LATERAL, so stale evidence cannot fire at refractory expiry. '
    '(5) Evidence accumulates on every sample, refractory samples included. (6) The path cannot '
    'fire during the shared 0.4 s refractory. (7) When an escape fires on any path, both sides\' '
    'long-window spike memories are cleared (as the lateral memory is), so spikes before an '
    'escape never count after it. Reset clears them too. (8) Diagnostic precedence: LATERAL, FAST, '
    'SUSTAINED, then LONG; the motor output does not depend on which path fired. (9) The path '
    'reads only the DNp01 traces already in MotorState: no geometry, Retina, encoder output, '
    'paddle coordinate or world distance can gate it.')


def make_policy(config, rule, mode='combined', root=None):
    """Build the accepted runtime policy from `config` and attach a LONG_DNP01 path.

    mode: 'combined' (N4B1C OR LONG), 'long_only' (LONG alone; N4B1C paths disabled; the same
    refractory, clearing and motor output) or 'n4b1c' (the unchanged runtime policy).
    The caller must have put the accepted runtime worktree first on sys.path.
    """
    from game.session import build_policy
    from game.action import FixedEscapePolicy
    policy = build_policy(config, root)[0] if root is not None else build_policy(config)[0]
    if type(policy) is not FixedEscapePolicy or policy.lateral_window_samples is None:
        raise RuntimeError('expected the accepted N4B1C FixedEscapePolicy')
    if mode == 'n4b1c':
        return policy
    spec = FAMILY[rule]

    class LongDnp01Policy(FixedEscapePolicy):
        long_k = int(spec['k'])
        long_window = int(spec['window_samples'])
        long_mode = mode
        long_rule = rule

        def reset(self):
            super().reset()
            self._long_spikes = (deque(), deque())
            self._long_prev = [None, None]
            self._long_now = []                 # [(side, count)] qualifying on this sample
            self.long_last_trigger = None       # (sample, sides, counts) of the last LONG firing

        def _observe_lateral(self, motor, sample):
            super()._observe_lateral(motor, sample)
            self._long_now = []
            for side, value in ((0, motor.dnp01_left), (1, motor.dnp01_right)):
                prev = self._long_prev[side]
                spike = prev is not None and value - self.trace_decay * prev >= 0.5
                q = self._long_spikes[side]
                if spike:
                    q.append(sample)
                while q and q[0] <= sample - self.long_window:
                    q.popleft()
                if spike and len(q) >= self.long_k:
                    self._long_now.append(('LR'[side], len(q)))
                self._long_prev[side] = float(value)

        def _trigger_channel(self, total):
            if self.long_mode == 'combined':
                super()._trigger_channel(total)
                paths = [p for p in self._pending_paths.split('+') if p]
            else:
                paths = []
            if self._long_now:
                paths.append('LONG')
            self._pending_paths = '+'.join(paths)
            return paths[0] if paths else None

        def decide(self, motor):
            sample = self._sample_index
            action = super().decide(motor)
            if action.escape:
                if 'LONG' in self._trigger_paths.split('+'):
                    self.long_last_trigger = (sample, ''.join(s for s, _ in self._long_now),
                                              [c for _, c in self._long_now])
                for q in self._long_spikes:
                    q.clear()
            return action

    policy.__class__ = LongDnp01Policy
    policy.reset()
    return policy


# ----------------------------------------------------------------- data and seeds ---
DEVELOPMENT_DATA = (
    'Already inspected; used only to characterise the candidates: the stored fixed-fly N0 '
    'records (N4B2 chunks, 840 min, per-side DNp01 spikes); N4B6 controlled trajectories '
    '(seeds 500001-500048); both recorded human sessions (recorded traces, and the G3 open-loop '
    'recomputation over five noise realizations); the 83 N4B5R no-player ROOM free-flight runs '
    'under the accepted runtime (249 min, G3, per-tick DNp01 traces); N1 strong / medium '
    'committed strikes re-simulated under G3 (seeds as in N1).')

# Fresh holdout seeds. None overlaps a used range: N0 up to 440149 plus 4000-4149, N1
# 6000-10059, ROOM 7101-7440 and 101 / 255 / 4242, N4B6 500001-500048. New: 700001-700096,
# 800001-800720, 900001-900120 and ROOM 7601-7680.
HOLDOUT = {
    'fixed_fly_n0': {'seeds': (800001, 800720), 'ticks_per_trial': 1400,
                     'note': '720 trials x 28 s = 336 min; accepted ROOM config (v17), ecology off, '
                             'fly motion and collisions disabled, escape disabled (recording '
                             'policy); the paddle hovers stationary at a per-trial offset drawn from '
                             'numpy default_rng(seed): angle U(0, 2 pi), radius U(30, 170) units, '
                             'after the accepted settle period.'},
    'room_free_flight': {'seeds': (7601, 7680), 'ticks_per_run': 9000, 'numba_threads': 1,
                         'note': '80 runs x 3 min = 240 min, no player (paddle parked at (1920, 388.8)), '
                                 'accepted ROOM config, closed loop. Each seed is run twice: with the '
                                 'unchanged N4B1C policy (reference; L1-L3 evaluated in shadow on its '
                                 'traces) and with N4B1C OR L1 live (primary). Every escape of the live '
                                 'L1 run is re-run with that escape withheld for 2 s (category B '
                                 'counterfactual), as in N4B5R.'},
    'n1_committed': {'seeds': (900001, 900120),
                     'note': 'fresh fixed-fly committed strikes: seeds 900001-900060 strong_direct, '
                             '900061-900120 medium_committed, generated by the N1 script '
                             '(tools/loom_robustness_study.py make_script) with numpy default_rng(seed) '
                             'per trial, under the accepted ROOM config (G3), ecology off. Direct-strike '
                             'coverage is an escape from 0.4 s before the click to the end of the 1.8 s '
                             'trial; latency is measured from the click.'},
    'controlled_approach': {'seeds': (700001, 700096),
                            'note': 'the 15 frozen N4B6 trajectories, unchanged (tools/n4b6_protocol.py '
                                    'sha256 01d91ab8...), with 96 new brain-noise seeds each.'},
}

# ----------------------------------------------------------------- metrics ---
FREE_FLIGHT_CATEGORIES = (
    'Accepted N4B4 / N4B5R split, computed exactly as tools/n4b5r_runtime_validation.py '
    'room_summary: A no-drive (max encoder drive over the last 10 ticks < 1e-6); B inappropriate '
    '(the counterfactual with the escape withheld keeps the fly >= 310 units horizontally from '
    'the paddle for the next 75 ticks); C foreshortening-driven (apparent-size share of positive '
    'expansion >= 0.6 and elevation >= 60 deg); D genuine self-approach (range rate <= -40 '
    'units/s and size share < 0.3); otherwise mixed.')

# ----------------------------------------------------------------- decision ---
MATERIAL_POOLED_TIMELY = 0.70
MATERIAL_GAIN_OVER_N4B1C = 0.40
MATERIAL_PER_TRAJECTORY = 0.50
MATERIAL_MEDIAN_LEAD_S = 0.25
SLOW_130 = ('A2_frontal_slow', 'C2_oblique_slow_left', 'C3_lateral_slow_close')

DECISION_RULE = (
    'L1 (N4B1C OR L1) is recommended as a future runtime candidate only if ALL hold on fresh '
    'holdout data: '
    '(1) 130 units/s controlled approaches: pooled over A2, C2 and C3 (C1 is bit-identical to A2 '
    'by construction and is reported only), the combined timely-detection probability (trigger '
    'at or before closest approach) is >= 0.70 and at least 0.40 above N4B1C alone; each of A2, '
    'C2, C3 is >= 0.50; and the median lead before closest approach of the combined timely '
    'detections is >= 0.25 s. '
    '(2) Fixed-fly holdout: combined escape events over the >= 280-min N0 holdout have an exact '
    'one-sided 95 % Poisson upper bound < 0.1/min; the stationary / receding controls and '
    'pre-holds of the controlled holdout are also < 0.1/min at 95 %. '
    '(3) Free-flight holdout (N4B1C OR L1 live): category B and category A each < 0.1/min at 95 %. '
    '(4) Direct strikes are not damaged: in the fresh N1 strong / medium holdout, and (as '
    'development evidence, since fresh human strikes cannot be generated without a player) in N1 '
    '(G3, N1 seeds) and the G3 open-loop human replays (five noise realizations), coverage by the combined policy (an escape from 0.4 s '
    'before the click to strike resolution) is not below N4B1C alone and the median latency '
    'after the click is not more than 0.02 s later. '
    '(5) No pathological repetition: no fixed-fly or free-flight holdout run contains >= 3 '
    'LONG-path escapes within any 5 s. '
    '(6) The 50 units/s trajectory (A1) plays no role in the decision. '
    'If any condition fails, L1 is not recommended, nothing is tuned against the holdout, and the '
    'frozen alternatives (keep the runtime and document the limitation) remain in force.')
