# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""画可平铺的传统纹样（灰度：白 = 纹样线，黑 = 底），给着色器当遮罩。
默认出怪化猫四张（麻叶 asanoha、市松 ichimatsu、青海波 seigaiha、七宝 shippo）；--set tang 出唐风四张（宝相花、联珠团窠、卷草、忍冬），那是另一个项目（唐风志异）的，搬过去时一起带走。
输出 web/public/textures/patterns/<name>.png 和一张预览 assets/concept/patterns_preview.png。
用法：uv run tools/patterns.py [--set tang|mononoke]"""
import argparse, math
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web/public/textures/patterns"
OUT.mkdir(parents=True, exist_ok=True)
SS = 2  # 超采样倍数，抗锯齿

def canvas(w, h):
    return Image.new("L", (w * SS, h * SS), 0)

def finish(im, w, h, name):
    im = im.resize((w, h), Image.LANCZOS)
    im.save(OUT / f"{name}.png")
    return im

def line(d, p, q, width):
    d.line([(p[0] * SS, p[1] * SS), (q[0] * SS, q[1] * SS)], fill=255, width=int(width * SS))

def wrapped(fn, w, h):
    """把画法在九个平移位置各画一次，保证边缘能平铺。"""
    for dx in (-w, 0, w):
        for dy in (-h, 0, h):
            fn(dx, dy)

# ---- 麻叶：等边三角形格子，每个三角形从重心连到三个顶点 ----
def asanoha(s=256, width=16):
    h = math.sqrt(3) / 2 * s
    W, H = 4 * s, round(2 * 2 * h)          # 两行三角形为一个纵向周期，取整后纵向拉伸 0.02%，看不出来
    hh = H / 4                              # 实际每行高
    im = canvas(W, H); d = ImageDraw.Draw(im)
    def draw(dx, dy):
        for row in range(-1, 6):
            y0 = row * hh + dy
            off = (s / 2) if row % 2 else 0
            for col in range(-1, 6):
                x0 = col * s + off + dx
                for up in (True, False):      # 一个菱形拆成正立和倒立两个三角形
                    if up: a, b, c = (x0, y0 + hh), (x0 + s, y0 + hh), (x0 + s / 2, y0)
                    else: a, b, c = (x0 + s / 2, y0), (x0 + s * 1.5, y0), (x0 + s, y0 + hh)
                    g = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3)
                    for p, q in ((a, b), (b, c), (c, a)): line(d, p, q, width)
                    for p in (a, b, c): line(d, g, p, width)
    wrapped(draw, W, H)
    return finish(im, W, H, "asanoha"), (W, H)

# ---- 市松：方格 ----
def ichimatsu(n=4, size=1024):
    im = canvas(size, size); d = ImageDraw.Draw(im)
    c = size / n
    for i in range(n):
        for j in range(n):
            if (i + j) % 2 == 0:
                d.rectangle([i * c * SS, j * c * SS, (i + 1) * c * SS - 1, (j + 1) * c * SS - 1], fill=255)
    return finish(im, size, size, "ichimatsu"), (size, size)

# ---- 青海波：成排的同心半圆，后一排盖住前一排的下半 ----
def seigaiha(R=128, rings=4, width=14):
    W, H = 8 * R, 4 * R                     # 横向 4 个圆，纵向 2 行为一个周期；多画一点再裁
    im = canvas(W, H); d = ImageDraw.Draw(im)
    # 只画一遍，行从上往下，下一排的圆底盖住上一排的下半；行列都画出边缘外一截，周期规则，天然可平铺
    for row in range(-2, H // R + 2):
        cy = row * R
        off = R if row % 2 else 0
        for col in range(-2, W // (2 * R) + 2):
            cx = col * 2 * R + off
            d.ellipse([(cx - R) * SS, (cy - R) * SS, (cx + R) * SS, (cy + R) * SS], fill=0)
            for k in range(rings):
                r = R * (1 - k / rings)
                d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], outline=255, width=int(width * SS))
    return finish(im, W, H, "seigaiha"), (W, H)

# ---- 七宝：等半径圆，圆心在棋盘格的同色点上，相邻圆互相穿过对方圆心 ----
def shippo(R=128, width=14):
    P = 2 * R; W = H = 4 * P
    im = canvas(W, H); d = ImageDraw.Draw(im)
    def draw(dx, dy):
        for i in range(-1, 10):
            for j in range(-1, 10):
                if (i + j) % 2: continue
                cx, cy = i * R + dx, j * R + dy
                d.ellipse([(cx - R) * SS, (cy - R) * SS, (cx + R) * SS, (cy + R) * SS], outline=255, width=int(width * SS))
    wrapped(draw, W, H)
    return finish(im, W, H, "shippo"), (W, H)

def polyline(d, pts, width, closed=False):
    pts = [(x * SS, y * SS) for x, y in pts]
    if closed: pts = pts + [pts[0]]
    d.line(pts, fill=255, width=int(width * SS), joint="curve")

def petal(cx, cy, angle, r0, r1, half_w, n=18):
    """从 (cx,cy) 出发沿 angle 方向、半径 r0 到 r1 的尖瓣轮廓点"""
    ca, sa = math.cos(angle), math.sin(angle)
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        r = r0 + (r1 - r0) * t
        w = half_w * math.sin(math.pi * t) ** 0.8
        px, py = cx + ca * r, cy + sa * r
        nx, ny = -sa * w, ca * w
        left.append((px + nx, py + ny)); right.append((px - nx, py - ny))
    return left + right[::-1]

def rosette(d, cx, cy, R, width, layers=((8, 0.0, 0.28, 1.0, 0.2), (8, 22.5, 0.18, 0.62, 0.14)), core=(0.12, 0.05)):
    for n, off, r0, r1, hw in layers:
        for k in range(n):
            a = math.radians(off + 360 * k / n)
            polyline(d, petal(cx, cy, a, R * r0, R * r1, R * hw), width, closed=True)
    for cr in core:
        r = R * cr
        d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], outline=255, width=int(width * SS))

# ---- 宝相花：正中一朵大团花（两层尖瓣 + 花心），四角各一朵小团花（跨边平铺） ----
def baoxianghua(size=1024, width=14):
    im = canvas(size, size); d = ImageDraw.Draw(im)
    rosette(d, size / 2, size / 2, size * 0.44, width)
    wrapped(lambda dx, dy: rosette(d, dx, dy, size * 0.17, width, layers=((8, 0.0, 0.3, 1.0, 0.22),), core=(0.14,)), size, size)
    return finish(im, size, size, "baoxianghua"), (size, size)

# ---- 联珠团窠：一圈珠子围一个团窠，窠内四瓣花，四角小四瓣花 ----
def lianzhu(size=1024, width=12, pearls=24):
    im = canvas(size, size); d = ImageDraw.Draw(im)
    cx = cy = size / 2; R = size * 0.40
    for k in range(pearls):
        a = 2 * math.pi * k / pearls
        px, py = cx + math.cos(a) * R, cy + math.sin(a) * R; pr = size * 0.022
        d.ellipse([(px - pr) * SS, (py - pr) * SS, (px + pr) * SS, (py + pr) * SS], fill=255)
    r2 = R - size * 0.06
    d.ellipse([(cx - r2) * SS, (cy - r2) * SS, (cx + r2) * SS, (cy + r2) * SS], outline=255, width=int(width * SS))
    rosette(d, cx, cy, size * 0.27, width, layers=((4, 45.0, 0.2, 1.0, 0.36), (4, 0.0, 0.12, 0.55, 0.18)), core=(0.1,))
    wrapped(lambda dx, dy: rosette(d, dx, dy, size * 0.11, width, layers=((4, 45.0, 0.2, 1.0, 0.4),), core=(0.15,)), size, size)
    return finish(im, size, size, "lianzhu"), (size, size)

def spiral(cx, cy, r_max, turns, a0, n=60, sign=1):
    pts = []
    for i in range(n + 1):
        t = i / n
        a = a0 + sign * 2 * math.pi * turns * t
        r = r_max * t
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts

# ---- 卷草：一条起伏的藤，波峰波谷各卷一个大螺旋，螺旋里长一片叶，藤上点小芽 ----
def juancao(W=1024, H=512, width=16):
    im = canvas(W, H); d = ImageDraw.Draw(im)
    def wave_y(x): return H / 2 + H * 0.16 * math.sin(2 * math.pi * x / W)
    def draw(dx, dy):
        polyline(d, [(x + dx, wave_y(x) + dy) for x in range(-40, W + 41, 8)], width)
        for x0, sign in ((W * 0.25, -1), (W * 0.75, 1)):   # sign -1：螺旋在藤上方；+1：下方
            bx, by = x0 + dx, wave_y(x0) + dy
            cx, cy = bx + sign * W * 0.04, by + sign * H * 0.27
            # 从藤上分出一段弧线接到螺旋外圈，再往里卷
            pts = spiral(cx, cy, H * 0.26, 1.75, math.radians(90 * sign), sign=-sign)
            polyline(d, [(bx, by)] + pts[::-1], width)
            # 叶子：从螺旋中心斜着伸出去，尖瓣形
            leaf = petal(cx, cy, math.radians(-150 if sign < 0 else 30), H * 0.05, H * 0.30, H * 0.075)
            polyline(d, leaf, width * 0.75, closed=True)
            # 小芽：藤上另一侧点一颗
            ax, ay = x0 + dx + W * 0.12, wave_y(x0 + W * 0.12) + dy - sign * H * 0.09
            d.ellipse([(ax - width) * SS, (ay - width) * SS, (ax + width) * SS, (ay + width) * SS], fill=255)
            polyline(d, [(x0 + dx + W * 0.12, wave_y(x0 + W * 0.12) + dy), (ax, ay)], width * 0.7)
    wrapped(draw, W, H)
    return finish(im, W, H, "juancao"), (W, H)

# ---- 忍冬：藤上交替向上、向下张开的掌状叶（忍冬纹的半叶形），每叶五片尖瓣扇形展开 ----
def rendong(W=1024, H=512, width=13):
    im = canvas(W, H); d = ImageDraw.Draw(im)
    def wave_y(x): return H / 2 + H * 0.10 * math.sin(2 * math.pi * x / W)
    def draw(dx, dy):
        polyline(d, [(x + dx, wave_y(x) + dy) for x in range(-40, W + 41, 8)], width)
        for x0, up in ((W * 0.25, True), (W * 0.75, False)):
            bx, by = x0 + dx, wave_y(x0) + dy
            base = math.radians(-90) if up else math.radians(90)
            for k in range(-2, 3):
                ang = base + k * math.radians(27)
                L = H * (0.40 - 0.06 * abs(k))
                polyline(d, petal(bx, by, ang, H * 0.04, L, H * (0.065 - 0.008 * abs(k))), width * 0.85, closed=True)
            r = width * 1.2
            d.ellipse([(bx - r) * SS, (by - r) * SS, (bx + r) * SS, (by + r) * SS], fill=255)
    wrapped(draw, W, H)
    return finish(im, W, H, "rendong"), (W, H)

SETS = {
    "tang": [("baoxianghua", baoxianghua), ("lianzhu", lianzhu), ("juancao", juancao), ("rendong", rendong)],
    "mononoke": [("asanoha", asanoha), ("ichimatsu", ichimatsu), ("seigaiha", seigaiha), ("shippo", shippo)],
}

def main():
    p = argparse.ArgumentParser(); p.add_argument("--set", default="tang", choices=SETS); args = p.parse_args()
    names = [n for n, _ in SETS[args.set]]
    outs = [fn() for _, fn in SETS[args.set]]
    # 预览：每张 2x2 平铺，检查接缝
    cell = 400
    sheet = Image.new("L", (cell * 4, cell), 0)
    for i, (im, (w, h)) in enumerate(outs):
        t = im.resize((cell // 2, int(cell // 2 * h / w)))
        for a in range(2):
            for b in range(3):
                sheet.paste(t, (i * cell + a * t.width, b * t.height))
    sheet = sheet.crop((0, 0, cell * 4, cell))
    sheet.save(ROOT / ("assets/concept/patterns_preview.png" if args.set == "tang" else "assets/concept/patterns_preview_mononoke.png"))
    for name, (_, (w, h)) in zip(names, outs):
        print(name, w, h, "aspect", round(h / w, 4))

if __name__ == "__main__":
    main()
