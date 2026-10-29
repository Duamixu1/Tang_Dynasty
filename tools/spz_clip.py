# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""离线裁剪高斯泼溅 .spz：按原始坐标系的范围删点，另存一份。
World Labs 用全景图生成房间时，会顺着门口把门外的走廊也"脑补"出来，和真走廊叠在一起；运行时用 Spark 的 SplatEdit 裁会让整个渲染停摆，所以在文件层面裁。
用法：uv run tools/spz_clip.py <输入.spz> <输出.spz> --zmin -2.1 [--zmax 9] [--xmin ..] [--xmax ..] [--ymin ..] [--ymax ..]
坐标是文件里的原始坐标（World Labs：y 向下、正前方 +z、相机在原点）。
SPZ 格式（Niantic）：gzip 包着 16 字节头 + 各属性数组：位置 int24×3（定点，fractionalBits）、alpha u8、颜色 u8×3、缩放 u8×3、旋转 u8×3（v2）/ u8×4（v3）、球谐 u8×(dim×3)。"""
import argparse, gzip, struct, sys
from pathlib import Path
import numpy as np

MAGIC = 0x5053474E

def main():
    p = argparse.ArgumentParser()
    p.add_argument("src"); p.add_argument("dst")
    for k in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"): p.add_argument("--" + k, type=float)
    a = p.parse_args()
    raw = gzip.decompress(Path(a.src).read_bytes())
    magic, version, n, sh_deg, frac_bits, flags, reserved = struct.unpack_from("<IIIBBBB", raw, 0)
    if magic != MAGIC: sys.exit(f"不是 SPZ 文件（magic {magic:#x}）")
    rot_bytes = 3 if version == 2 else 4
    sh_dim = (sh_deg + 1) ** 2 - 1
    sizes = [("pos", n * 9), ("alpha", n), ("color", n * 3), ("scale", n * 3), ("rot", n * rot_bytes), ("sh", n * sh_dim * 3)]
    off = 16; parts = {}
    for name, size in sizes:
        parts[name] = np.frombuffer(raw, dtype=np.uint8, count=size, offset=off); off += size
    if off != len(raw): print(f"提示：文件还有 {len(raw) - off} 字节没对上（版本 {version}），按已知布局继续")
    # int24 小端有符号 → float
    b = parts["pos"].reshape(n, 3, 3).astype(np.int32)
    v = b[:, :, 0] | (b[:, :, 1] << 8) | (b[:, :, 2] << 16)
    v = np.where(v & 0x800000, v - 0x1000000, v)
    pos = v.astype(np.float64) / (1 << frac_bits)
    keep = np.ones(n, dtype=bool)
    for i, axis in enumerate("xyz"):
        lo, hi = getattr(a, axis + "min"), getattr(a, axis + "max")
        if lo is not None: keep &= pos[:, i] >= lo
        if hi is not None: keep &= pos[:, i] <= hi
    m = int(keep.sum())
    out = bytearray(struct.pack("<IIIBBBB", magic, version, m, sh_deg, frac_bits, flags, reserved))
    for name, size in sizes:
        per = size // n if n else 0
        arr = parts[name].reshape(n, per)[keep] if per else parts[name][:0]
        out += arr.tobytes()
    Path(a.dst).write_bytes(gzip.compress(bytes(out), compresslevel=6))
    print(f"版本 {version} 球谐 {sh_deg} 阶；{n} → {m} 点（删掉 {n - m}），范围 x[{pos[:,0].min():.2f},{pos[:,0].max():.2f}] y[{pos[:,1].min():.2f},{pos[:,1].max():.2f}] z[{pos[:,2].min():.2f},{pos[:,2].max():.2f}] → {a.dst}")

if __name__ == "__main__":
    main()
