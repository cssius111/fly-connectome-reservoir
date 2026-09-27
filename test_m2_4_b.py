"""M2.4-B blind A/B infrastructure: randomisation / commitments, blinding, metrics from unchanged tick events."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parent
_spec = importlib.util.spec_from_file_location('m2_4_b_blind_ab_test', ROOT / 'tools/m2_4_b_blind_ab.py')
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


class Randomisation(unittest.TestCase):
    def test_blocks_are_balanced_paired_and_short_runs(self):
        for k in range(20):
            rows = M.assignments(bytes([k]) * 32)
            self.assertEqual(len(rows), 2 * M.N_BLOCKS)
            self.assertEqual(sum(r['policy'] == 'A' for r in rows), M.N_BLOCKS)
            for b in range(1, M.N_BLOCKS + 1):
                blk = [r for r in rows if r['block'] == b]
                self.assertEqual(sorted(r['policy'] for r in blk), ['A', 'B'])
                self.assertEqual(len({r['world_seed'] for r in blk}), 1)
            seq = ''.join(r['policy'] for r in rows)
            self.assertNotIn('AAA', seq)
            self.assertNotIn('BBB', seq)

    def test_assignment_is_reproducible_from_the_key_and_commitments_bind_it(self):
        key = b'\x07' * 32
        self.assertEqual(M.assignments(key), M.assignments(key))
        r = M.assignments(key)[0]
        other = 'B' if r['policy'] == 'A' else 'A'
        self.assertNotEqual(M._commit(key, r['session'], r['policy']), M._commit(key, r['session'], other))

    def test_world_seeds_are_outside_all_m2_ranges(self):
        for b in range(1, M.N_BLOCKS + 1):
            s = M._world_seed(b)
            self.assertFalse(20_000_000 <= s < 30_000_000)
            self.assertFalse(3_000_000 <= s < 4_000_000)


class Metrics(unittest.TestCase):
    def test_strikes_hits_and_escapes_are_counted_from_tick_events(self):
        from game.session import Session, load_config
        cfg = load_config(ROOT / 'game_room_config.json')
        s = Session(cfg, root=ROOT, seed=41_999_001, mode='play')
        m = M.SessionMetrics(s, 1e9)
        w = s.world
        for t in range(1500):
            fx, fy = w.fly.x, w.fly.y
            s.tick(pointer=(fx, fy), strike=(t % 150 == 100))
            if not w.fly.alive:
                break
        out = m.summary()
        self.assertGreaterEqual(out['committed_strikes'], 1)
        self.assertGreaterEqual(out['resolved_strikes'], 1)
        self.assertEqual(out['hits'] + out['untracked_hits'], int(not w.fly.alive))
        self.assertEqual(out['total_ticks'], t + 1)
        self.assertAlmostEqual(sum(out['action_distribution'].values()), 1.0)


if __name__ == '__main__':
    unittest.main()
