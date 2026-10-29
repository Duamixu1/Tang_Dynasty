# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""按 docs/02 的 12 色画色板图（也作为生图参考）。

  uv run tools/palette.py            唐风版 → assets/concept/00_色板.png（现行）
  uv run tools/palette.py --set tang   唐风版 → assets/concept/00_色板_唐风.png（另一个项目的，搬家时带走）
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    "tang": {
        "title": "ZHIYI (Tang) · 12-colour palette",
        "out": "assets/concept/00_色板.png",
        "colors": [
            ("01 铅白 silk cream", "#EFE4CC"), ("02 朱砂 vermilion", "#D9503C"), ("03 土红 earth red", "#9C3A2F"),
            ("04 金 gold", "#D7A54A"), ("05 石绿 malachite", "#5FA07A"), ("06 石青 azurite", "#3A5BA0"),
            ("07 绛紫 purple", "#74457A"), ("08 赭石 ochre brown", "#A0623A"), ("09 墨 lacquer black", "#2E2723"),
            ("10 铅粉 skin", "#F3DCC8"), ("11 胭脂 rouge", "#E48C92"), ("12 赭墨 outline", "#4A2C1E"),
        ],
    },
    "mononoke": {
        "title": "MONONOKE fan game · 12-colour palette",
        "out": "assets/concept/00_色板_怪化猫.png",
        "colors": [
            ("01 生成り paper", "#F1E9DA"), ("02 珊瑚 coral", "#E6667A"), ("03 深紅 crimson", "#B42A47"),
            ("04 山吹 ochre gold", "#DCC67C"), ("05 萌葱 green", "#59B86A"), ("06 青磁 teal", "#49B3A6"),
            ("07 藍 indigo blue", "#4F74BF"), ("08 藤 wisteria", "#6A4C8C"), ("09 濃紺 navy", "#2A2A4E"),
            ("10 白藤 pale lavender", "#D6D3EF"), ("11 鴇 pink", "#E7A3B5"), ("12 墨 outline ink", "#322D48"),
        ],
    },
}
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", default="tang", choices=SETS)
    args = p.parse_args()
    s = SETS[args.set]
    palette, paper, ink = s["colors"], s["colors"][0][1], s["colors"][-1][1]
    cols, sw, sh, pad = 6, 300, 260, 24
    rows = (len(palette) + cols - 1) // cols
    W, H = cols * sw + pad * 2, rows * sh + pad * 2 + 70
    im = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(im)
    try:
        f_big, f_small, f_title = ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT, 22), ImageFont.truetype(FONT, 34)
    except OSError:
        f_big = f_small = f_title = ImageFont.load_default()
    d.text((pad, pad), s["title"], fill=ink, font=f_title)
    for i, (name, hx) in enumerate(palette):
        x, y = pad + (i % cols) * sw, pad + 70 + (i // cols) * sh
        d.rectangle([x + 10, y + 10, x + sw - 10, y + sh - 70], fill=hx, outline=ink, width=3)
        d.text((x + 12, y + sh - 60), name, fill=ink, font=f_big)
        d.text((x + 12, y + sh - 30), hx, fill=ink, font=f_small)
    out = ROOT / s["out"]
    im.save(out)
    print(out)

if __name__ == "__main__":
    main()
