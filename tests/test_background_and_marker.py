"""Regressions for changing backgrounds and target surface markers."""
import random
import unittest

from PIL import ImageDraw

from jumpbot import observe
from simulate import scene


class BackgroundAndMarkerTests(unittest.TestCase):
    def test_pale_background_and_dark_block_are_not_game_over(self):
        rng = random.Random(20261019)
        for index in range(88):
            image, _, target = scene(rng, index)
        state = observe(image)
        self.assertFalse(state["game_over"])
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["target_top_center"][0], target[0], delta=12)

    def test_white_surface_marker_takes_priority_when_distinct(self):
        rng = random.Random(20261019)
        for index in range(88):
            image, _, target = scene(rng, index)
        marker = (target[0] + 10, target[1])
        ImageDraw.Draw(image).ellipse((marker[0]-8, marker[1]-8,
                                       marker[0]+8, marker[1]+8), fill="white")
        state = observe(image)
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["target_top_center"][0], marker[0], delta=2)
        self.assertAlmostEqual(state["target_top_center"][1], marker[1], delta=2)


if __name__ == "__main__":
    unittest.main()
