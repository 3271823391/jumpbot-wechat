"""Build a source-only archive without local game data or personal screenshots."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    ".gitignore", "LICENSE", "README.md", "RESEARCH.md", "ITERATIONS.md",
    "TEST_REPORT.md", "requirements.txt", "start.bat", "pause.bat",
    "resume.bat", "stop.bat", "jumpbot.py", "model.py", "label.py",
    "train_labels.py", "make_review.py", "report.py", "reprocess.py",
    "simulate.py", "package.py",
]


def build():
    output = ROOT / "dist" / "jumpbot-windows-source.zip"
    output.parent.mkdir(exist_ok=True)
    sources = [ROOT / name for name in FILES]
    sources.extend(sorted((ROOT / "tests").glob("test_*.py")))
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"缺少源码文件：{missing}")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sources:
            archive.write(path, (Path("jumpbot-windows") / path.relative_to(ROOT)).as_posix())
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"压缩包校验失败：{bad}")
    return output, len(sources)


if __name__ == "__main__":
    path, count = build()
    print(f"已打包 {count} 个源码文件：{path}")
