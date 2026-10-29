# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "numpy"]
# ///
"""把一张"正 / 侧 / 背"三视图切成三张单图，给 tripo_v2.py 的多视图生成用。

  uv run tools/split_views.py 15_书生_建模三视图 [16_... ...]
  uv run tools/split_views.py 20_金甲使者_三视图:1400,2520     两个视图挨得太近切不开时，手动给两条切线的 x
    → assets/concept/scenes/<id>_split/{front,left,back}.png（每张补成正方形，底色取画面角上的颜色）

按列扫描：和底色差得多的像素算"有东西"，连续的空白列就是分隔。默认取最宽的两条空白把画面切成三段；
切不出正好三段时报错，手动处理。"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "assets/concept/scenes"
NAMES = ["front", "left", "back"]


def split(sheet, cuts=None):
    im = Image.open(sheet).convert("RGB")
    a = np.asarray(im).astype(int)
    bg = np.median(np.concatenate([a[:20, :20].reshape(-1, 3), a[:20, -20:].reshape(-1, 3)]), axis=0)
    diff = np.abs(a - bg).sum(axis=2)
    h = a.shape[0]
    body = diff[: int(h * 0.93)]                # 底部的地平线不算，它横贯整张
    col_has = (body > 60).sum(axis=0) > body.shape[0] * 0.01
    # 找空白段
    gaps, start = [], None
    for x, has in enumerate(col_has):
        if not has and start is None: start = x
        if has and start is not None: gaps.append((start, x)); start = None
    if start is not None: gaps.append((start, len(col_has)))
    if cuts is None:
        inner = [g for g in gaps if g[0] > 0 and g[1] < len(col_has)]
        inner.sort(key=lambda g: g[1] - g[0], reverse=True)
        if len(inner) < 2:
            raise SystemExit(f"{sheet.name}: 只找到 {len(inner)} 条分隔，切不成三段，用 id:x1,x2 手动切")
        cuts = sorted(((g[0] + g[1]) // 2 for g in inner[:2]))
    edges = [0, *cuts, a.shape[1]]
    out = SCENES / f"{sheet.stem}_split"; out.mkdir(exist_ok=True)
    for name, x0, x1 in zip(NAMES, edges, edges[1:]):
        part = im.crop((x0, 0, x1, h))
        # 去掉四周空白再补成正方形，三张的比例才一致
        d = diff[:, x0:x1] > 60
        ys, xs = np.where(d[: int(h * 0.93)])
        part = part.crop((max(xs.min() - 40, 0), max(ys.min() - 40, 0), min(xs.max() + 40, part.width), min(ys.max() + 40, h)))
        s = max(part.size)
        sq = Image.new("RGB", (s, s), tuple(int(c) for c in bg))
        sq.paste(part, ((s - part.width) // 2, (s - part.height) // 2))
        sq.save(out / f"{name}.png")
    print(out, [e for e in edges])


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        sid, _, manual = arg.partition(":")
        split(SCENES / f"{sid}.png", [int(x) for x in manual.split(",")] if manual else None)
