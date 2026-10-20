"""Click target landing centers in saved full game screenshots."""
from __future__ import annotations

import argparse
import json
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent
LABELS = ROOT / "data" / "target_labels.jsonl"


def main():
    parser = argparse.ArgumentParser(description="人工标注目标方块最佳落点")
    parser.add_argument("images", nargs="*", type=Path, help="待标注的完整截图")
    parser.add_argument("--all", action="store_true", help="标注所有保存的跳前截图")
    args = parser.parse_args()
    review = ROOT / "data" / "review"
    if args.images:
        paths = args.images
    elif args.all:
        paths = sorted(review.glob("*/jump_*_before.png"))
    else:
        paths = []
        for log in sorted(review.glob("*/jumps.jsonl")):
            for line in log.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if "before" not in row:
                    continue
                target = row.get("initial", {}).get("target_top_center")
                geometry = row.get("initial", {}).get("target_geometric_center")
                discrepancy = (max(abs(a-b) for a, b in zip(target, geometry))
                               if target and geometry else 0)
                error = abs((row.get("measurement") or {}).get("landing_error") or 0)
                if (row.get("outcome") not in ("success_measured",) or
                        discrepancy > 20 or error > 12):
                    paths.append(log.parent / row["before"])
    paths = [p.resolve() for p in paths if p.is_file()]
    if not args.images and LABELS.exists():
        labeled = {Path(json.loads(line)["image"]).resolve()
                   for line in LABELS.read_text(encoding="utf-8").splitlines()}
        paths = [p for p in paths if p not in labeled]
    if not paths:
        raise SystemExit("没有找到截图。可传入一张或多张图片路径。")

    root = tk.Tk()
    root.title("跳一跳中心标注：左键标注，N 跳过，Q 退出")
    canvas = tk.Canvas(root, highlightthickness=0)
    canvas.pack()
    status = tk.Label(root, text="")
    status.pack()
    index = 0
    scale = 1.0
    photo = None

    def show():
        nonlocal scale, photo
        if index >= len(paths):
            root.destroy()
            return
        image = Image.open(paths[index]).convert("RGB")
        scale = min(1.0, (root.winfo_screenwidth() - 100) / image.width,
                    (root.winfo_screenheight() - 150) / image.height)
        shown = image.resize((round(image.width * scale), round(image.height * scale)))
        photo = ImageTk.PhotoImage(shown)
        canvas.configure(width=shown.width, height=shown.height)
        canvas.delete("all")
        canvas.create_image(0, 0, image=photo, anchor="nw")
        status.configure(text=f"{index + 1}/{len(paths)}  {paths[index].name}  |  点击目标顶部最佳落点；N 跳过；Q 退出")

    def mark(event):
        nonlocal index
        image = Image.open(paths[index])
        x, y = event.x / scale, event.y / scale
        if not (0 <= x < image.width and 0 <= y < image.height):
            return
        LABELS.parent.mkdir(exist_ok=True)
        row = {"image": str(paths[index]), "target_center": [round(x, 2), round(y, 2)],
               "image_size": [image.width, image.height], "labeled_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with LABELS.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        index += 1
        show()

    def skip(_event=None):
        nonlocal index
        index += 1
        show()

    canvas.bind("<Button-1>", mark)
    root.bind("n", skip)
    root.bind("q", lambda _event: root.destroy())
    show()
    root.mainloop()
    print(f"标注文件：{LABELS}")


if __name__ == "__main__":
    main()
