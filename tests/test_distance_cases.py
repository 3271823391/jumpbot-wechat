"""Geometry stress cases, separate from measured real-game performance."""
import unittest

from PIL import Image, ImageDraw

from jumpbot import observe


def scene(dx, radius, direction=1):
    image = Image.new("RGB", (632, 1160), (210, 196, 190))
    draw = ImageDraw.Draw(image)
    pawn_x = 200 if direction == 1 else 432

    def block(x, y, r, color):
        draw.polygon([(x-r, y), (x, y-r*.55), (x+r, y), (x, y+r*.55)], fill=color)
        draw.polygon([(x-r, y), (x, y+r*.55), (x, y+r*.55+45),
                      (x-r, y+45)], fill=(90, 90, 90))
        draw.polygon([(x, y+r*.55), (x+r, y), (x+r, y+45),
                      (x, y+r*.55+45)], fill=(100, 100, 100))

    target_x = pawn_x + direction*dx
    target_y = 570 if dx < 150 else 520
    block(target_x, target_y, radius, (110, 160, 110))
    block(pawn_x, 670, 90, (116, 116, 116))
    draw.ellipse((pawn_x-17, 598, pawn_x+17, 632), fill=(49, 43, 78))
    draw.polygon([(pawn_x-14, 635), (pawn_x+14, 635),
                  (pawn_x+21, 700), (pawn_x-21, 700)], fill=(57, 51, 84))
    return image, (target_x, target_y)


class DistanceAndSizeCases(unittest.TestCase):
    def test_near_far_small_in_both_directions(self):
        for direction in (-1, 1):
            for name, dx, radius in (("near", 80, 45), ("far", 300, 85),
                                     ("small", 205, 25), ("far_small", 300, 25)):
                with self.subTest(direction=direction, case=name):
                    image, expected = scene(dx, radius, direction)
                    state = observe(image)
                    self.assertTrue(state["ready"])
                    self.assertAlmostEqual(state["target_top_center"][0], expected[0], delta=12)
                    self.assertAlmostEqual(state["target_top_center"][1], expected[1], delta=15)


if __name__ == "__main__":
    unittest.main()
