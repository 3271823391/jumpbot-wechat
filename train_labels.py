"""Build conservative screenshot exemplars from human target-center labels."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
LABELS = ROOT / "data" / "target_labels.jsonl"
MODEL = ROOT / "data" / "center_templates.npz"
PATCH_WIDTH, PATCH_HEIGHT = 96, 70


def train(labels=LABELS, model=MODEL):
    if not labels.exists():
        raise FileNotFoundError(f"尚无人工标注：{labels}")
    patches, widths, sources = [], [], []
    for line in labels.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        path = Path(row["image"])
        if not path.is_file():
            continue
        image = cv2.cvtColor(np.asarray(Image.open(path).convert("RGB")), cv2.COLOR_RGB2GRAY)
        x, y = (round(v) for v in row["target_center"])
        x0, y0 = x - PATCH_WIDTH // 2, y - PATCH_HEIGHT // 2
        if x0 < 0 or y0 < 0 or x0 + PATCH_WIDTH > image.shape[1] or y0 + PATCH_HEIGHT > image.shape[0]:
            continue
        patch = image[y0:y0 + PATCH_HEIGHT, x0:x0 + PATCH_WIDTH]
        # A blank near-white surface carries no unique texture or edge cues.
        if patch.std() < 8:
            continue
        patches.append(patch)
        widths.append(image.shape[1])
        sources.append(str(path))
    if not patches:
        raise ValueError("标注中没有足够清晰的可训练样本")
    model.parent.mkdir(exist_ok=True)
    np.savez_compressed(model, patches=np.stack(patches), widths=np.array(widths),
                        sources=np.array(sources))
    return len(patches)


if __name__ == "__main__":
    count = train()
    print(f"已训练 {count} 个样本：{MODEL}")
