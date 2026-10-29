# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""把游戏截图和参考帧并排拼一张：uv run tools/shot_compare.py 输出.jpg 截图1 参考1 [截图2 参考2 ...]
每对一行，左截图右参考，统一高度。"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out, pairs = Path(sys.argv[1]), sys.argv[2:]
H, GAP = 480, 14
try: font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 20)
except OSError: font = ImageFont.load_default()
def fit(p):
    im = Image.open(p).convert("RGB"); return im.resize((round(im.width * H / im.height), H))
rows = [(fit(pairs[i]), fit(pairs[i + 1]), Path(pairs[i]).stem, Path(pairs[i + 1]).stem) for i in range(0, len(pairs), 2)]
W = max(a.width + b.width + GAP * 3 for a, b, _, _ in rows)
sheet = Image.new("RGB", (W, len(rows) * (H + 36) + GAP), "#F1E9DA"); d = ImageDraw.Draw(sheet)
y = GAP
for a, b, na, nb in rows:
    d.text((GAP, y), f"游戏：{na}", fill="#322D48", font=font); d.text((GAP * 2 + a.width, y), f"预告片：{nb}", fill="#322D48", font=font)
    sheet.paste(a, (GAP, y + 28)); sheet.paste(b, (GAP * 2 + a.width, y + 28)); y += H + 36
sheet.save(out, quality=90); print(out)
