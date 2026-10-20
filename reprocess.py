"""Re-evaluate recorded screenshots after a vision update, preserving raw inputs."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from jumpbot import DATA, observe, measure_landing


def main():
    events_file = DATA / "events.jsonl"
    events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
    samples = []
    for event in events:
        if "actual_press_seconds" not in event:
            continue
        before_path = event.get("before_capture") or event.get("capture")
        after_path = event.get("after_capture")
        if not before_path or not after_path:
            continue
        before = Image.open(before_path)
        after = Image.open(after_path)
        first, last = observe(before), observe(after)
        measurement = measure_landing(before, after, first, last)
        event["before_observation_reprocessed"] = first
        event["after_observation_reprocessed"] = last
        event["measurement"] = measurement
        event["valid_measurement"] = measurement is not None
        event["vision_version"] = 7
        if measurement:
            samples.append(dict(seconds=event["actual_press_seconds"],
                                distance=measurement["distance"],
                                direction=measurement["direction"],
                                screen_width=before.width,
                                confidence=measurement["measurement_confidence"],
                                source="real", event_time=event["time"]))
    events_file.write_text("".join(json.dumps(e, ensure_ascii=False)+"\n" for e in events), encoding="utf-8")
    (DATA / "model.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"重新处理 {len([e for e in events if 'actual_press_seconds' in e])} 次按压，得到 {len(samples)} 个有效距离测量")


if __name__ == "__main__":
    main()
