# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""把生成图和它的参考帧排成一排，检查风格有没有漂。
用法：uv run tools/lineup.py            → assets/concept/scenes/_lineup.png
      uv run tools/lineup.py --from 13  → 只排 id 序号 >= 13 的（唐风版），输出 _lineup_tang.png
每张 scenes/<id>.png 一行：左边生成图，右边依次是 scenes.json 里的 refs。"""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
spec = json.loads((ROOT / "tools/scenes.json").read_text(encoding="utf-8"))
H, GAP = 420, 16
try:
    font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 22)
except OSError:
    font = ImageFont.load_default()

def fit(p):
    im = Image.open(p).convert("RGB")
    return im.resize((round(im.width * H / im.height), H))

FROM = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 0
rows = []
for s in spec["scenes"]:
    if int(s["id"].split("_")[0]) < FROM:
        continue
    gen = ROOT / "assets/concept/scenes" / f"{s['id']}.png"
    if not gen.exists():
        continue
    ims = [fit(gen)] + [fit(ROOT / r) for r in s["refs"]]
    rows.append((s["id"], ims))
W = max(sum(i.width for i in ims) + GAP * (len(ims) + 1) for _, ims in rows)
sheet = Image.new("RGB", (W, len(rows) * (H + 40) + GAP), "#F1E9DA")
d = ImageDraw.Draw(sheet)
y = GAP
for sid, ims in rows:
    d.text((GAP, y), f"{sid}   左：生成图   右：参考帧", fill="#322D48", font=font)
    x = GAP
    for im in ims:
        sheet.paste(im, (x, y + 32)); x += im.width + GAP
    y += H + 40
out = ROOT / ("assets/concept/scenes/_lineup_tang.png" if FROM else "assets/concept/scenes/_lineup.png")
sheet.save(out); print(out)
