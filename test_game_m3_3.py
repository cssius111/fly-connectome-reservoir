"""M3.3: the same_side_doublet_v1 escape decoder (game/M3_3_ESCAPE_DECISION_DESIGN.md, V7).

Unit tests inject MotorState directly. The decoder escapes only when one DNp01 side produces
two inferred spikes at most 2 samples (40 ms) apart; no summed path exists.
"""
import copy
import os
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.action import FixedEscapePolicy
from game.session import DOUBLET_DECODER, doublet_window_samples, escape_decoder_spec, load_config
from test_game_n4b1c_decoder import DECAY, DT, ROOT, feed, fired, lateral_policy, traces

ROOM = load_config(ROOT/'game_room_config.json')
DOUBLET = {'kind': DOUBLET_DECODER, 'alert_reference_threshold': 1.45, 'doublet_window_ms': 40,
           'required_spikes': 2}


def doublet_policy():
    return FixedEscapePolicy(1.45, .4, DT, lateral_window_samples=2, trace_decay=DECAY,
                             summed_paths=False)


def with_decoder(block):
    c = copy.deepcopy(ROOM)
    c['policy']['escape_decoder'] = block
    return c


class TestSpecification(unittest.TestCase):
    def test_the_block_is_validated(self):
        spec = escape_decoder_spec(with_decoder(DOUBLET))
        self.assertEqual(spec, {**DOUBLET, 'doublet_window_ms': 40.0, 'alert_reference_threshold': 1.45})
        self.assertEqual(doublet_window_samples(spec, ROOM), 2)
        bad = [dict(DOUBLET, required_spikes=3), dict(DOUBLET, doublet_window_ms=0),
               dict(DOUBLET, alert_reference_threshold=-1), dict(DOUBLET, summed_fast_threshold=2.1)]
        missing = dict(DOUBLET); del missing['doublet_window_ms']
        bad.append(missing)
        for block in bad:
            with self.assertRaises(ValueError):
                escape_decoder_spec(with_decoder(block))
        with self.assertRaises(ValueError):
            doublet_window_samples(dict(spec, doublet_window_ms=30.0), ROOM)

    def test_the_policy_rejects_summed_criteria_without_summed_paths(self):
        with self.assertRaises(ValueError):
            FixedEscapePolicy(1.45, .4, DT, fast_threshold=2.1, persistence_samples=3,
                              sustained_window_samples=5, lateral_window_samples=2,
                              trace_decay=DECAY, summed_paths=False)
        with self.assertRaises(ValueError):
            FixedEscapePolicy(1.45, .4, DT, summed_paths=False)
        with self.assertRaises(ValueError):
            FixedEscapePolicy(1.45, .4, DT, lateral_window_samples=2, trace_decay=DECAY)


class TestDoubletRule(unittest.TestCase):
    def test_a_same_side_doublet_within_two_samples_fires(self):
        for gap in (1, 2):
            p = doublet_policy()
            self.assertEqual(fired(feed(p, traces({10, 10 + gap}, set(), 30))), [10 + gap])
            self.assertEqual(p.criterion_diagnostics()['escape_decoder'], 'same_side_doublet_v1')

    def test_a_wider_gap_or_opposite_sides_do_not_fire(self):
        self.assertEqual(fired(feed(doublet_policy(), traces({10, 13}, set(), 30))), [])
        self.assertEqual(fired(feed(doublet_policy(), traces({10}, {11}, 30))), [])
        self.assertEqual(fired(feed(doublet_policy(), traces(set(), {4, 6}, 30))), [6])

    def test_no_summed_path_fires(self):
        # Alternating sides every tick: the summed trace exceeds 2.1, but no side has a doublet.
        left, right = set(range(10, 40, 3)), set(range(11, 40, 3))
        pairs = traces(left, right, 45)
        self.assertGreater(max(l + r for l, r in pairs), 2.1)
        self.assertEqual(fired(feed(doublet_policy(), pairs)), [])
        self.assertTrue(fired(feed(lateral_policy(), pairs)), 'N4B1C fires on the same input')

    def test_refractory_and_memory_clearing(self):
        # Escape at 12; the doublet at 20-21 falls inside the 0.4 s refractory and does not
        # fire; the next doublet after it does.
        pairs = traces({10, 12, 20, 21, 31, 33}, set(), 45)
        self.assertEqual(fired(feed(doublet_policy(), pairs)), [12, 33])
        # A spike before the escape never pairs with one after the refractory.
        pairs = traces({10, 12, 32, 40}, set(), 45)
        self.assertEqual(fired(feed(doublet_policy(), pairs)), [12])
        # Spikes inside the refractory period (ticks 13-32) still update the history.
        pairs = traces({10, 12, 31, 32}, set(), 45)
        self.assertEqual(fired(feed(doublet_policy(), pairs)), [12])
        pairs = traces({10, 12, 33, 34}, set(), 45)
        self.assertEqual(fired(feed(doublet_policy(), pairs)), [12, 34])

    def test_escape_direction_and_alert_logic_are_unchanged(self):
        pairs = traces({10, 11}, set(), 20)
        a = [x for x in feed(doublet_policy(), pairs) if x.escape][0]
        b = [x for x in feed(lateral_policy(), pairs) if x.escape][0]
        self.assertEqual((a.lateral, a.forward, a.strength, a.turn), (b.lateral, b.forward, b.strength, b.turn))


if __name__ == '__main__':
    unittest.main()
