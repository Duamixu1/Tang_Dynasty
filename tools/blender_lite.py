"""
把 Tripo 原始 GLB 减成网页能用的轻量版。

  1. 平滑法线（消掉减面后描边抓到的碎面小点），Decimate 到目标面数（默认 10 万），顶点组（蒙皮权重）会跟着保留
  2. 只保留 basecolor 贴图，缩到 2048；法线图、粗糙度/金属度图丢掉
  3. 没骨骼：合并网格，统一高度（默认 1.7 米），原点放脚底中心
     有骨骼（--keep-rig）：不合并、不缩放，骨骼和全部动作原样导出，尺寸交给查看器归一
  4. 导出 Draco 压缩 GLB

用法：
  /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/blender_lite.py -- \
      --in assets/tripo_raw/kusuriuri_v1.glb --out assets/processed/kusuriuri_v1_lite.glb \
      [--tris 100000] [--tex 2048] [--height 1.7] [--keep-rig]
"""
import argparse, os, sys, time
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument("--in", dest="inp", required=True)
p.add_argument("--out", required=True)
p.add_argument("--tris", type=int, default=100_000)
p.add_argument("--tex", type=int, default=2048)
p.add_argument("--height", type=float, default=1.7)
p.add_argument("--keep-rig", action="store_true")
a = p.parse_args(argv)

t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a.inp)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
print(f"[lite] objects: {len(meshes)} mesh, {len(arms)} armature, actions: {[ac.name for ac in bpy.data.actions]}")

if not a.keep_rig and len(meshes) > 1:
    for o in bpy.data.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    meshes = [bpy.context.view_layer.objects.active]

total_before = 0
for m in meshes:
    m.data.calc_loop_triangles(); total_before += len(m.data.loop_triangles)
print(f"[lite] tris before: {total_before}")

# 1. 平滑 + 减面（按每个网格占的比例分配面数）
for obj in meshes:
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.calc_loop_triangles()
    n = len(obj.data.loop_triangles)
    ratio = min(1.0, a.tris * (n / total_before) / max(n, 1))
    if ratio < 1.0:
        bpy.context.view_layer.objects.active = obj
        mod = obj.modifiers.new("dec", "DECIMATE")
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_move_to_index(modifier="dec", index=0)  # 放到骨骼修改器前面才能应用
        bpy.ops.object.modifier_apply(modifier="dec")
total_after = 0
for m in meshes:
    m.data.calc_loop_triangles(); total_after += len(m.data.loop_triangles)
print(f"[lite] tris after: {total_after}  ({time.time()-t0:.0f}s)")

# 2. 贴图：只留 Base Color
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not bsdf:
        continue
    keep = None
    for n in list(nt.nodes):
        if n.type == "TEX_IMAGE":
            if any(l.to_socket.name == "Base Color" for l in n.outputs[0].links):
                keep = n
            else:
                nt.nodes.remove(n)
        elif n.type in ("NORMAL_MAP", "SEPARATE_COLOR"):
            nt.nodes.remove(n)
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    if keep and keep.image:
        img = keep.image
        if max(img.size) > a.tex:
            img.scale(a.tex, a.tex)
            img.pack()
        print(f"[lite] basecolor {img.name} -> {list(img.size)}")
for img in list(bpy.data.images):
    if img.users == 0:
        bpy.data.images.remove(img)

# 3. 高度和原点（只在没骨骼时做）
if not a.keep_rig:
    obj = meshes[0]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    lo = Vector((1e9,)*3); hi = Vector((-1e9,)*3)
    for v in obj.data.vertices:
        lo = Vector(map(min, lo, v.co)); hi = Vector(map(max, hi, v.co))
    h = hi.z - lo.z
    s = a.height / h
    obj.scale = (s, s, s)
    obj.location = (-(lo.x+hi.x)/2*s, -(lo.y+hi.y)/2*s, -lo.z*s)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.name = "kusuriuri"
    print(f"[lite] height {h:.3f} -> {a.height}")

# 3b. 统一朝向：有骨骼时按左右锁骨算出正面，绕 Z 转到 Blender 的 -Y（导出后就是 glTF/Three.js 的 +Z）
#     只转对象不应用变换，骨骼动画不受影响。Tripo 不同任务导出的朝向不一样（v1 朝 -Y，v2 朝 +X）。
if a.keep_rig and arms:
    import math
    from mathutils import Vector as _V
    arm = arms[0]
    try:
        lt = arm.matrix_world @ arm.data.bones["L_Clavicle"].tail_local
        rt = arm.matrix_world @ arm.data.bones["R_Clavicle"].tail_local
        left = lt - rt; left.z = 0; left.normalize()
        front = left.cross(_V((0, 0, 1)))
        cur = math.atan2(front.y, front.x); target = -math.pi / 2
        roots = [o for o in bpy.data.objects if o.parent is None and o.type in ("ARMATURE", "MESH", "EMPTY")]
        for o in roots:
            o.rotation_mode = "XYZ"; o.rotation_euler.z += target - cur
        bpy.context.view_layer.update()
        print(f"[lite] front was ({front.x:.2f},{front.y:.2f}), rotated {math.degrees(target-cur):.0f}° so it faces -Y")
    except KeyError:
        print("[lite] 没找到锁骨骨头，朝向不动")

# 4. 导出
bpy.ops.export_scene.gltf(
    filepath=a.out, export_format="GLB", use_selection=False,
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
    export_image_format="JPEG", export_jpeg_quality=85,
    export_normals=True, export_tangents=False, export_materials="EXPORT",
    export_animations=a.keep_rig, export_skins=a.keep_rig, export_yup=True,
    export_animation_mode="ACTIONS" if a.keep_rig else "ACTIONS",
)
print(f"[lite] wrote {a.out}  {os.path.getsize(a.out)/1e6:.1f} MB  ({time.time()-t0:.0f}s)")
