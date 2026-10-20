import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from jumpbot import observe, measure_landing, score_change, recover_occluded_platform


DATA = Path(__file__).resolve().parents[1] / "data"


@unittest.skipUnless((DATA / "capture_20261019_164013.png").exists(),
                     "本机真实截图未随公开仓库发布")
class RealSceneRegression(unittest.TestCase):
    def scene(self, name):
        return observe(Image.open(DATA / name))

    def test_initial_target_geometry(self):
        state = self.scene("capture_20261019_164013.png")
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["pawn_contact"][0], 202, delta=4)
        self.assertAlmostEqual(state["target_geometric_center"][0], 457, delta=8)
        self.assertAlmostEqual(state["target_geometric_center"][1], 545, delta=15)

    def test_touching_red_yellow_platforms_separate(self):
        state = self.scene("after_20261019_165457_063790100.png")
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["target_top_center"][0], 248, delta=10)
        self.assertLess(state["target_top_center"][0], state["pawn_contact"][0])

    def test_mushroom_platform_is_current(self):
        state = self.scene("capture_20261019_170457_094788600.png")
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["current_top_center"][0], 264, delta=10)
        self.assertAlmostEqual(state["target_top_center"][0], 395, delta=10)

    def test_narrow_white_pedestal_after_landing(self):
        path = DATA / "review" / "20261020_085536" / "jump_0009_after.png"
        if not path.exists():
            self.skipTest("本机复盘截图未随公开仓库发布")
        state = observe(Image.open(path))
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["current_top_center"][0], 289, delta=5)
        self.assertAlmostEqual(state["target_top_center"][0], 367, delta=8)

    def test_previous_target_tracks_hidden_pedestal(self):
        folder = DATA / "review" / "20261020_085536"
        if not (folder / "jump_0009_after.png").exists():
            self.skipTest("本机复盘截图未随公开仓库发布")
        before = Image.open(folder / "jump_0009_before.png")
        after = Image.open(folder / "jump_0009_after.png").copy()
        ImageDraw.Draw(after).rectangle((271, 655, 305, 733), fill=after.getpixel((320, 735)))
        initial = observe(before)
        final = observe(after)
        self.assertIsNone(final["current_top_center"])
        recovered = recover_occluded_platform(before, after, initial, final)
        self.assertTrue(recovered["ready"])
        self.assertEqual(recovered["current_center_source"], "tracked_from_previous_frame")
        self.assertAlmostEqual(recovered["current_top_center"][0], 289, delta=8)

    def test_two_real_game_over_layouts(self):
        self.assertEqual(self.scene("capture_20261019_165947_035695700.png")["game_over_variant"], "record")
        self.assertEqual(self.scene("capture_20261019_170220_365732800.png")["game_over_variant"], "normal")

    def test_new_record_overlay_and_side_logo(self):
        folder = DATA / "review" / "20261020_085748"
        if not (folder / "uncertain.png").exists():
            self.skipTest("本机复盘截图未随公开仓库发布")
        self.assertEqual(observe(Image.open(folder / "uncertain.png"))["game_over_variant"], "record")
        before = observe(Image.open(folder / "jump_0111_before.png"))
        self.assertTrue(before["ready"])
        self.assertAlmostEqual(before["target_top_center"][0], 196.5, delta=5)
        self.assertAlmostEqual(before["target_top_center"][1], 537.5, delta=5)

    def test_touching_green_blocks_use_visible_surface_marker(self):
        path = DATA / "review" / "20261020_091713" / "uncertain.png"
        if not path.exists():
            self.skipTest("本机复盘截图未随公开仓库发布")
        state = observe(Image.open(path))
        self.assertTrue(state["ready"])
        self.assertEqual(state["current_center_source"], "pawn_contact_marker_supported")
        self.assertEqual(state["target_center_source"], "white_surface_marker")
        self.assertAlmostEqual(state["target_top_center"][0], 254, delta=3)
        self.assertAlmostEqual(state["target_top_center"][1], 574, delta=3)

    def test_rubik_platform_on_blue_background(self):
        state = self.scene("capture_20261019_172630_828258200.png")
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["pawn_contact"][1], 688, delta=10)
        self.assertAlmostEqual(state["current_top_center"][0], 219, delta=15)
        self.assertAlmostEqual(state["target_top_center"][0], 442, delta=15)

    def test_orange_platform_uses_surface_marker(self):
        state = self.scene("capture_20261019_173022_313391000.png")
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["target_top_center"][0], 388, delta=10)
        self.assertAlmostEqual(state["target_top_center"][1], 583, delta=10)

    def test_yellow_platform_on_yellow_background(self):
        state = self.scene("capture_20261019_173315_807838100.png")
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["target_top_center"][0], 272, delta=10)
        self.assertAlmostEqual(state["target_top_center"][1], 583, delta=10)

    def test_moved_window_pink_pattern_landing(self):
        before = Image.open(DATA / "before_20261019_222140_230560400.png")
        after = Image.open(DATA / "after_20261019_222140_230560400.png")
        first, last = observe(before), observe(after)
        self.assertTrue(last["ready"])
        self.assertAlmostEqual(last["current_top_center"][0], 259, delta=10)
        measured = measure_landing(before, after, first, last)
        self.assertIsNotNone(measured)
        self.assertAlmostEqual(measured["distance"], 240, delta=12)

    def test_small_blue_bottle_target(self):
        state = self.scene("capture_20261019_223006_093063900.png")
        self.assertTrue(state["ready"])
        self.assertAlmostEqual(state["target_top_center"][0], 423, delta=8)
        self.assertAlmostEqual(state["target_top_center"][1], 563, delta=12)

    def test_touching_same_color_platform_uses_marker_without_false_distance(self):
        before = Image.open(DATA / "before_20261019_223136_058282900.png")
        after = Image.open(DATA / "after_20261019_223136_058282900.png")
        first, last = observe(before), observe(after)
        self.assertTrue(last["ready"])
        self.assertIsNone(last["target_geometric_center"])
        self.assertAlmostEqual(last["target_top_center"][0], 388, delta=8)
        self.assertGreater(score_change(before, after)[0], 80)
        self.assertIsNone(measure_landing(before, after, first, last))

    def test_far_brown_platform_landing_is_measured(self):
        before = Image.open(DATA / "before_20261019_225353_976848700.png")
        after = Image.open(DATA / "after_20261019_225353_976848700.png")
        first, last = observe(before), observe(after)
        self.assertTrue(last["ready"])
        self.assertAlmostEqual(last["current_top_center"][0], 246, delta=10)
        measurement = measure_landing(before, after, first, last)
        self.assertIsNotNone(measurement)
        self.assertAlmostEqual(measurement["distance"], 367, delta=12)

    def test_small_roll_landing_is_measured(self):
        before = Image.open(DATA / "before_20261019_225826_906285400.png")
        after = Image.open(DATA / "after_20261019_225826_906285400.png")
        first, last = observe(before), observe(after)
        self.assertTrue(last["ready"])
        self.assertAlmostEqual(last["current_top_center"][0], 185, delta=10)
        measurement = measure_landing(before, after, first, last)
        self.assertIsNotNone(measurement)
        self.assertAlmostEqual(measurement["distance"], 342, delta=12)

    def test_pink_pattern_on_similar_background(self):
        before = Image.open(DATA / "before_20261020_081200_749734200.png")
        after = Image.open(DATA / "after_20261020_081200_749734200.png")
        first, last = observe(before), observe(after)
        self.assertTrue(last["ready"])
        self.assertAlmostEqual(last["current_top_center"][0], 416, delta=10)
        measurement = measure_landing(before, after, first, last)
        self.assertIsNotNone(measurement)
        self.assertAlmostEqual(measurement["distance"], 339, delta=12)

    def test_close_miniature_cylinders(self):
        before = Image.open(DATA / "before_20261020_081849_530222000.png")
        after = Image.open(DATA / "after_20261020_081849_530222000.png")
        first, last = observe(before), observe(after)
        self.assertTrue(last["ready"])
        self.assertAlmostEqual(last["current_top_center"][0], 289, delta=8)
        self.assertAlmostEqual(last["target_top_center"][0], 368, delta=8)
        self.assertLess(abs(last["target_top_center"][0]-last["pawn_contact"][0]), 100)
        measurement = measure_landing(before, after, first, last)
        self.assertIsNotNone(measurement)
        self.assertAlmostEqual(measurement["distance"], 151, delta=12)

    def test_neighboring_green_face_does_not_train_bad_distance(self):
        before = Image.open(DATA / "before_20261020_082229_329411600.png")
        after = Image.open(DATA / "after_20261020_082229_329411600.png")
        first, last = observe(before), observe(after)
        self.assertTrue(last["ready"])
        self.assertIsNone(measure_landing(before, after, first, last))


if __name__ == "__main__":
    unittest.main()
