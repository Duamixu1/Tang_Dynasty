# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "numpy"]
# ///
"""绢壁纸纹：给 post.js 的屏幕空间叠加用（灰度，0.5 为中性；亮处往纸白提，暗处压暗）。

  uv run tools/paper.py            → web/public/textures/paper.png（1024，可平铺）+ assets/concept/paper_preview.png（和旧和纸并排）

三层叠出来：
  1. 细颗粒：矿物颜料在绢上的粗糙感，比和纸的揉皱细得多（两种频率的噪声叠加）
  2. 淡裂纹：壁画的龟裂，用 Voronoi 单元的边界画细线，很淡
  3. 零星剥落：少量不规则小块稍亮一点（露出泥底的感觉由色相来，这里只给亮度）
旧和纸留在 paper_washi.png，不删。"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web/public/textures/paper.png"
N = 1024
rng = np.random.default_rng(7)


def tile_noise(n, scale, octaves=1):
    """可平铺的平滑噪声：低分辨率随机图放大（双三次），放大前复制边缘保证接缝"""
    acc = np.zeros((n, n), dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        s = max(2, int(scale / (2 ** o)))
        small = rng.random((s, s)).astype(np.float32)
        big = np.array(Image.fromarray((small * 255).astype(np.uint8)).resize((n + n // s, n + n // s), Image.BICUBIC), dtype=np.float32) / 255
        # 用 wrap 的方式：先把小图平铺 2x2 再放大，再裁中间一块，接缝自然连续
        tiled = np.tile(small, (2, 2))
        big = np.array(Image.fromarray((tiled * 255).astype(np.uint8)).resize((2 * n, 2 * n), Image.BICUBIC), dtype=np.float32) / 255
        acc += big[:n, :n] * amp
        total += amp; amp *= 0.5
    return acc / total


def craquelure(n, cells=26, width=1.0):
    """Voronoi 边界线：随机点（平铺到 3x3 保证接缝），每个像素到最近两个点的距离差小的地方是裂纹"""
    pts = rng.random((cells * cells, 2)) * n
    pts += (rng.random(pts.shape) - 0.5) * (n / cells) * 0.0
    pts9 = np.concatenate([pts + np.array([dx, dy]) * n for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    ys, xs = np.mgrid[0:n, 0:n]
    best1 = np.full((n, n), np.inf, dtype=np.float32); best2 = best1.copy()
    for px, py in pts9:
        d = (xs - px) ** 2 + (ys - py) ** 2
        m = d < best1
        best2 = np.where(m, best1, np.minimum(best2, d)); best1 = np.where(m, d, best1)
    gap = np.sqrt(best2) - np.sqrt(best1)
    line = np.clip(1.0 - gap / width, 0, 1)
    # 裂纹不是整张都有：用一张大尺度噪声当遮罩，只在约 40% 的区域出现
    mask = tile_noise(n, 4) > 0.55
    return line * mask


def main():
    grain = tile_noise(N, 512, octaves=3)            # 细颗粒
    grain = (grain - grain.mean()) / (grain.std() + 1e-6) * 0.06
    cloud = tile_noise(N, 8, octaves=2)              # 大面积的深浅不匀（颜料厚薄）
    cloud = (cloud - cloud.mean()) * 0.10
    cracks = craquelure(N, width=1.6) * 0.22        # 淡裂纹，压暗
    flakes = (tile_noise(N, 48, octaves=2) > 0.78).astype(np.float32)
    flakes = np.array(Image.fromarray((flakes * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float32) / 255 * 0.10   # 零星剥落，稍亮
    g = 0.5 + grain + cloud - cracks + flakes
    im = Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8), "L")
    im.save(OUT)
    # 预览：旧和纸 | 新绢壁，各 2x2 平铺一角
    old = Image.open(ROOT / "web/public/textures/paper_washi.png").convert("L").resize((512, 512))
    new = im.resize((512, 512))
    sheet = Image.new("L", (1024 + 16, 512), 128)
    sheet.paste(old, (0, 0)); sheet.paste(new, (528, 0))
    sheet.save(ROOT / "assets/concept/paper_preview.png")
    print(OUT, "预览 assets/concept/paper_preview.png")


if __name__ == "__main__":
    main()
