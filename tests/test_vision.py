import unittest

from PIL import Image, ImageDraw

from jumpbot import observe
from pathlib import Path


class VisionTests(unittest.TestCase):
    def test_rejects_blank_screen(self):
        image = Image.new("RGB", (421, 773), (150, 150, 160))
        self.assertFalse(observe(image)["ready"])

    def test_rejects_clipped_pawn(self):
        image = Image.new("RGB", (421, 773), (150, 150, 160))
        draw = ImageDraw.Draw(image)
        draw.ellipse((400, 450, 440, 520), fill=(34, 26, 54))
        self.assertIsNone(observe(image)["pawn_contact"])

    def test_real_clipped_target_is_not_ready(self):
        image_path = Path(__file__).resolve().parents[1] / "data" / "capture_20261019_163035.png"
        if not image_path.exists():
            self.skipTest("本机真实截图未随公开仓库发布")
        self.assertFalse(observe(Image.open(image_path))["ready"])

    def test_real_splash_detected(self):
        image_path = Path(__file__).resolve().parents[1] / "data" / "capture_20261019_163145.png"
        if not image_path.exists():
            self.skipTest("本机真实截图未随公开仓库发布")
        self.assertTrue(observe(Image.open(image_path))["title_visible"])

    def test_real_skin_page_is_not_gameplay(self):
        image_path = Path(__file__).resolve().parents[1] / "data" / "capture_20261019_163442.png"
        if not image_path.exists():
            self.skipTest("本机真实截图未随公开仓库发布")
        self.assertFalse(observe(Image.open(image_path))["ready"])


if __name__ == "__main__":
    unittest.main()
