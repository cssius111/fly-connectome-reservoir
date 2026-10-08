"""M1.8-N4B8 research: frozen candidate set and measurement plan (long-mode pathway feasibility).

Research only. Nothing here is imported by the runtime. No decoder, threshold, window,
weighted combination, motion gate or geometry gate is defined for runtime use. The candidate
set is fixed from the primary literature BEFORE any new N4B8 simulation is evaluated;
`tools/n4b8_long_mode.py freeze` records this module's sha256 and every simulation mode
refuses to run if it changes.

Evidence classes used throughout: A directly demonstrated biology; B anatomical / connectomic
inference; C simulator engineering interpretation. "Responds to looming" is never equated
with "causes escape".
"""
from __future__ import annotations

# ----------------------------------------------------------------- candidate set ---
CANDIDATES = {
    'DNp01': {
        'role': 'reference (accepted fast pathway)',
        'literature': 'Giant fiber. A: GF spike timing relative to parallel descending pathways selects '
                      'short- versus long-mode takeoff; GF is essential for short-mode takeoff (von Reyn et '
                      'al. 2014, Nat Neurosci 17:962). A: LPLC2 (size) and LC4 (velocity) synapse onto the GF '
                      'and their summation shapes its looming response (von Reyn et al. 2017, Neuron; Ache et '
                      'al. 2019, Curr Biol).'},
    'DNp04': {
        'role': 'reference baseline (known non-specific in free flight; N4B2 / N4B3); not reopened',
        'literature': 'A (dissertation-level): one of the LC4-glomerulus DNs ("LC4DNs"); optogenetic '
                      'activation elicits long-duration takeoffs; co-activation with DNp02 gives backward '
                      'escapes (Peek 2018, PhD dissertation, University of Chicago). B: innervates the whole '
                      'LC4 glomerulus (Namiki et al. 2018, eLife).'},
    'DNp02': {
        'role': 'long-mode takeoff candidate',
        'literature': 'A: postsynaptic to LC4; LC4 synaptic-number gradients onto DNp02 and DNp11 convert '
                      'looming location into opposite takeoff directions (Dombrovski et al. 2023, Nature '
                      '613:534). A (dissertation-level): LC4DN activation can evoke long-mode escapes distinct '
                      'from GF short-mode escapes (Peek 2018). B: DNp02 receives LC4 but not LPLC2 synapses '
                      '(Moreno-Sanchez et al. 2024, bioRxiv).'},
    'DNp11': {
        'role': 'long-mode takeoff candidate',
        'literature': 'A: LC4 target promoting forward takeoff, opposite to DNp02 (Dombrovski et al. 2023). '
                      'A (dissertation-level): activation elicits long-duration, forward takeoffs (Peek 2018).'},
    'DNp03': {
        'role': 'flight-evasion (saccade) candidate',
        'literature': 'A: responds to ipsilateral looming in a flight-state-dependent manner; sustained '
                      'post-stimulus activity best predicts evasive flight saccades (Buchsbaum et al. 2025, '
                      'Curr Biol). A/B: direct input from LPLC1, LC4, LPLC4, LC22 and LC23 VPNs, octopamine '
                      'mimics flight, outputs to wing and neck motor neurons (Croke et al. 2025, Curr Biol).'},
    'DNp07': {
        'role': 'landing candidate (self-motion toward an object)',
        'literature': 'A: controls visually evoked landing; visual responses are severely attenuated when '
                      'not flying; octopamine mimics flight for DNp07 (Ache et al. 2019, Nat Neurosci '
                      '22:1132). The paper states that an approaching predator and self-motion toward an '
                      'object generate similar looming on the retina.'},
    'DNp10': {
        'role': 'landing candidate (self-motion toward an object)',
        'literature': 'A: controls visually evoked landing; flight gating is octopamine-independent and '
                      'probably from flight-motor feedback (Ache et al. 2019).'},
}
REFERENCES = ('DNp01', 'DNp04')
NON_REFERENCE = ('DNp02', 'DNp11', 'DNp03', 'DNp07', 'DNp10')
EXCLUDED = {
    'DNp06': 'looming-responsive (Moreno-Sanchez et al. 2024) but no demonstrated takeoff / avoidance role',
    'other LC4-glomerulus DNs': 'no specific literature role for slow approach; not searched (no unrestricted DN search)',
    'N4B2 comparison DNs (DNg40, DNp05, DNpe056, DNp103, DNpe025)': 'already characterised in N4B2; no literature '
                                                                   'role for gradual looming',
}

# ----------------------------------------------------------------- data ---
DATA = {
    'controlled': 'the 15 frozen N4B6 trajectories (tools/n4b6_protocol.py sha256 01d91ab8...), N4B6 seeds '
                  '500001-500048, re-simulated with every candidate cell recorded. DNp01 / DNp04 spikes must '
                  'reproduce the stored N4B6 records exactly.',
    'mirror': 'self-motion mirrors of A2 (130 units/s) and B1 (300 units/s): the paddle is parked at hover, '
              'facing the fly as in the approach, and the fly is translated so that the paddle-fly relative '
              'position equals the recorded N4B6 approach at every tick (heading 0). Same 48 seeds. Tests '
              'whether external and self-generated approach deliver different brain input.',
    'n1': 'N1 strong_direct and medium_committed (60 each), N1 seeds and N1 script, accepted config (G3).',
    'free_flight': 'no-player ROOM closed loop under the unchanged accepted runtime (N4B1C live), seeds '
                   '7601-7640 (40 runs x 3 min = 120 min; the N4B7 reference runs). DNp01 traces must '
                   'reproduce the stored N4B7 reference rows exactly.',
    'human': 'both recorded human sessions, open-loop G3 recomputation (N4B5R method), noise offset 0.',
}

# ----------------------------------------------------------------- metrics (descriptive) ---
WINDOW = 50                  # 1.0 s count window, as in N4B6 section 6.3 (descriptive only)
MARGIN = 13                  # the window ends 0.26 s before closest approach (N4B6 response margin)
SLOW_130 = ('A2_frontal_slow', 'C2_oblique_slow_left', 'C3_lateral_slow_close')
SELF_APPROACH = {'range_rate_max': -80.0, 'horizontal_min': 250.0, 'horizontal_max': 800.0,
                 'theta_dot_band': (0.05, 0.12)}
METRICS = (
    'All per cell on the side ipsilateral to the stimulus (the Retina azimuth sign), spikes read directly '
    'from the brain step. (1) Baseline rate: stationary pre-holds and F1. (2) Controlled response: spike '
    'count in the 1 s window ending 0.26 s before closest approach (approach / abort trajectories), in the '
    '1 s after motion end for F3 (stop rotation), and in 1 s windows for F1 / F2; separability from '
    'stationary baseline 1 s windows by ROC AUC. (3) N1: first ipsilateral spike after the click and count '
    'in the 0.3 s after it. (4) Free flight: 1 s window counts on both sides; the rate of episodes (window '
    'exceedances separated by >= 1 s) at the level that captures 50 % and 90 % of the 130 units/s approach '
    'windows (matched sensitivity; a signal-detection characterisation, not a decoder). (5) Self-approach '
    'windows in free flight (airborne, range rate <= -80 units/s, horizontal 250-800, mean theta_dot 0.05-0.12 '
    'rad/s over the window): AUC of external 130 units/s windows versus these windows. (6) Mirror test: '
    'Retina and spike identity between external approach and its self-motion mirror. (7) Human sessions: '
    'counts in hover / chase bouts and in strike windows.')

OUTCOME_RULE = (
    'A. VIABLE BIOLOGICAL LONG-MODE SIGNAL: at least one non-reference candidate (DNp02, DNp11, DNp03, DNp07, '
    'DNp10) (i) separates the 130 units/s window from stationary baseline with AUC >= 0.90 in at least two of '
    'A2, C2, C3; (ii) at the level capturing 50 % of the 130 units/s windows, has a free-flight episode rate '
    'at most half of both DNp01 and DNp04 at their own matched levels, AND separates external 130 units/s '
    'windows from matched free-flight self-approach windows with AUC >= 0.80; and (iii) fires its first '
    'ipsilateral spike within 0.2 s of the click in >= 90 % of N1 strong_direct trials or, if it is not a '
    'fast-threat cell, responds to N1 strong / medium above baseline (AUC >= 0.90). '
    'B. SIGNAL EXISTS BUT IS NOT SELECTIVE: some non-reference candidate meets (i) but none meets (ii). '
    'C. NO USEFUL LONG-MODE SIGNAL: no non-reference candidate meets (i). '
    'The mirror test is reported with the outcome; if it shows identical brain input for external and '
    'self-generated approach, that is the structural explanation for B or C.')
