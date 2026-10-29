# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""把 assets/concept/scenes/34_画壁_证物图标.png（4x2 格：E1 幞头、E2 壁上的人、E3 半首诗、E4 反写题记、E5 金链、E6a 镜中螺髻、E6b 镜中榻下、scale 铜镜）裁成单个图标 → web/public/icons/<id>.png（256px）。"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets/concept/scenes/34_画壁_证物图标.png"
OUT = ROOT / "web/public/icons"; OUT.mkdir(parents=True, exist_ok=True)
IDS = ["E1", "E2", "E3", "E4", "E5", "E6a", "E6b", "scale"]
im = Image.open(SRC).convert("RGB")
cols, rows = 4, 2
cw, ch = im.width // cols, im.height // rows
inset = 10   # 去掉格线
for i, id_ in enumerate(IDS):
    x, y = (i % cols) * cw, (i // cols) * ch
    tile = im.crop((x + inset, y + inset, x + cw - inset, y + ch - inset)).resize((256, 256), Image.LANCZOS)
    tile.save(OUT / f"{id_}.png")
    print(id_, OUT / f"{id_}.png")
