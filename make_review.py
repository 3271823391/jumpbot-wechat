"""Create an offline browser for separately saved jump screenshots."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVIEW = ROOT / "data" / "review"


def build(folders=None):
    folders = folders or sorted(p for p in REVIEW.iterdir() if (p / "jumps.jsonl").exists())
    jumps = []
    for folder in folders:
        for line in (folder / "jumps.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if "jump" not in row:
                continue
            jumps.append({
                "number": len(jumps) + 1,
                "before": f"{folder.name}/{row['before']}",
                "after": f"{folder.name}/{row['after']}",
                "outcome": row.get("outcome", "unknown"),
                "press": row.get("actual_press_seconds"),
                "error": (row.get("measurement") or {}).get("landing_error"),
                "target": row.get("initial", {}).get("target_top_center"),
                "failure": f"{folder.name}/{row['failure_capture']}" if row.get("failure_capture") else None,
            })
    data = json.dumps(jumps, ensure_ascii=False).replace("</", "<\\/")
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>跳一跳逐跳复盘</title>
<style>body{font-family:system-ui,sans-serif;background:#171b24;color:#f4f5f7;margin:24px}
button,input{font:inherit;padding:8px 12px;margin:4px}button{cursor:pointer}
.screens{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap}.screens img{max-width:46vw;max-height:75vh;object-fit:contain}
.card{background:#252b36;padding:12px;border-radius:10px}#info{margin:12px 0;white-space:pre-wrap}</style>
<h1>跳一跳逐跳复盘</h1><p>每跳的原始前后截图独立保存。左右箭头可切换。</p>
<button onclick="move(-1)">上一跳</button><input id="n" type="number" min="1" onchange="show(+this.value-1)">
<button onclick="move(1)">下一跳</button><span id="count"></span><div id="info"></div>
<div class="screens"><div class="card"><h2>跳前</h2><img id="before"></div>
<div class="card"><h2>跳后</h2><img id="after"></div>
<div class="card" id="failureCard" hidden><h2>最终结算</h2><img id="failure"></div></div>
<script>const jumps=DATA;let index=0;function show(i){index=Math.max(0,Math.min(jumps.length-1,i));
const j=jumps[index];document.getElementById('n').value=index+1;document.getElementById('count').textContent=` / ${jumps.length}`;
document.getElementById('before').src=j.before;document.getElementById('after').src=j.after;
document.getElementById('info').textContent=`第 ${j.number} 跳 | ${j.outcome} | 按压 ${j.press?.toFixed(3)??'?'} 秒 | 落点误差 ${j.error?.toFixed(1)??'未测量'} px | 目标 ${JSON.stringify(j.target)}`;
document.getElementById('failureCard').hidden=!j.failure;if(j.failure)document.getElementById('failure').src=j.failure;}
function move(d){show(index+d)}document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')move(-1);if(e.key==='ArrowRight')move(1)});show(0)</script></html>'''.replace("DATA", data)
    output = REVIEW / "index.html"
    output.write_text(html, encoding="utf-8")
    return output, len(jumps)


if __name__ == "__main__":
    path, count = build()
    print(f"{count} 跳：{path}")
