"""M3.4: Retina elevation and the retinotopic_v1 encoder mode (game/M3_4_RETINOTOPIC_DRIVE_DESIGN.md, V7).

The tests use small synthetic receptive-field tables written to a temporary directory and need
no network. One test also exercises the locally built table when it is present.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

os.environ.setdefault("NUMBA_NUM_THREADS", "4")

import numpy as np

from game.fly import ROOT, build_brain
from game.perception import (FEATURE_MODEL_ACHE2019, FEATURE_MODEL_RETINOTOPIC, RETINOTOPIC_FIELD_KEYS,
                             Retina, RetinaProjector, RetinalEncoder, ache2019_drive_mv,
                             encoder_feature_model, fields_digest, load_receptive_fields,
                             view_direction)
from game.session import load_config

LAB = load_config(ROOT / "game_config.json")
FIELDS = "data/fields_test.npz"
SCALE = 1.0
_SHARED: dict = {}


def brain():
    if "brain" not in _SHARED:
        _SHARED["brain"] = build_brain(LAB, ROOT)
    return _SHARED["brain"]


def driven_cells():
    """The balanced LPLC2/LC4 subsets the encoder drives, from the runtime's own code."""
    if "cells" not in _SHARED:
        enc = RetinalEncoder(brain(), LAB)
        _SHARED["cells"] = {"LPLC2": enc._fd.cells["loom"], "LC4": enc._fd.cells["threat"]}
    return _SHARED["cells"]


def synthetic_fields(centres: dict, spread_deg: float = 4.0) -> dict:
    """Three columns per driven cell around the (az, el) centre of its side, in degrees."""
    ids = np.load(ROOT / "data/brain.npz")["ids"]
    rows = sorted((int(i), t, s) for t, by_side in driven_cells().items()
                  for s, cells in by_side.items() for i in cells)
    offsets, dirs, counts = [0], [], []
    for _, _, s in rows:
        az, el = centres[s]
        for d_az, d_el, n in ((0.0, 0.0, 4), (spread_deg, 0.0, 2), (0.0, spread_deg, 2)):
            dirs.append(view_direction(math.radians(az + d_az), math.radians(el + d_el)))
            counts.append(n)
        offsets.append(offsets[-1] + 3)
    fields = {
        "cell_index": np.array([r[0] for r in rows], np.int64),
        "cell_body": ids[[r[0] for r in rows]].astype(np.int64),
        "cell_type": np.array([r[1] for r in rows], "<U8"),
        "cell_side": np.array([r[2] for r in rows], "<U1"),
        "column_offsets": np.array(offsets, np.int64),
        "column_code": np.arange(len(counts), dtype=np.int32),
        "column_count": np.array(counts, np.int32),
        "column_direction": np.array(dirs, np.float64),
    }
    assert tuple(sorted(fields)) == RETINOTOPIC_FIELD_KEYS
    return fields


class Workspace:
    """A temporary root with the real brain.npz and a synthetic receptive-field table."""

    def __init__(self, fields: dict):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        os.symlink(ROOT / "data/brain.npz", self.root / "data/brain.npz")
        np.savez(self.root / FIELDS, **fields)
        self.digest = fields_digest(fields)

    def config(self, scale=SCALE, min_edge=10.0, digest=None):
        c = copy.deepcopy(LAB)
        c["encoder"]["feature_model"] = FEATURE_MODEL_RETINOTOPIC
        c["encoder"]["retinotopic"] = {"scale_volts_per_mv": scale, "acceptance_fwhm_deg": 7.7,
                                       "lplc2_min_edge_speed_deg_s": min_edge, "fields_file": FIELDS,
                                       "fields_sha256": digest or self.digest}
        return c

    def encoder(self, **kwargs):
        return RetinalEncoder(brain(), self.config(**kwargs), self.root)

    def close(self):
        self.tmp.cleanup()


def retina(theta_deg, theta_dot, az_deg, el_deg=0.0):
    return Retina(theta=math.radians(theta_deg), theta_dot=theta_dot, azimuth=az_deg / 180.0,
                  elevation=math.radians(el_deg))


def driven(inject) -> dict:
    return {int(i): float(amount) for idx, amount in inject for i in idx}


class TestRetinaElevation(unittest.TestCase):
    def test_default_and_positional_construction(self):
        self.assertEqual(Retina(0.5, 1.0, 0.2).elevation, 0.0)
        self.assertEqual(Retina(theta=0.5, theta_dot=1.0, azimuth=0.2, elevation=0.3).elevation, 0.3)

    def test_recorder_record_gains_only_the_elevation_key(self):
        self.assertEqual(set(asdict(Retina(0.5, 1.0, 0.2))), {"theta", "theta_dot", "azimuth", "elevation"})

    def test_projector_elevation_is_height_over_horizontal_distance(self):
        world = SimpleNamespace(fly=SimpleNamespace(x=0.0, y=0.0, heading=0.0),
                                swatter=SimpleNamespace(x=300.0, y=400.0, height=500.0),
                                visual_half_size=50.0)
        r = RetinaProjector(0.02).project(world)
        self.assertAlmostEqual(r.elevation, math.radians(45.0), places=12)
        world.swatter.height = 0.0
        self.assertEqual(RetinaProjector(0.02).project(world).elevation, 0.0)

    def test_legacy_and_ache_ignore_elevation(self):
        ache = copy.deepcopy(LAB)
        ache["encoder"]["feature_model"] = FEATURE_MODEL_ACHE2019
        ache["encoder"]["ache2019"] = {"scale_volts_per_mv": 0.3}
        for config in (LAB, ache):
            enc = RetinalEncoder(brain(), config)
            for theta, dot, az in ((0.4, 2.0, 0.3), (0.9, 6.0, -0.6), (0.2, 0.0, 0.1)):
                flat = [(i.tolist(), float(a)) for i, a in enc.inject(Retina(theta, dot, az))]
                high = [(i.tolist(), float(a)) for i, a in enc.inject(Retina(theta, dot, az, 0.8))]
                self.assertEqual(flat, high)


class TestConfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Workspace(synthetic_fields({"L": (-30.0, 0.0), "R": (30.0, 0.0)}))

    @classmethod
    def tearDownClass(cls):
        cls.ws.close()

    def test_valid_block_is_accepted(self):
        self.assertEqual(encoder_feature_model(self.ws.config()), FEATURE_MODEL_RETINOTOPIC)

    def test_invalid_blocks_are_rejected(self):
        bad = []
        c = self.ws.config(); del c["encoder"]["retinotopic"]; bad.append(c)
        c = self.ws.config(); c["encoder"]["retinotopic"]["extra"] = 1; bad.append(c)
        c = self.ws.config(); c["encoder"]["ache2019"] = {"scale_volts_per_mv": 0.3}; bad.append(c)
        for key, value in (("scale_volts_per_mv", 0.0), ("acceptance_fwhm_deg", -1.0),
                           ("lplc2_min_edge_speed_deg_s", float("nan")), ("scale_volts_per_mv", True),
                           ("fields_file", ""), ("fields_sha256", "ABC"), ("fields_sha256", "0" * 63)):
            c = self.ws.config(); c["encoder"]["retinotopic"][key] = value; bad.append(c)
        legacy = copy.deepcopy(LAB); legacy["encoder"]["retinotopic"] = self.ws.config()["encoder"]["retinotopic"]
        bad.append(legacy)
        for c in bad:
            with self.assertRaises(ValueError):
                encoder_feature_model(c)

    def test_digest_mismatch_is_refused(self):
        with self.assertRaises(ValueError):
            self.ws.encoder(digest="0" * 64)

    def test_missing_table_is_refused(self):
        with self.assertRaises(FileNotFoundError):
            load_receptive_fields(self.ws.root / "data/none.npz", self.ws.digest)

    def test_table_without_a_driven_cell_is_refused(self):
        fields = synthetic_fields({"L": (-30.0, 0.0), "R": (30.0, 0.0)})
        keep = np.arange(len(fields["cell_index"])) != 0
        lo = fields["column_offsets"]
        cols = np.concatenate([np.arange(lo[k], lo[k + 1]) for k in np.flatnonzero(keep)])
        fields = {**{k: fields[k][keep] for k in ("cell_index", "cell_body", "cell_type", "cell_side")},
                  "column_offsets": np.r_[0, np.cumsum(np.diff(lo)[keep])].astype(np.int64),
                  **{k: fields[k][cols] for k in ("column_code", "column_count", "column_direction")}}
        ws = Workspace(fields)
        try:
            with self.assertRaises(ValueError):
                ws.encoder()
        finally:
            ws.close()


class TestRetinotopicMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Workspace(synthetic_fields({"L": (-30.0, 0.0), "R": (30.0, 0.0)}))
        cls.enc = cls.ws.encoder()
        cls.drive = cls.enc._retinotopic
        cls.side = {int(i): s for t in driven_cells().values() for s, cells in t.items() for i in cells}

    @classmethod
    def tearDownClass(cls):
        cls.ws.close()

    def test_coverage_is_monotonic_in_size_and_bounded(self):
        centre = view_direction(math.radians(30.0), 0.0)
        right = self.drive.channels["loom"]["side"] == "R"
        previous = None
        for theta in (2, 5, 10, 20, 40, 60, 80):
            c = self.drive.coverage("loom", centre, theta)
            self.assertTrue(np.all((c >= 0) & (c <= 1)))
            if previous is not None:
                self.assertTrue(np.all(c >= previous))
            previous = c
        self.assertTrue(np.all(previous[right] > 0.999))
        self.assertTrue(np.all(previous[~right] < 1e-6))
        far = self.drive.coverage("loom", view_direction(math.radians(-150.0), 0.0), 20)
        self.assertTrue(np.all(far < 1e-12))

    def test_drive_is_scale_times_feature_times_coverage(self):
        r = retina(20, 1.0, 30)
        lplc2_mv, lc4_mv = ache2019_drive_mv(r)
        got = driven(self.enc.inject(r))
        centre = view_direction(math.radians(30.0), 0.0)
        for channel, mv in (("loom", lplc2_mv), ("threat", lc4_mv)):
            ch = self.drive.channels[channel]
            want = np.minimum(0.8, SCALE * mv * self.drive.coverage(channel, centre, 20.0)).astype(np.float32)
            for i, w in zip(ch["index"], want):
                self.assertEqual(got.get(int(i), 0.0), float(w) if w >= 1e-6 else 0.0)

    def test_disk_drives_only_the_eye_it_covers(self):
        right = driven(self.enc.inject(retina(30, 2.0, 30)))
        left = driven(self.enc.inject(retina(30, 2.0, -30)))
        self.assertTrue(right and left)
        self.assertEqual({self.side[i] for i in right}, {"R"})
        self.assertEqual({self.side[i] for i in left}, {"L"})

    def test_lplc2_needs_the_edge_speed_and_lc4_does_not(self):
        loom = set(int(i) for i in self.drive.channels["loom"]["index"])
        threat = set(int(i) for i in self.drive.channels["threat"]["index"])
        slow = driven(self.enc.inject(retina(30, math.radians(19.0), 30)))    # edge 9.5 deg/s
        fast = driven(self.enc.inject(retina(30, math.radians(21.0), 30)))    # edge 10.5 deg/s
        self.assertFalse(loom & set(slow))
        self.assertTrue(threat & set(slow))
        self.assertTrue(loom & set(fast))
        self.assertEqual(self.enc.last_drive["loomL"], 0.0)
        creep = driven(self.enc.inject(retina(28, 0.003, 30)))
        self.assertFalse(loom & set(creep))

    def test_static_and_receding_drive_nothing(self):
        for dot in (0.0, -0.5):
            self.assertEqual(self.enc.inject(retina(40, dot, 30)), [])
            self.assertTrue(all(v == 0.0 for v in self.enc.last_drive.values()))

    def test_pure_function_of_retina(self):
        r = retina(35, 3.0, 25, 5)
        first = [(i.tolist(), float(a)) for i, a in self.enc.inject(r)]
        self.enc.inject(retina(60, 9.0, -40))
        self.assertEqual(first, [(i.tolist(), float(a)) for i, a in self.enc.inject(r)])

    def test_cap_holds(self):
        enc = self.ws.encoder(scale=1000.0)
        amounts = [float(a) for _, a in enc.inject(retina(60, 5.0, 30))]
        self.assertTrue(amounts)
        self.assertLessEqual(max(amounts), np.float32(0.8))


class TestFrontalDiskDrivesBothEyes(unittest.TestCase):
    def test_both_sides(self):
        ws = Workspace(synthetic_fields({"L": (-4.0, 0.0), "R": (4.0, 0.0)}))
        try:
            enc = ws.encoder()
            side = {int(i): s for t in driven_cells().values() for s, cells in t.items() for i in cells}
            got = driven(enc.inject(retina(30, 2.0, 0.5)))     # Retina.side is 'R'
            self.assertEqual({side[i] for i in got}, {"L", "R"})
        finally:
            ws.close()


# The tested M3.4 candidate (ROOM v30). M3.4 failed checks V2 and V8a, so the working ROOM
# configuration is v27 again (results/game/M3_4_RETINOTOPIC_DRIVE.md); the candidate stays in git
# history.
CANDIDATE_COMMIT = "10e12f6c29a285817e020b06b7c0dfc2d3ae5fe1"


class TestRoomCandidate(unittest.TestCase):
    """The M3.4 candidate, ROOM config_version 30: the preregistered encoder block and the M3.3 decoder."""

    def setUp(self):
        import json
        import subprocess
        self.room = json.loads(subprocess.check_output(
            ["git", "show", CANDIDATE_COMMIT + ":game_room_config.json"], cwd=ROOT, text=True))

    def test_the_working_room_configuration_keeps_the_legacy_encoder(self):
        # M3.4 failed and restored v27; the M3.7 (v31), M3.8 (v32), M3.9 (v33) and M3.10 (v34)
        # candidates change only class-B flight and ecology keys.
        room = load_config(ROOT / "game_room_config.json")
        self.assertIn(room["config_version"], (27, 31, 32, 33, 34))
        self.assertNotIn("feature_model", room["encoder"])

    def test_candidate_configuration(self):
        from game.session import escape_decoder_spec
        self.assertEqual(self.room["config_version"], 30)
        self.assertEqual(encoder_feature_model(self.room), FEATURE_MODEL_RETINOTOPIC)
        block = self.room["encoder"]["retinotopic"]
        self.assertEqual({k: block[k] for k in ("acceptance_fwhm_deg", "lplc2_min_edge_speed_deg_s",
                                                "fields_file")},
                         {"acceptance_fwhm_deg": 7.7, "lplc2_min_edge_speed_deg_s": 10.0,
                          "fields_file": "data/receptive_fields_v1.npz"})
        self.assertEqual(escape_decoder_spec(self.room),
                         {"kind": "same_side_doublet_v1", "alert_reference_threshold": 1.45,
                          "doublet_window_ms": 40.0, "required_spikes": 2})

    def test_candidate_resolves_the_m3_4_record(self):
        from game.session import resolve_escape_threshold
        source = resolve_escape_threshold(self.room)
        self.assertEqual(source.origin, "results/game/calibration_room_m3_4.json")
        self.assertEqual(source.threshold, 1.45)
        record = load_config(ROOT / source.origin)
        self.assertEqual(record["encoder"]["block"], self.room["encoder"]["retinotopic"])

    def test_lab_and_game_keep_the_legacy_encoder(self):
        for name in ("game_config.json", "game_play_config.json"):
            self.assertNotIn("feature_model", load_config(ROOT / name)["encoder"])


@unittest.skipUnless((ROOT / "data/receptive_fields_v1.npz").exists(), "receptive-field table not built")
class TestBuiltTable(unittest.TestCase):
    def test_built_table_drives_the_covered_eyes(self):
        with np.load(ROOT / "data/receptive_fields_v1.npz") as z:
            digest = fields_digest({k: z[k] for k in z.files})
        c = copy.deepcopy(LAB)
        c["encoder"]["feature_model"] = FEATURE_MODEL_RETINOTOPIC
        c["encoder"]["retinotopic"] = {"scale_volts_per_mv": 40.0, "acceptance_fwhm_deg": 7.7,
                                       "lplc2_min_edge_speed_deg_s": 10.0,
                                       "fields_file": "data/receptive_fields_v1.npz", "fields_sha256": digest}
        enc = RetinalEncoder(brain(), c)
        side = {int(i): s for t in driven_cells().values() for s, cells in t.items() for i in cells}
        self.assertEqual({side[i] for i in driven(enc.inject(retina(30, 2.0, 0)))}, {"L", "R"})
        self.assertEqual({side[i] for i in driven(enc.inject(retina(30, 2.0, 90, 11)))}, {"R"})


if __name__ == "__main__":
    unittest.main()
