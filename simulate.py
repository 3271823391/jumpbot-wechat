"""Independent synthetic vision stress test; results never enter the real model."""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from jumpbot import observe

ROOT = Path(__file__).resolve().parent


def scene(rng: random.Random, index: int):
    scale = rng.choice([.75, 1.0, 1.25])
    width, height = round(632*scale), round(1160*scale)
    image = Image.new("RGB", (width, height), (236, 218, 215))
    draw = ImageDraw.Draw(image)
    header = round(66*scale)
    draw.rectangle((0, 0, width, header), fill=(255, 255, 255))
    rightward = index % 2 == 0
    pawn_x = round((200 if rightward else 430)*scale)
    pawn_y = round(700*scale)
    distance = rng.randrange(120, 370)
    target_x = round((pawn_x/scale + (distance if rightward else -distance))*scale)
    target_y = round((pawn_y/scale - rng.randrange(90, 165))*scale)
    target_x = max(round(115*scale), min(width-round(115*scale), target_x))
    target_color = rng.choice([(113, 113, 113), (110, 160, 110), (235, 210, 85)])

    def block(cx, cy, color, shape):
        rx, ry = round(92*scale), round(54*scale)
        if shape == "round":
            draw.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), fill=color)
        else:
            draw.polygon([(cx, cy-ry), (cx+rx, cy), (cx, cy+ry), (cx-rx, cy)], fill=color)
        draw.polygon([(cx-rx, cy), (cx, cy+ry), (cx, cy+ry+round(55*scale)),
                      (cx-rx, cy+round(55*scale))], fill=(87, 87, 87))
        draw.polygon([(cx, cy+ry), (cx+rx, cy), (cx+rx, cy+round(55*scale)),
                      (cx, cy+ry+round(55*scale))], fill=(104, 104, 104))

    block(pawn_x, pawn_y, (113, 113, 113), "diamond")
    block(target_x, target_y, target_color, rng.choice(["diamond", "round"]))
    # Pawn foot is the contact point. The synthetic body uses real screenshot
    # colors but geometry is independently rendered.
    draw.ellipse((pawn_x-round(17*scale), pawn_y-round(92*scale),
                  pawn_x+round(17*scale), pawn_y-round(58*scale)), fill=(49, 43, 78))
    draw.polygon([(pawn_x-round(14*scale), pawn_y-round(56*scale)),
                  (pawn_x+round(14*scale), pawn_y-round(56*scale)),
                  (pawn_x+round(21*scale), pawn_y),
                  (pawn_x-round(21*scale), pawn_y)], fill=(57, 51, 84))
    for _ in range(14):
        px = rng.randrange(20, width-20)
        py = rng.randrange(header+40, height-20)
        draw.ellipse((px-2, py-2, px+2, py+2), fill=(rng.randrange(70, 240), 80, 140))
    return image, (pawn_x, pawn_y), (target_x, target_y)


def main():
    rng = random.Random(20261019)
    rows = []
    for index in range(120):
        image, pawn, target = scene(rng, index)
        state = observe(image)
        pawn_error = float(np.linalg.norm(np.array(state["pawn_contact"])-pawn)) if state["pawn_contact"] else None
        target_error = float(np.linalg.norm(np.array(state["target_top_center"])-target)) if state["target_top_center"] else None
        rows.append({"ready": state["ready"], "pawn_error": pawn_error,
                     "target_error": target_error, "direction": "right" if index % 2 == 0 else "left",
                     "size": image.size})
    result = {"simulated_scenes": len(rows),
              "ready_count": sum(row["ready"] for row in rows),
              "pawn_mean_error": float(np.mean([row["pawn_error"] for row in rows if row["pawn_error"] is not None])),
              "target_mean_error_when_found": float(np.mean([row["target_error"] for row in rows if row["target_error"] is not None])),
              "note": "Synthetic vision scenes only; no game jump or real score is inferred."}
    (ROOT / "data" / "simulation_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
