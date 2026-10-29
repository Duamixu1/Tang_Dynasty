"""
修 Tripo 贴图里头发上的白条：2D 线稿把黑发的高光画成了细白线，Tripo 烘进了 basecolor，进游戏就是几缕白头发。
做法：只看贴图，找"大片黑色里夹着的细亮线"——亮像素周围 15 像素见方里，深色占比超过 0.6 的，涂成周围深色的平均色。
脸、眼白周围大多是肤色，占比到不了 0.6，不会被动。骨骼、动作、其余贴图原样导出。

  Blender -b --python tools/blender_fix_hair.py -- --in assets/processed/scholar_v2_lite.glb --out assets/processed/scholar_v2_lite.glb \
      [--dark 70] [--light 150] [--win 15] [--frac 0.6] [--preview 目录]
"""
import argparse, os, sys
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument("--in", dest="inp", required=True)
p.add_argument("--out", required=True)
p.add_argument("--dark", type=float, default=70)      # 亮度低于这个算黑发
p.add_argument("--light", type=float, default=150)    # 亮度高于这个算"白条"候选
p.add_argument("--win", type=int, default=15)
p.add_argument("--frac", type=float, default=0.6)
p.add_argument("--preview")
a = p.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a.inp)


def box_mean(m, r):
    """r 半径的方框均值（积分图），边缘按实际像素数归一"""
    H, W = m.shape
    c = np.pad(m, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    y0 = np.clip(np.arange(H) - r, 0, H); y1 = np.clip(np.arange(H) + r + 1, 0, H)
    x0 = np.clip(np.arange(W) - r, 0, W); x1 = np.clip(np.arange(W) + r + 1, 0, W)
    s = c[y1][:, x1] - c[y0][:, x1] - c[y1][:, x0] + c[y0][:, x0]
    n = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    return s / n


done = set()
for mat in bpy.data.materials:
    if not mat.node_tree: continue
    for n in mat.node_tree.nodes:
        if n.type != "TEX_IMAGE" or not n.image or n.image.name in done: continue
        if not any(l.to_socket.name == "Base Color" for l in n.outputs[0].links): continue
        img = n.image; done.add(img.name)
        W, H = img.size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)
        lum = (0.299 * px[..., 0] + 0.587 * px[..., 1] + 0.114 * px[..., 2]) * 255
        dark = (lum < a.dark).astype(np.float32)
        r = a.win // 2
        frac = box_mean(dark, r)
        fix = (lum > a.light) & (frac > a.frac)
        # 周围深色的平均色
        cols = [box_mean(px[..., k] * dark, r) / np.maximum(frac, 1e-6) for k in range(3)]
        before = px.copy()
        for k in range(3): px[..., k] = np.where(fix, cols[k], px[..., k])
        img.pixels[:] = px.ravel()
        img.pack()
        print(f"[hair] {img.name} {W}x{H}：改了 {int(fix.sum())} 个像素（{fix.mean() * 100:.2f}%）")
        if a.preview:
            os.makedirs(a.preview, exist_ok=True)
            for tag, arr in (("before", before), ("after", px)):
                out = bpy.data.images.new(f"{tag}", W, H, alpha=True); out.pixels[:] = arr.ravel()
                out.filepath_raw = os.path.join(a.preview, f"{img.name}_{tag}.png"); out.file_format = "PNG"; out.save()

bpy.ops.export_scene.gltf(filepath=a.out, export_format="GLB", use_selection=False,
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
    export_image_format="JPEG", export_jpeg_quality=90,
    export_animations=True, export_skins=True, export_yup=True)
print(f"[hair] wrote {a.out} {os.path.getsize(a.out) / 1e6:.1f} MB")
