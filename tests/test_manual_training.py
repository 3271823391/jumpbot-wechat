import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

import jumpbot
from train_labels import train


class ManualTrainingTests(unittest.TestCase):
    def test_label_trains_a_reusable_target_template(self):
        image_path = Path(__file__).resolve().parents[1] / "data" / "review" / "20261020_085748" / "jump_0111_before.png"
        if not image_path.exists():
            self.skipTest("本机复盘截图未随公开仓库发布")
        with tempfile.TemporaryDirectory() as folder:
            labels = Path(folder) / "labels.jsonl"
            model = Path(folder) / "centers.npz"
            labels.write_text(json.dumps({"image": str(image_path),
                                          "target_center": [196.5, 537.5]}) + "\n", encoding="utf-8")
            self.assertEqual(train(labels, model), 1)
            with patch.object(jumpbot, "CENTER_TEMPLATES", model):
                actual = jumpbot.trained_center(np.asarray(Image.open(image_path).convert("RGB")),
                                                [196.5, 537.5], [460, 699])
                wrong_side = jumpbot.trained_center(np.asarray(Image.open(image_path).convert("RGB")),
                                                    [248.8, 572.3], [460, 699])
            self.assertIsNotNone(actual)
            self.assertIsNone(wrong_side)
            self.assertAlmostEqual(actual[0], 196.5, delta=2)
            self.assertAlmostEqual(actual[1], 537.5, delta=2)


if __name__ == "__main__":
    unittest.main()
