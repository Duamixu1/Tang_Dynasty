"""
给 Tripo 角色换一张高清脸：把 2D 头部正视图（scenes/37_书生_头部三视图 的正面）正面投影到现有的头上。

为什么：整身生成时脸在 2048 贴图里只分到约 300×360 像素，一只眼 18 像素左右，眼线、金瞳、镜钿全糊。
做法：
  1. 在旧贴图上给出四个点的像素位置（两眼、眉心、嘴），找到它们在 3D 模型上的位置
  2. 在 2D 正视图上给出同样四个点，求"3D 正面投影 → 图片像素"的缩放 + 平移（x、y 各自一组）
  3. 选出脸那片面：头部骨骼权重 > 0.5、法线朝前、四个角都落在 2D 脸的肤色区内、旧贴图上不是黑帽子
  4. 这片面换成单独的材质 + 单独一张脸贴图（从 2D 正视图裁出来，肤色按旧贴图校一下，区外补成肤色），UV 按投影重写
  骨骼、蒙皮、动作原样导出。

  Blender -b --python tools/blender_face_decal.py -- \
      --in assets/processed/scholar_v3_lite.glb --out assets/processed/scholar_v3_lite.glb \
      --sheet assets/concept/scenes/37_书生_头部三视图.png \
      --tex-landmarks 1552,744 1551,836 1597.5,791 1480,789 \
      --img-landmarks 506.9,966.5 919.5,968.4 716.1,782.4 717.9,1326.8 \
      --crop 230,430,1200,1600 [--min-facing 0.3] [--preview 目录]
  两组 landmarks 的顺序都是：眼、眼、眉心、嘴（两只眼谁左谁右不用管，按投影后的左右自动配对）
"""
import argparse, os, sys
import bpy, bmesh
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument("--in", dest="inp", required=True)
p.add_argument("--out", required=True)
p.add_argument("--sheet", required=True)
p.add_argument("--tex-landmarks", nargs=4, required=True)
p.add_argument("--img-landmarks", nargs=4, required=True)
p.add_argument("--crop", required=True, help="x0,y0,x1,y1：2D 正视图里脸贴图要裁的范围（像素）")
p.add_argument("--tex-size", type=int, default=1024)
p.add_argument("--min-facing", type=float, default=0.3)
p.add_argument("--preview")
a = p.parse_args(argv)
pt = lambda s: tuple(float(x) for x in s.split(","))
tex_lm = [pt(s) for s in a.tex_landmarks]
img_lm = [pt(s) for s in a.img_landmarks]
cx0, cy0, cx1, cy1 = (int(x) for x in a.crop.split(","))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a.inp)
obj = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.polygons))
me = obj.data
mw = obj.matrix_world
base_mat = me.materials[0]
base_img = next(n.image for n in base_mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image)
TW, TH = base_img.size
atlas = np.array(base_img.pixels[:], dtype=np.float32).reshape(TH, TW, 4)[..., :3]   # 行 0 在底部（v=0）
uvl = me.uv_layers.active.data


def tex_to_uv(x, y):            # 图片像素（行 0 在顶部）→ UV
    return ((x + 0.5) / TW, 1 - (y + 0.5) / TH)


def uv_to_atlas(u, v):
    return atlas[min(TH - 1, max(0, int(v * TH))), min(TW - 1, max(0, int(u * TW)))]


# ---- 1. 旧贴图上的四个点 → 3D 位置（在三角形里按 UV 求重心坐标）----
me.calc_loop_triangles()
co = np.array([mw @ v.co for v in me.vertices])
tris = [(t.loops[:], t.vertices[:]) for t in me.loop_triangles]
L = np.array([[uvl[l].uv[:] for l in loops] for loops, _ in tris])     # (T,3,2)
V = np.array([vs for _, vs in tris])


def locate(u, v):
    A, B, C = L[:, 0], L[:, 1], L[:, 2]
    v0, v1, v2 = B - A, C - A, np.array([u, v]) - A
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = den > 1e-14                                                    # UV 里退化成线的三角形不算
    den = np.where(ok, den, 1.0)
    bv = (d11 * d20 - d01 * d21) / den; bw = (d00 * d21 - d01 * d20) / den; bu = 1 - bv - bw
    inside = ok & (bu >= -1e-4) & (bv >= -1e-4) & (bw >= -1e-4)
    if not inside.any():
        raise SystemExit(f"UV ({u:.4f},{v:.4f}) 不在任何三角形里")
    i = np.nonzero(inside)[0][0]
    return co[V[i, 0]] * bu[i] + co[V[i, 1]] * bv[i] + co[V[i, 2]] * bw[i]


P3 = np.array([locate(*tex_to_uv(*xy)) for xy in tex_lm])

# ---- 2. 正面方向 + 投影拟合 ----
gi = obj.vertex_groups["Head"].index
head_w = np.zeros(len(me.vertices))
for v in me.vertices:
    for g in v.groups:
        if g.group == gi: head_w[v.index] = g.weight
head_c = co[head_w > 0.5].mean(0)
up = np.array([0, 0, 1.0])
fwd = P3.mean(0) - head_c; fwd -= up * fwd.dot(up); fwd /= np.linalg.norm(fwd)
right = np.cross(up, fwd)                                               # 从正面看过去的画面右方
S = np.stack([co @ right, co @ up], 1)                                  # 每个顶点的正面投影
S_lm = np.stack([P3 @ right, P3 @ up], 1)
# 两只眼按投影左右配对：画面左边那只对 2D 里 x 小的那只
img = np.array(img_lm)
if (S_lm[0, 0] > S_lm[1, 0]) != (img[0, 0] > img[1, 0]):
    img[[0, 1]] = img[[1, 0]]
ax, bx = np.polyfit(S_lm[:, 0], img[:, 0], 1)
ay, by = np.polyfit(S_lm[:, 1], img[:, 1], 1)
proj = np.stack([S[:, 0] * ax + bx, S[:, 1] * ay + by], 1)               # 每个顶点在 2D 正视图上的像素位置
fit = np.stack([S_lm[:, 0] * ax + bx, S_lm[:, 1] * ay + by], 1)
print("[face] 3D 四点", np.round(P3, 4).tolist())
print("[face] 拟合误差（像素）", np.round(np.linalg.norm(fit - img, axis=1), 1).tolist(), f"比例 x {ax:.0f} y {ay:.0f} px/m")

# ---- 3. 2D 正视图上的脸部肤色区（从眉心往外长，逐行补洞：眼、眉、镜钿都包进来）----
sheet = bpy.data.images.load(os.path.abspath(a.sheet))
SW, SH = sheet.size
sp = np.array(sheet.pixels[:], dtype=np.float32).reshape(SH, SW, 4)[::-1, :, :3]   # 翻成行 0 在顶部
crop = sp[cy0:cy1, cx0:cx1]
r, g, b = crop[..., 0], crop[..., 1], crop[..., 2]
lum = 0.299 * r + 0.587 * g + 0.114 * b
skin = (lum > 0.72) & (r >= g) & (g >= b) & (r - b > 0.05) & (r - b < 0.30)
k = 4                                                                   # 1/4 分辨率上长区域，快
sm = skin[::k, ::k]
sy, sx = ((img[0, 1] + img[3, 1]) / 2 - cy0) / k, (img[2, 0] - cx0) / k  # 鼻梁中段（眉心本身是镜钿，不是肤色）
cand = np.argwhere(sm)
seed = tuple(cand[np.argmin(((cand - [sy, sx]) ** 2).sum(1))])          # 离它最近的肤色点
region = np.zeros_like(sm); region[seed] = True
for _ in range(400):
    grown = region.copy()
    grown[1:] |= region[:-1]; grown[:-1] |= region[1:]; grown[:, 1:] |= region[:, :-1]; grown[:, :-1] |= region[:, 1:]
    grown &= sm
    if (grown == region).all(): break
    region = grown
chin_y = (img[3, 1] - cy0) + 0.55 * (img[3, 1] - img[2, 1])               # 嘴往下约半个"眉心到嘴"就是下巴
mask_s = region.copy()
for y in range(mask_s.shape[0]):                                        # 逐行补洞
    xs = np.nonzero(region[y])[0]
    if len(xs): mask_s[y, xs.min():xs.max() + 1] = True
    if y * k > chin_y: mask_s[y] = False
mask = np.repeat(np.repeat(mask_s, k, 0), k, 1)[:crop.shape[0], :crop.shape[1]]
# 收进来几像素，边上那圈面留给旧贴图（脸轮廓线也在旧贴图那边）
er = mask.copy()
for _ in range(3):
    er[1:] &= mask[:-1]; er[:-1] &= mask[1:]; er[:, 1:] &= mask[:, :-1]; er[:, :-1] &= mask[:, 1:]; mask = er.copy()


def in_mask(px, py):
    x, y = int(px - cx0), int(py - cy0)
    return 0 <= x < mask.shape[1] and 0 <= y < mask.shape[0] and mask[y, x]


# ---- 4. 选面 ----
face_polys = []
fwd_v = Vector(fwd)
nmat = mw.to_3x3().inverted().transposed()
cnt = [0, 0, 0, 0]
for poly in me.polygons:
    vs = poly.vertices
    if head_w[list(vs)].min() < 0.5: continue
    cnt[0] += 1
    if (nmat @ poly.normal).normalized().dot(fwd_v) < a.min_facing: continue
    cnt[1] += 1
    if not all(in_mask(*proj[v]) for v in vs): continue
    cnt[2] += 1
    u, v = np.mean([uvl[l].uv[:] for l in poly.loop_indices], 0)
    c = uv_to_atlas(u, v)
    # 旧贴图上是黑的、又在眉心以上（靠帽檐）：是帽子，不动。眉心以下的深色是旧的眼睛眉毛，要换掉
    if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] < 0.3 and proj[list(vs)][:, 1].mean() < img[2, 1]: continue
    cnt[3] += 1
    face_polys.append(poly.index)
print(f"[face] 筛选：头部 {cnt[0]} → 朝前 {cnt[1]} → 在脸区内 {cnt[2]} → 不是黑帽 {cnt[3]}；脸区 {int(mask.sum())} 像素")
# 脸区外、朝前的头部和脖子肤色面：统一涂成纯肤色（脸贴图角上那块），盖掉旧贴图的眼线残迹，阴影也和新脸一致。耳朵朝侧面，不动
neck_w = np.zeros(len(me.vertices))
for name in ("NeckTwist01", "NeckTwist02"):
    if name in obj.vertex_groups:
        ni = obj.vertex_groups[name].index
        for v in me.vertices:
            for g in v.groups:
                if g.group == ni: neck_w[v.index] = max(neck_w[v.index], g.weight)
fs0 = set(face_polys)
plain_polys = []
for poly in me.polygons:
    if poly.index in fs0: continue
    vs = list(poly.vertices)
    is_head, is_neck = head_w[vs].min() >= 0.5, neck_w[vs].min() >= 0.5
    if not (is_head or is_neck): continue
    if (nmat @ poly.normal).normalized().dot(fwd_v) < 0.3: continue
    u, v = np.mean([uvl[l].uv[:] for l in poly.loop_indices], 0)
    c = uv_to_atlas(u, v); lum_c = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    if is_head and lum_c < 0.35: continue                               # 帽子、幞头脚：深色一律不动
    if is_neck and not (lum_c > 0.65 and c[0] >= c[1] >= c[2]): continue  # 脖子只换肤色，不碰领口
    if is_head and not (c[0] >= c[1] - 0.02): continue                 # 头上偏蓝偏绿的（领口、袍子）不碰
    plain_polys.append(poly.index)
print(f"[face] 脸区外换成纯肤色的面：{len(plain_polys)}")
print(f"[face] 换成高清脸的面：{len(face_polys)}")
if len(face_polys) < 50:
    raise SystemExit("选到的面太少，检查 landmarks 和 --crop")

# ---- 5. 脸贴图：裁 2D，肤色按旧贴图校，区外补肤色 ----
fs = set(face_polys)
old_cols = np.array([uv_to_atlas(*np.mean([uvl[l].uv[:] for l in me.polygons[i].loop_indices], 0)) for i in face_polys])
old_lum = old_cols @ np.array([0.299, 0.587, 0.114])
atlas_skin = np.median(old_cols[old_lum > 0.7], 0)                     # 只拿旧贴图上本来就是肤色的面估肤色
img_skin = np.median(crop[mask & skin], 0)
gain = atlas_skin / np.maximum(img_skin, 1e-3)
out = crop.copy()
w = np.clip((lum - 0.55) / 0.2, 0, 1)[..., None] * skin[..., None]     # 只校肤色，线条和金瞳不动
out = out * (1 - w) + out * gain * w
out[~mask] = atlas_skin
print("[face] 肤色 2D", np.round(img_skin * 255).tolist(), "→ 旧贴图", np.round(atlas_skin * 255).tolist())
N = a.tex_size
fimg = bpy.data.images.new("scholar_face", N, N, alpha=False)
ys = (np.arange(N) * out.shape[0] / N).astype(int); xs = (np.arange(N) * out.shape[1] / N).astype(int)
small = out[ys][:, xs]
px = np.concatenate([small[::-1], np.ones((N, N, 1), np.float32)], 2)  # 翻回行 0 在底部
fimg.pixels[:] = px.ravel()
fimg.pack()

# ---- 6. 新材质 + 改写这片面的 UV ----
fmat = base_mat.copy(); fmat.name = "scholar_face"
for n in fmat.node_tree.nodes:
    if n.type == "TEX_IMAGE" and n.image == base_img: n.image = fimg
me.materials.append(fmat)
fi = len(me.materials) - 1
for i in face_polys:
    poly = me.polygons[i]; poly.material_index = fi
    for l in poly.loop_indices:
        vx, vy = proj[me.loops[l].vertex_index]
        uvl[l].uv = ((vx - cx0) / (cx1 - cx0), 1 - (vy - cy0) / (cy1 - cy0))
for i in plain_polys:                                                   # 脸贴图左上角：2D 里是帽子，区外已补成肤色
    poly = me.polygons[i]; poly.material_index = fi
    for l in poly.loop_indices: uvl[l].uv = (0.02, 0.98)

if a.preview:
    os.makedirs(a.preview, exist_ok=True)
    fimg.filepath_raw = os.path.join(a.preview, "face_tex.png"); fimg.file_format = "PNG"; fimg.save()
    dbg = (np.stack([mask] * 3, -1) * 0.5 + crop * 0.5)
    for i in face_polys:
        for v in me.polygons[i].vertices:
            x, y = proj[v]; x, y = int(x - cx0), int(y - cy0)
            if 0 <= x < dbg.shape[1] and 0 <= y < dbg.shape[0]: dbg[y, x] = (0, 1, 0)
    for x, y in img: dbg[max(0, int(y - cy0) - 3):int(y - cy0) + 3, max(0, int(x - cx0) - 3):int(x - cx0) + 3] = (1, 0, 0)
    for x, y in fit: dbg[max(0, int(y - cy0) - 3):int(y - cy0) + 3, max(0, int(x - cx0) - 3):int(x - cx0) + 3] = (0, 0, 1)
    di = bpy.data.images.new("dbg", dbg.shape[1], dbg.shape[0], alpha=False)
    di.pixels[:] = np.concatenate([dbg[::-1], np.ones(dbg.shape[:2] + (1,), np.float32)], 2).ravel()
    di.filepath_raw = os.path.join(a.preview, "face_select.png"); di.file_format = "PNG"; di.save()

bpy.ops.export_scene.gltf(filepath=a.out, export_format="GLB", use_selection=False,
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
    export_image_format="JPEG", export_jpeg_quality=90,
    export_animations=True, export_skins=True, export_yup=True)
print(f"[face] wrote {a.out} {os.path.getsize(a.out) / 1e6:.1f} MB")
