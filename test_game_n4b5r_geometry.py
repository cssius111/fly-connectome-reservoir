"""M1.8-N4B5R: elevation-aware paddle tilt geometry (runtime candidate).

Geometry only: the accepted N4B1C decoder is unchanged. These tests pin the geometry
invariants, the ROOM-only scope, the configuration versioning and the provenance chain.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest

import numpy as np

from game.session import (build_policy, calibration_provenance, escape_decoder_spec, load_config,
                          resolve_escape_threshold)
from game.world import TILT_BEARING_ONLY, TILT_ELEVATION_AWARE, World

ROOT = Path(__file__).parent
ROOM = load_config(ROOT/'game_room_config.json')
GAME = load_config(ROOT/'game_play_config.json')
LAB = load_config(ROOT/'game_config.json')
ACCEPTED_COMMIT = 'e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf'
ACCEPTED = json.loads(subprocess.check_output(['git', 'show', ACCEPTED_COMMIT + ':game_room_config.json'],
                                              cwd=ROOT, text=True))
RECORD = 'results/game/calibration_room_m1_8_n4b5r.json'
DECODER_RECORD = 'results/game/calibration_room_m1_8_n4b1c.json'
DT = 0.02


def world(mode):
    cfg = copy.deepcopy(ROOM)
    cfg['swatter']['directional']['tilt_geometry'] = mode
    return World(cfg, 1)


def place(w, fx, fy, px, py, height, face, orientation):
    w.fly.x, w.fly.y = fx, fy
    sw = w.swatter
    sw.x, sw.y, sw.height, sw.face, sw.orientation = px, py, height, face, orientation
    return w.visual_half_size


def bearing_only(r, e, a, fx, fy, px, py, face, orientation):
    """The accepted M1.5/M1.7 formula, written out independently."""
    f = e + (1.0 - e) * face
    f *= 1.0 - a * (1 - face) * abs(math.sin(math.atan2(fy - py, fx - px) - orientation))
    return r * f


def elevation_aware(r, e, a, fx, fy, px, py, height, face, orientation):
    """N4B5 G3, written out independently."""
    dh = math.hypot(fx - px, fy - py)
    rng = math.sqrt(dh * dh + height * height)
    c = dh / rng if rng > 0 else 0.0
    return r * (e + (1.0 - e) * face) * (1.0 - a * c * (1.0 - face) * abs(math.sin(math.atan2(fy - py, fx - px) - orientation)))


def content_sha256(path):
    return hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


class TestGeometryInvariants(unittest.TestCase):
    def setUp(self):
        self.g0 = world(TILT_BEARING_ONLY)
        self.g3 = world(TILT_ELEVATION_AWARE)
        self.r, self.e = self.g0.paddle_radius, self.g0.edge_on_factor
        self.a = ROOM['swatter']['directional']['tilt_anisotropy']
        self.rng = np.random.default_rng(20260925)

    def random_states(self, n=2000):
        for _ in range(n):
            yield (float(self.rng.uniform(0, 3800)), float(self.rng.uniform(0, 2100)),
                   float(self.rng.uniform(0, 3800)), float(self.rng.uniform(0, 2100)),
                   float(self.rng.uniform(24, 320)), float(self.rng.choice([0.0, 0.15, 0.5, 0.85, 1.0])),
                   float(self.rng.uniform(-math.pi, math.pi)))

    def test_bearing_only_mode_is_the_accepted_formula_exactly(self):
        for fx, fy, px, py, h, face, o in self.random_states():
            self.assertEqual(place(self.g0, fx, fy, px, py, h, face, o),
                             bearing_only(self.r, self.e, self.a, fx, fy, px, py, face, o))

    def test_elevation_aware_mode_is_the_frozen_g3_formula(self):
        for fx, fy, px, py, h, face, o in self.random_states():
            self.assertAlmostEqual(place(self.g3, fx, fy, px, py, h, face, o),
                                   elevation_aware(self.r, self.e, self.a, fx, fy, px, py, h, face, o), places=10)

    def test_face_on_strike_geometry_is_unchanged(self):
        for fx, fy, px, py, h, _, o in self.random_states(500):
            self.assertAlmostEqual(place(self.g3, fx, fy, px, py, h, 1.0, o), place(self.g0, fx, fy, px, py, h, 1.0, o),
                                   places=12)

    def test_low_elevation_matches_the_current_formula_closely(self):
        # Paddle at hover height, fly far away: elevation <= 10 deg.
        worst = 0.0
        for k in range(360):
            b = math.radians(k)
            d = 320.0 / math.tan(math.radians(10.0)) + 50.0
            fx, fy = 1900 + d * math.cos(b), 1000 + d * math.sin(b)
            h0 = place(self.g0, fx, fy, 1900, 1000, 320, 0.0, 0.3)
            h3 = place(self.g3, fx, fy, 1900, 1000, 320, 0.0, 0.3)
            worst = max(worst, abs(h3 - h0) / h0)
        # Bounded by a * (1 - cos 10 deg) / (1 - a) ~= 0.5 %.
        self.assertLess(worst, 0.006)

    def test_tilt_modulation_vanishes_straight_overhead_and_is_continuous(self):
        base = self.r * self.e
        self.assertAlmostEqual(place(self.g3, 1000, 1000, 1000, 1000, 320, 0.0, 0.7), base, places=12)
        # Cross directly beneath the paddle, perpendicular to its axis, in 0.1-unit steps.
        prev = None
        jump3 = jump0 = 0.0
        prev0 = None
        for k in range(-2000, 2001):
            x = 1000 + 0.1 * k
            h3 = place(self.g3, 1000, x, 1000, 1000, 320, 0.0, 0.0)
            h0 = place(self.g0, 1000, x, 1000, 1000, 320, 0.0, 0.0)
            if prev is not None:
                jump3 = max(jump3, abs(h3 - prev))
                jump0 = max(jump0, abs(h0 - prev0))
            prev, prev0 = h3, h0
        self.assertLess(jump3, 0.02)       # continuous: at most ~0.01 units per 0.1-unit step
        self.assertGreater(jump0, 20.0)    # the bearing-only formula jumps by about r e a at the centre

    def test_no_bearing_rate_amplification_under_a_parked_paddle(self):
        """Straight pass at 200 units/s under a parked paddle (N4B5 section 4)."""
        def peak_size_theta_dot(w, offset):
            n = int(1200 / 200 / DT)
            th, hs, rs = [], [], []
            for k in range(n):
                fx, fy = 1900 - 600 + 200 * DT * k, 1000 + offset
                h = place(w, fx, fy, 1900, 1000, 320, 0.0, math.pi / 2)
                r = math.sqrt((fx - 1900) ** 2 + offset ** 2 + 320 ** 2)
                th.append(2 * math.atan(h / r)); hs.append(h); rs.append(r)
            size = [(2 * math.atan(hs[k + 1] / rs[k + 1]) - 2 * math.atan(hs[k] / rs[k + 1])) / DT for k in range(n - 1)]
            return max(size)
        for offset in (0.0, 2.0, 10.0, 25.0, 50.0):
            self.assertLess(peak_size_theta_dot(self.g3, offset), 0.1, offset)
        self.assertGreater(peak_size_theta_dot(self.g0, 2.0), 2.0)

    def test_unknown_geometry_mode_is_rejected(self):
        cfg = copy.deepcopy(ROOM)
        cfg['swatter']['directional']['tilt_geometry'] = 'elevation_aware_tilt_v2'
        with self.assertRaisesRegex(ValueError, 'unknown swatter.directional.tilt_geometry'):
            World(cfg, 1)


class TestScopeAndVersioning(unittest.TestCase):
    def test_room_only(self):
        self.assertEqual(ROOM['swatter']['directional']['tilt_geometry'], TILT_ELEVATION_AWARE)
        self.assertNotIn('tilt_geometry', GAME['swatter'].get('directional') or {})
        self.assertIsNone(LAB['swatter'].get('directional'))
        self.assertEqual(World(GAME, 1).tilt_geometry, TILT_BEARING_ONLY)
        self.assertEqual(World(LAB, 1).tilt_geometry, TILT_BEARING_ONLY)

    def test_room_differs_from_the_accepted_n4b1c_config_only_in_geometry_and_record(self):
        self.assertEqual(ROOM['config_version'], ACCEPTED['config_version'] + 1)
        after = copy.deepcopy(ROOM)
        after['config_version'] = ACCEPTED['config_version']
        for key in ('tilt_geometry', '_tilt_geometry_comment'):
            after['swatter']['directional'].pop(key)
        after['policy']['_comment'] = ACCEPTED['policy']['_comment']
        after['policy']['calibration_paths'] = ACCEPTED['policy']['calibration_paths']
        self.assertEqual(after, ACCEPTED)
        self.assertEqual(escape_decoder_spec(ROOM), escape_decoder_spec(ACCEPTED))


class TestProvenance(unittest.TestCase):
    def test_room_resolves_the_geometry_record_with_the_unchanged_decoder(self):
        source = resolve_escape_threshold(ROOM)
        self.assertEqual(source.origin, RECORD)
        self.assertEqual(source.threshold, 1.45)
        self.assertEqual(source.decoder, resolve_escape_threshold(ACCEPTED).decoder)
        p, _ = build_policy(ROOM)
        q, _ = build_policy(ACCEPTED)
        # Every constructed decoder / motor parameter and initial state is identical.
        self.assertEqual({k: v for k, v in vars(p).items()}, {k: v for k, v in vars(q).items()})
        self.assertEqual((p.threshold, p.fast_threshold, p.persistence_samples, p.sustained_window_samples,
                          p.lateral_window_samples, p.refractory_ticks), (1.45, 2.1, 3, 5, 3, 20))
        self.assertEqual(p.criterion_diagnostics()['escape_decoder'], 'lateral_dual_path_v1')

    def test_record_states_geometry_change_and_unchanged_decoder(self):
        record = load_config(ROOT/RECORD)
        decoder_record = load_config(ROOT/DECODER_RECORD)
        self.assertEqual(record['record_kind'], 'geometry-runtime-candidate-provenance-v1')
        self.assertTrue(record['decoder_unchanged'])
        self.assertTrue(record['not_a_decoder_recalibration'])
        self.assertTrue(record['geometry_changed'])
        self.assertEqual(record['escape_decoder'], decoder_record['escape_decoder'])
        self.assertEqual(record['escape_threshold'], decoder_record['escape_threshold'])
        self.assertEqual(record['provenance'], calibration_provenance(ROOM))
        self.assertEqual(record['geometry']['tilt_geometry'], TILT_ELEVATION_AWARE)
        self.assertEqual(record['geometry']['research']['research_commit'], '0e9d2d9')
        kept = record['decoder_record']
        self.assertEqual(kept['record'], DECODER_RECORD)
        self.assertEqual(kept['sha256'], content_sha256(DECODER_RECORD))
        self.assertFalse(kept['modified'])
        self.assertEqual(sorted(record['measurement_reuse']['changed_config_paths']),
                         ['config_version', 'policy._comment', 'policy.calibration_paths',
                          'swatter.directional._tilt_geometry_comment', 'swatter.directional.tilt_geometry'])

    def test_n4b1c_decoder_record_is_unmodified_and_still_bound_to_the_accepted_config(self):
        committed = subprocess.check_output(['git', 'show', ACCEPTED_COMMIT + ':' + DECODER_RECORD], cwd=ROOT)
        self.assertEqual((ROOT/DECODER_RECORD).read_bytes().replace(b'\r\n', b'\n'), committed.replace(b'\r\n', b'\n'))
        self.assertEqual(resolve_escape_threshold(ACCEPTED).origin, DECODER_RECORD)

    def test_geometry_mode_is_bound_into_provenance(self):
        cfg = copy.deepcopy(ROOM)
        cfg['swatter']['directional']['tilt_geometry'] = TILT_BEARING_ONLY
        with self.assertRaisesRegex(ValueError, 'No matching'):
            resolve_escape_threshold(cfg)


if __name__ == '__main__':
    unittest.main()
