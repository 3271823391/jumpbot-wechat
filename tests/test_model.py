import tempfile
import unittest
from pathlib import Path

from model import JumpModel


class ModelTests(unittest.TestCase):
    def test_requires_real_samples(self):
        with tempfile.TemporaryDirectory() as d:
            m = JumpModel(Path(d) / "model.json")
            self.assertIsNone(m.fit())
            with self.assertRaises(ValueError):
                m.add(seconds=.2, distance=30, direction=1, screen_width=400,
                      confidence=1, source="simulated")

    def test_selects_monotonic_nonlinear_model(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "model.json"
            m = JumpModel(path)
            for i in range(12):
                seconds = .18 + i * .065
                distance = 400 * (.035 + .45 * seconds + .32 * seconds**2)
                m.add(seconds=seconds, distance=distance, direction=1,
                      screen_width=400, confidence=1, source="real")
            fit = m.fit()
            self.assertEqual(fit["kind"], "quadratic")
            self.assertLess(fit["loo_mae_normalized"], 1e-9)
            target = 400 * (.035 + .45 * .5 + .32 * .5**2)
            estimate = m.press_for(target, 400)
            self.assertAlmostEqual(estimate["seconds"], .5, delta=.01)
            self.assertEqual(len(JumpModel(path).samples), 12)


if __name__ == "__main__":
    unittest.main()
