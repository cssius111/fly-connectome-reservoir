"""M3.2: the ache2019_v1 encoder feature model (game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md, V7).

The legacy feature model stays the default and is unchanged when the key is absent. The new
mode drives LPLC2 by a Gaussian of log angular size and LC4 linearly by angular velocity, both
only while the stimulus expands, with the published constants of Ache et al. 2019.
"""
from __future__ import annotations

import copy
import math
import os
import unittest

os.environ.setdefault("NUMBA_NUM_THREADS", "4")

import numpy as np

from game.fly import ROOT, build_brain
from game.perception import (ACHE2019, FEATURE_MODEL_ACHE2019, FEATURE_MODEL_LEGACY, Retina,
                             RetinalEncoder, ache2019_drive_mv, encoder_feature_model)
from game.session import load_config

LAB = load_config(ROOT / "game_config.json")
SCALE = 0.1
CANDIDATE_COMMIT = "408fbc093c4e8f37c1371910756fb31f5f60ecbf"   # the M3.2 candidate, ROOM v28
_SHARED: dict = {}


def brain():
    if "brain" not in _SHARED:
        _SHARED["brain"] = build_brain(LAB, ROOT)
    return _SHARED["brain"]


def with_model(config, model, scale=SCALE):
    c = copy.deepcopy(config)
    c["encoder"]["feature_model"] = model
    if model == FEATURE_MODEL_ACHE2019:
        c["encoder"]["ache2019"] = {"scale_volts_per_mv": scale}
    return c


def injection(encoder, retina):
    return [(idx.tolist(), float(amount)) for idx, amount in encoder.inject(retina)]


RETINAS = [Retina(theta=math.radians(t), theta_dot=d, azimuth=a)
           for t, d, a in ((10, 0.0, 0.3), (12, 0.4, -0.2), (30, 3.0, 0.5), (42, 9.0, -0.7),
                           (70, 25.0, 0.0), (90, -4.0, 0.9), (120, 60.0, -1.0))]


class TestConfiguration(unittest.TestCase):
    def test_absent_key_means_legacy(self):
        self.assertNotIn("feature_model", LAB["encoder"])
        self.assertEqual(encoder_feature_model(LAB), FEATURE_MODEL_LEGACY)

    def test_invalid_configurations_are_rejected(self):
        bad = []
        c = copy.deepcopy(LAB); c["encoder"]["feature_model"] = "other"; bad.append(c)
        c = with_model(LAB, FEATURE_MODEL_ACHE2019); del c["encoder"]["ache2019"]; bad.append(c)
        for value in (0.0, -0.1, float("nan"), True, "0.1"):
            bad.append(with_model(LAB, FEATURE_MODEL_ACHE2019, value))
        c = with_model(LAB, FEATURE_MODEL_ACHE2019); c["encoder"]["ache2019"]["lplc2_center_deg"] = 50
        bad.append(c)
        c = copy.deepcopy(LAB); c["encoder"]["ache2019"] = {"scale_volts_per_mv": SCALE}; bad.append(c)
        for config in bad:
            with self.assertRaises(ValueError):
                encoder_feature_model(config)

    def test_published_constants(self):
        self.assertEqual(ACHE2019, {"lc4_mv_per_deg_s": 0.0002567, "lplc2_peak_mv": 1.7,
                                    "lplc2_center_deg": 42.0, "lplc2_log_width": 0.52,
                                    "weight_lplc2": 1.45, "weight_lc4": 1.62})


class TestLegacyUnchanged(unittest.TestCase):
    def test_explicit_legacy_equals_absent_key(self):
        a = RetinalEncoder(brain(), LAB)
        b = RetinalEncoder(brain(), with_model(LAB, FEATURE_MODEL_LEGACY))
        for retina in RETINAS:
            self.assertEqual(injection(a, retina), injection(b, retina))
            self.assertEqual(a.last_drive, b.last_drive)


class TestAche2019Mode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enc = RetinalEncoder(brain(), with_model(LAB, FEATURE_MODEL_ACHE2019))
        cls.legacy = RetinalEncoder(brain(), LAB)

    def drive(self, theta_deg, theta_dot, azimuth=0.5):
        self.enc.inject(Retina(theta=math.radians(theta_deg), theta_dot=theta_dot, azimuth=azimuth))
        return dict(self.enc.last_drive)

    def test_pure_function_of_retina(self):
        r = Retina(theta=0.7, theta_dot=5.0, azimuth=-0.4)
        first = injection(self.enc, r)
        for other in RETINAS:
            self.enc.inject(other)
        self.assertEqual(first, injection(self.enc, r))
        self.assertTrue(first)

    def test_static_and_receding_drive_nothing(self):
        for theta in (5, 30, 42, 60, 90, 150):
            for theta_dot in (0.0, -0.5, -20.0):
                r = Retina(theta=math.radians(theta), theta_dot=theta_dot, azimuth=0.2)
                self.assertEqual(self.enc.inject(r), [])
                self.assertTrue(all(v == 0.0 for v in self.enc.last_drive.values()))

    def test_lplc2_is_a_log_gaussian_peaking_at_42_degrees(self):
        theta_dot = 1e-6          # expanding, with negligible LC4 drive
        values = {t: self.drive(t, theta_dot)["loomR"] for t in (20, 30, 41, 42, 43, 60, 90)}
        self.assertEqual(max(values, key=values.get), 42)
        expected = SCALE * 1.45 * 1.7 * math.exp(-math.log(60 / 42) ** 2 / (2 * 0.52 ** 2))
        self.assertAlmostEqual(values[60], expected, places=6)
        # Symmetric in log size: 42 * k and 42 / k give the same drive.
        self.assertAlmostEqual(self.drive(42 * 1.5, theta_dot)["loomR"],
                               self.drive(42 / 1.5, theta_dot)["loomR"], places=6)

    def test_lc4_is_linear_in_angular_velocity(self):
        a = self.drive(30, 1.0)["threatR"]
        b = self.drive(30, 2.0)["threatR"]
        self.assertAlmostEqual(b, 2 * a, places=6)
        self.assertAlmostEqual(a, SCALE * 1.62 * 0.0002567 * math.degrees(1.0), places=6)
        # The LC4 drive does not depend on size.
        self.assertAlmostEqual(self.drive(80, 1.0)["threatR"], a, places=6)

    def test_cap_and_side(self):
        big = self.drive(42, 1000.0, azimuth=-0.3)
        self.assertEqual(big["threatL"], np.float32(0.8))
        self.assertEqual(big["threatR"], 0.0)
        self.assertEqual(big["loomR"], 0.0)
        self.assertGreater(big["loomL"], 0.0)
        right = self.drive(42, 1.0, azimuth=0.0)       # azimuth 0 counts as right, as in legacy
        self.assertGreater(right["loomR"], 0.0)
        self.assertEqual(right["loomL"], 0.0)

    def test_same_cells_and_keys_as_legacy(self):
        r = Retina(theta=math.radians(40), theta_dot=3.0, azimuth=0.6)
        new = self.enc.inject(r)
        old = self.legacy.inject(r)
        self.assertEqual([idx.tolist() for idx, _ in new], [idx.tolist() for idx, _ in old])
        self.assertEqual(set(self.enc.last_drive), set(self.legacy.last_drive))
        self.assertEqual(self.enc.population, self.legacy.population)

    def test_drive_function_matches_the_paper(self):
        lplc2, lc4 = ache2019_drive_mv(Retina(theta=math.radians(42), theta_dot=math.radians(1000),
                                              azimuth=0.1))
        self.assertAlmostEqual(lplc2, 1.45 * 1.7, places=9)
        self.assertAlmostEqual(lc4, 1.62 * 0.0002567 * 1000, places=9)


class TestRoomConfiguration(unittest.TestCase):
    """The M3.2 candidate (ROOM v28 at 408fbc0), its transfer record, and the revert to v27.

    M3.2 failed its primary criterion and the user chose to restore the v27 ROOM configuration
    (results/game/M3_2_ESCAPE_FEATURE_ROLES.md). The candidate stays in git history and its
    record stays in results/ as the record of what was tested.
    """

    @classmethod
    def setUpClass(cls):
        import json
        import subprocess
        from tools.m3_2_record import RECORD, SOURCE_RECORD
        cls.room = load_config(ROOT / "game_room_config.json")
        cls.candidate = json.loads(subprocess.check_output(
            ["git", "show", CANDIDATE_COMMIT + ":game_room_config.json"], cwd=ROOT, text=True))
        cls.record = load_config(ROOT / RECORD)
        cls.source = load_config(ROOT / SOURCE_RECORD)
        cls.record_path = RECORD

    def test_the_working_room_configuration_is_the_reverted_v27(self):
        self.assertEqual(self.room["config_version"], 27)
        self.assertEqual(encoder_feature_model(self.room), FEATURE_MODEL_LEGACY)
        self.assertNotIn("ache2019", self.room["encoder"])

    def test_the_candidate_used_the_calibrated_ache2019_encoder(self):
        self.assertEqual(self.candidate["config_version"], 28)
        self.assertEqual(encoder_feature_model(self.candidate), FEATURE_MODEL_ACHE2019)
        self.assertEqual(self.candidate["encoder"]["ache2019"], {"scale_volts_per_mv": 0.28})

    def test_lab_and_game_keep_the_legacy_encoder(self):
        for name in ("game_config.json", "game_play_config.json"):
            config = load_config(ROOT / name)
            self.assertNotIn("feature_model", config["encoder"], name)
            self.assertEqual(encoder_feature_model(config), FEATURE_MODEL_LEGACY)

    def test_the_record_binds_the_candidate_and_carries_the_decoder(self):
        from game.session import calibration_provenance, resolve_escape_threshold
        self.assertEqual(self.record["record_kind"], "m3-2-encoder-feature-roles-transfer-provenance-v1")
        self.assertEqual(self.record["provenance"], calibration_provenance(self.candidate))
        resolved = resolve_escape_threshold(self.candidate)
        self.assertEqual(resolved.origin, self.record_path)
        self.assertEqual(resolved.threshold, 1.45)
        for key in ("escape_threshold", "escape_decoder", "parameter_basis", "geometry"):
            self.assertEqual(self.record[key], self.source[key], key)
        self.assertTrue(self.record["decoder_unchanged"] and self.record["encoder_changed"])
        self.assertEqual(self.record["encoder"]["published_constants"], ACHE2019)
        self.assertEqual(self.record["encoder"]["scale_volts_per_mv"], 0.28)

    def test_the_writer_rejects_a_change_outside_the_encoder_keys(self):
        from tools.m3_2_record import build_record
        config = copy.deepcopy(self.candidate)
        config["encoder"]["loom_gain"] += 1
        with self.assertRaises(SystemExit):
            build_record(config)


if __name__ == "__main__":
    unittest.main()
