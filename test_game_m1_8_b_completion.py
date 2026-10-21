"""M1.8-B completion stages: behaviour of each new mechanism (B2d onwards).

See game/M1_8_B_COMPLETION_DESIGN.md. Configuration scope and provenance are tested in
test_game_m1_8_b_stages.py.
"""
import math
import os
from pathlib import Path
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.ecology import EcologicalCommand
from game.kinematics import KinematicSampler
from game.session import load_config
from game.world import World
from tools.m1_8_b_stage_record import read_commit

ROOT = Path(__file__).parent
ROOM = load_config(ROOT/'game_room_config.json')
B3A_ROOM = read_commit('6b43c0fd2cf5537216bb5f663b4e606e0fac76f6')


def command(state):
    return EcologicalCommand(state, 6.0, 0.0, 1.0)


def triangular_moments(low, mode, high):
    mean = (low + mode + high)/3
    var = (low*low + mode*mode + high*high - low*mode - low*high - mode*high)/18
    return mean, math.sqrt(var)


class TestB2dSampling(unittest.TestCase):
    SPECS = {'ODOR_SEARCH': ('odor_search_speed_bl_s', (4.0, 5.5, 7.0)),
             'RECOVER': ('recover_speed_bl_s', (5.0, 6.5, 8.0))}

    def test_room_configures_the_accepted_envelopes(self):
        for state, (key, support) in self.SPECS.items():
            spec = ROOM['kinematics'][key]
            self.assertEqual(spec['distribution'], 'triangular_symmetric')
            self.assertEqual((spec['min_bl_s'], spec['mode_bl_s'], spec['max_bl_s']), support)
            self.assertEqual(tuple(ROOM['ecology']['speed_bl_s'][state]), (support[0], support[2]))
            self.assertNotIn(key, B3A_ROOM['kinematics'])

    def test_one_draw_per_episode_from_its_own_stream(self):
        for state, (key, (low, mode, high)) in self.SPECS.items():
            sampler = KinematicSampler(255, **{key.replace('_speed_bl_s', ''): ROOM['kinematics'][key]})
            first = sampler.target_speed_bl_s(command(state), False)
            self.assertTrue(low <= first <= high)
            self.assertEqual(sampler.target_speed_bl_s(command(state), False), first)
            self.assertIsNone(sampler.target_speed_bl_s(command('TRANSIT'), False))
            second = sampler.target_speed_bl_s(command(state), False)
            self.assertNotEqual(first, second)
            self.assertEqual(sampler.draws_by_context, {state: 2})
            # The draw comes from the context's own stream and seed offset.
            offset = {'ODOR_SEARCH': KinematicSampler.ODOR_SEARCH_SEED_OFFSET,
                      'RECOVER': KinematicSampler.RECOVER_SEED_OFFSET}[state]
            import numpy as np
            self.assertEqual(first, float(np.random.default_rng(255 + offset).triangular(low, mode, high)))
            self.assertIsNone(sampler.target_speed_bl_s(command(state), True))

    def test_offline_draws_match_the_triangular_moments(self):
        for state, (key, support) in self.SPECS.items():
            sampler = KinematicSampler(4242, **{key.replace('_speed_bl_s', ''): ROOM['kinematics'][key]})
            draws = [sampler._draw(state) for _ in range(200_000)]
            mean = sum(draws)/len(draws)
            sd = math.sqrt(sum((d - mean)**2 for d in draws)/(len(draws) - 1))
            expected_mean, expected_sd = triangular_moments(*support)
            self.assertLess(abs(mean - expected_mean), 0.01)
            self.assertLess(abs(sd - expected_sd), 0.01)
            self.assertTrue(all(support[0] <= d <= support[2] for d in draws))

    def test_earlier_contexts_draw_the_same_sequence(self):
        k = ROOM['kinematics']
        old = KinematicSampler(101, k['explore_speed_bl_s'], k['odor_track_speed_bl_s'])
        new = KinematicSampler(101, k['explore_speed_bl_s'], k['odor_track_speed_bl_s'],
                               k['odor_search_speed_bl_s'], k['recover_speed_bl_s'])
        sequence = ['EXPLORE', 'ODOR_SEARCH', 'ODOR_TRACK', 'RECOVER', 'EXPLORE', 'ODOR_TRACK']
        old_draws = [old.target_speed_bl_s(command(s), False) for s in sequence]
        new_draws = [new.target_speed_bl_s(command(s), False) for s in sequence]
        for state, a, b in zip(sequence, old_draws, new_draws):
            if state in ('EXPLORE', 'ODOR_TRACK'):
                self.assertEqual(a, b)
            else:
                self.assertIsNone(a)
                self.assertIsNotNone(b)

    def test_world_wiring_and_gating(self):
        sampler = World(ROOM, 1).kinematic_sampler
        self.assertIsNotNone(sampler.odor_search)
        self.assertIsNotNone(sampler.recover)
        for config in (B3A_ROOM, load_config(ROOT/'game_play_config.json'), load_config(ROOT/'game_config.json')):
            sampler = World(config, 1).kinematic_sampler
            self.assertIsNone(sampler.odor_search)
            self.assertIsNone(sampler.recover)

    def test_invalid_specification_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'odor search speed'):
            KinematicSampler(1, odor_search={'distribution': 'uniform', 'min_bl_s': 4, 'mode_bl_s': 5,
                                             'max_bl_s': 6})


if __name__ == '__main__':
    unittest.main()
