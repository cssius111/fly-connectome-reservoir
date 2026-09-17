"""Small checks aimed at leakage and the temporal task's control conditions."""
import json
import unittest
import numpy as np
from experiment import ROOT, make_trials, fit_ridge, predict, wilson


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT/"config.json").read_text())

    def test_splits_and_reproducibility(self):
        rows, drives = make_trials(self.cfg, "side", 101)
        rows2, drives2 = make_trials(self.cfg, "side", 101)
        self.assertEqual(rows, rows2)
        np.testing.assert_array_equal(drives, drives2)
        for split in ("train", "validation", "test"):
            labels = [r["label"] for r in rows if r["split"] == split]
            self.assertEqual(sum(labels)*2, len(labels))
        self.assertEqual(len(set(r["noise_seed"] for r in rows)), len(rows))

    def test_temporal_input_is_matched_and_absent_at_readout(self):
        _, d = make_trials(self.cfg, "order", 101)
        np.testing.assert_array_equal(d.sum(axis=1)[:, 0], d.sum(axis=1)[:, 1])
        a, b = self.cfg["tasks"]["order"]["readout"]
        self.assertFalse(d[:, a:b].any())
        self.assertFalse(np.array_equal(d[:, 10:20], d[:, 25:35]))

    def test_ridge_scaling_and_input_separability(self):
        rows, d = make_trials(self.cfg, "side", 101)
        tr = np.array([r["split"] == "train" for r in rows])
        y = np.array([r["label"] for r in rows])
        x = d.sum(axis=1)
        model = fit_ridge(x[tr], y[tr], 1.0)
        np.testing.assert_allclose(model["mean"], x[tr].mean(axis=0, dtype=np.float64))
        before = model["mean"].copy()
        predict(model, np.full((3, 2), 1e9))
        np.testing.assert_array_equal(before, model["mean"])
        self.assertEqual(float(np.mean(predict(model, x[~tr]) == y[~tr])), 1.0)

    def test_uncertainty_not_zero_at_perfect_accuracy(self):
        lo, hi = wilson(60, 60)
        self.assertLess(lo, 1.0)
        self.assertAlmostEqual(hi, 1.0)


if __name__ == "__main__":
    unittest.main()
