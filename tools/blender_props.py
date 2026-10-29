"""
挂在角色身上的道具整理：assets/tripo_raw/<id>.glb → assets/processed/attach/<id>.glb（Draco，只留 basecolor）。
（场景里摆的道具在 assets/processed/props/，是 blender_lite.py 出的，米制；这里出的是角色单位，身高 1.0，别混。）
尺寸、朝向、原点按 tools/props.json。坐标约定（Blender，角色面朝 -Y）：
  笔：长轴沿 +Z、笔尖朝 +Z，原点在握笔处（grip_at = 从笔帽那头量起占全长的比例）。挂到手掌挂点后，+Z 就是笔尖方向。
  书箧：贴背那一面在原点，箱子往 +Y（身后）伸出去。
  铜镜：贴身那一面在原点，往 -Y（身前）伸出去。
  Blender -b --python tools/blender_props.py -- [--only sword] [--render 目录] [--raw]
  --raw 只渲原始模型三个方向（看 Tripo 导出的朝向，用来填 props.json 的 rot），不导出
"""
import argparse, json, math, os, sys
import bpy, bmesh
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument("--only", nargs="*")
p.add_argument("--render")
p.add_argument("--raw", action="store_true")
a = p.parse_args(argv)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "tools/props.json"), encoding="utf-8"))
RAW = os.path.join(ROOT, "assets/tripo_raw"); OUT = os.path.join(ROOT, "assets/processed/attach")
os.makedirs(OUT, exist_ok=True)


def load(pid):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(RAW, f"{pid}.glb"))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in bpy.data.objects: o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1: bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    # 去掉父级空节点，把世界变换应用进网格
    mw = obj.matrix_world.copy(); obj.parent = None; obj.matrix_world = mw
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in list(bpy.data.objects):
        if o is not obj: bpy.data.objects.remove(o, do_unlink=True)
    return obj


def verts(obj): return [v.co.copy() for v in obj.data.vertices]
def bbox(vs):
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def transform(obj, M):
    obj.data.transform(M); obj.data.update()


def align(obj, how):
    vs = verts(obj)
    if how == "sword":
        import numpy as np
        P = np.array([tuple(v) for v in vs]); c = P.mean(axis=0)
        w, V = np.linalg.eigh(np.cov((P - c).T)); ax = Vector(V[:, 2]).normalized()
        # 最长轴转到 +Z
        transform(obj, Matrix.Translation(-Vector(c)))
        transform(obj, ax.rotation_difference(Vector((0, 0, 1))).to_matrix().to_4x4())
        # 刀尖朝上：比较两端 15% 长度里截面的宽度，宽的一头（护手、流苏）是柄
        vs = verts(obj); lo, hi = bbox(vs); L = hi.z - lo.z
        def spread(sel):
            pts = [v for v in vs if sel(v.z)]
            if not pts: return 0
            l2, h2 = bbox(pts); return (h2.x - l2.x) + (h2.y - l2.y)
        if spread(lambda z: z > hi.z - 0.15 * L) > spread(lambda z: z < lo.z + 0.15 * L):
            transform(obj, Matrix.Rotation(math.pi, 4, "X"))
        print(f"[props] sword 长轴方差比 {w[2]/max(w[1],1e-9):.0f}")
    elif how == "box":
        # 在水平面上找使包围矩形面积最小的转角（0~90°，步长 1°），把箱子的面对齐 X/Y
        best = (1e9, 0)
        for deg in range(0, 90):
            r = math.radians(deg); cs, sn = math.cos(r), math.sin(r)
            xs = [v.x * cs - v.y * sn for v in vs]; ys = [v.x * sn + v.y * cs for v in vs]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if area < best[0]: best = (area, deg)
        transform(obj, Matrix.Rotation(math.radians(best[1]), 4, "Z"))
        print(f"[props] box 转 {best[1]}° 对齐")


def finish(obj, pid, d):
    if any(d["rot"]):
        rx, ry, rz = (math.radians(x) for x in d["rot"])
        transform(obj, (Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rx, 4, "X")))
    vs = verts(obj); lo, hi = bbox(vs); ext = hi - lo
    s = d["size"] / cfg["char_height_m"] / max(ext)          # 换成角色单位（身高 1.0）
    transform(obj, Matrix.Scale(s, 4))
    if d.get("depth_scale"): transform(obj, Matrix.Scale(d["depth_scale"], 4, Vector((0, 1, 0))))
    vs = verts(obj); lo, hi = bbox(vs); c = (lo + hi) / 2
    if d["anchor"] == "grip":
        L = hi.z - lo.z; zg = lo.z + d.get("grip_at", 0.13) * L   # 剑：柄约占全长 1/4，握柄中心在 1/8 处
        ring = [v for v in vs if abs(v.z - zg) < 0.03 * L] or vs
        l2, h2 = bbox(ring); o = Vector(((l2.x + h2.x) / 2, (l2.y + h2.y) / 2, zg))
    elif d["anchor"] == "back_face":
        ys = sorted(v.y for v in vs); zo = lo.z + d.get("anchor_z", 0.5) * (hi.z - lo.z)   # anchor_z：原点在高度的哪个比例（竹笈要往上伸过头顶）
        o = Vector((c.x, ys[int(len(ys) * 0.03)] + d.get("dy", 0.0), zo))   # 百分位数：肩带圈会往身体这边伸出来；dy 再把箱体往身上贴（角色单位）
    elif d["anchor"] == "hang":
        o = Vector((c.x, hi.y, c.z + 0.15 * (hi.z - lo.z)))
    else:
        o = c
    transform(obj, Matrix.Translation(-o))
    lo, hi = bbox(verts(obj))
    print(f"[props] {pid} 尺寸（角色单位）{tuple(round(x,3) for x in (hi-lo))}，原点 {d['anchor']}")


def rebuild_blade(obj):
    """剑已经转成刀身沿 +Z、原点在握柄中心。找护手（下半段截面最宽处），删掉它以上的部分，
    换成一片生成的刀身：菱形截面、刀刃朝 -Y、刀尖往刀背（+Y）方向微弯，单独一个浅钢色材质。"""
    vs = verts(obj); lo, hi = bbox(vs); L = hi.z - lo.z
    bins = 60; best = (0, lo.z)
    for i in range(bins):
        z0 = lo.z + L * i / bins; z1 = z0 + L / bins
        if z1 > lo.z + 0.5 * L: break
        pts = [v for v in vs if z0 <= v.z < z1]
        if len(pts) < 8: continue
        l2, h2 = bbox(pts); sp = (h2.x - l2.x) + (h2.y - l2.y)
        if sp > best[0]: best = (sp, (z0 + z1) / 2)
    z_cut = best[1] + 0.035 * L                             # 护手再往上一点（留刀镡后面的金色套）
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > z_cut], context="VERTS")
    bm.to_mesh(obj.data); bm.free()
    # 刀身
    base = z_cut - 0.005 * L; length = hi.z - base
    W, T, sori, N = 0.032 * L, 0.008 * L, 0.025 * L, 24
    bm = bmesh.new(); rings = []
    for i in range(N + 1):
        t = i / N; z = base + length * t; yoff = sori * t * t
        taper = 1.0 - 0.25 * t
        w = W * taper; th = T * taper
        if t > 0.92: w *= (1 - t) / 0.08 * 0.9 + 0.1; th *= (1 - t) / 0.08 * 0.9 + 0.1   # 刀尖收窄
        ring = [bm.verts.new((0, yoff - w * 0.5, z)),      # 刀刃
                bm.verts.new((th * 0.5, yoff + w * 0.1, z)),
                bm.verts.new((0, yoff + w * 0.5, z)),      # 刀背
                bm.verts.new((-th * 0.5, yoff + w * 0.1, z))]
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(4):
            bm.faces.new((r0[k], r0[(k + 1) % 4], r1[(k + 1) % 4], r1[k]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    me = bpy.data.meshes.new("blade"); bm.to_mesh(me); bm.free()
    blade = bpy.data.objects.new("blade", me); bpy.context.scene.collection.objects.link(blade)
    mat = bpy.data.materials.new("blade_steel"); mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.78, 0.78, 0.86, 1)
    b.inputs["Roughness"].default_value = 1.0
    me.materials.append(mat)
    for poly in me.polygons: poly.use_smooth = False
    print(f"[props] 刀身重建：护手在 z={best[1]:.3f}，刀身长 {length:.3f}（全长 {L:.3f}）")
    return blade


def slim(obj, tris):
    for poly in obj.data.polygons: poly.use_smooth = True
    obj.data.calc_loop_triangles(); n0 = len(obj.data.loop_triangles)
    if n0 > tris:
        m = obj.modifiers.new("dec", "DECIMATE"); m.ratio = tris / n0; m.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = obj; bpy.ops.object.modifier_apply(modifier="dec")
    for mat in bpy.data.materials:
        if not mat.node_tree: continue
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        for n in list(nt.nodes):
            if n.type == "TEX_IMAGE" and not any(l.to_socket.name == "Base Color" for l in n.outputs[0].links):
                nt.nodes.remove(n)
            elif n.type == "TEX_IMAGE" and n.image and max(n.image.size) > 1024:
                n.image.scale(1024, 1024); n.image.pack()
        if bsdf: bsdf.inputs["Roughness"].default_value = 1.0; bsdf.inputs["Metallic"].default_value = 0.0
    obj.data.calc_loop_triangles(); print(f"[props] 面数 {n0} → {len(obj.data.loop_triangles)}")


def render(obj, pid, tag):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = 640
    w = bpy.data.worlds.new("W"); scene.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.85, 0.83, 0.78, 1)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")); sun.data.energy = 3
    sun.rotation_euler = (math.radians(50), 0, math.radians(30)); scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.type = "ORTHO"
    lo, hi = bbox([obj.matrix_world @ v for v in verts(obj)]); c = (lo + hi) / 2; R = max(hi - lo)
    cam.data.ortho_scale = R * 1.25
    # 坐标轴小标记：红 +X、绿 +Y、蓝 +Z，原点处
    for i, col in enumerate([(1, 0, 0, 1), (0, 0.7, 0, 1), (0, 0, 1, 1)]):
        bpy.ops.mesh.primitive_cylinder_add(radius=R * 0.01, depth=R * 0.3)
        cy = bpy.context.active_object; d = Vector((0, 0, 0)); d[i] = R * 0.15; cy.location = d
        cy.rotation_euler = [(0, math.pi / 2, 0), (-math.pi / 2, 0, 0), (0, 0, 0)][i]
        m = bpy.data.materials.new(f"ax{i}"); m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = col
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = col
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 1.0
        cy.data.materials.append(m)
    for name, dvec in [("front", Vector((0, -1, 0))), ("side", Vector((1, 0, 0))), ("top", Vector((0, 0, 1)))]:
        cam.location = c + dvec * R * 3
        cam.rotation_euler = (-dvec).to_track_quat("-Z", "Y" if name != "top" else "Y").to_euler()
        scene.render.filepath = os.path.join(a.render, f"{pid}_{tag}_{name}.png"); bpy.ops.render.render(write_still=True)


for pid, d in cfg["props"].items():
    if a.only and pid not in a.only: continue
    if not os.path.exists(os.path.join(RAW, f"{pid}.glb")): print(f"[props] 没有 {pid}.glb，跳过"); continue
    obj = load(pid)
    if a.raw:
        if a.render: render(obj, pid, "raw")
        continue
    align(obj, d["align"]); finish(obj, pid, d); slim(obj, d["tris"])
    obj.name = pid
    if d.get("rebuild_blade"):
        blade = rebuild_blade(obj)
        for o in bpy.data.objects: o.select_set(o in (obj, blade))
        bpy.context.view_layer.objects.active = obj; bpy.ops.object.join()
    out = os.path.join(OUT, f"{pid}.glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False,
        export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
        export_image_format="JPEG", export_jpeg_quality=85, export_yup=True)
    print(f"[props] wrote {out} {os.path.getsize(out)/1e6:.2f} MB")
    if a.render: render(obj, pid, "done")
