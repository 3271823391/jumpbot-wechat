import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import jumpbot


class StopOnFailureTests(unittest.TestCase):
    def test_auto_saves_game_over_and_returns_without_input(self):
        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(jumpbot, "DATA", Path(folder)),
                  patch.object(jumpbot, "window", return_value=123),
                  patch.object(jumpbot, "capture", return_value=Image.new("RGB", (630, 1160))),
                  patch.object(jumpbot, "observe", return_value={"game_over": True,
                                                                  "title_visible": False}),
                  patch.object(jumpbot.win32gui, "GetForegroundWindow", return_value=123),
                  patch.object(jumpbot.win32api, "GetAsyncKeyState", return_value=0),
                  patch.object(jumpbot, "append") as append,
                  patch.object(jumpbot, "press") as press):
                jumpbot.auto(10)
                press.assert_not_called()
                self.assertEqual(append.call_count, 1)
                self.assertEqual(append.call_args.args[0]["state"], "game_over")
                self.assertEqual(len(list(Path(folder).glob("game_over_*.png"))), 1)


if __name__ == "__main__":
    unittest.main()
