# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pillow"]
# ///
"""
用 World Labs（Marble）API 把一张概念图生成成可走动的 3D 世界（高斯泼溅 + 碰撞网格）。

用法（在 mononoke-game 目录下）：
  uv run tools/worldlabs_gen.py --image assets/concept/scenes/02_走廊全景.png --name corridor
  多图（方位角：0 正面、90 右、180 背后、270 左）：
  uv run tools/worldlabs_gen.py --name corridor_v2 --multi 正面.png:0 右墙.png:90 回头.png:180 左墙.png:270
  360 全景图（等距柱状 2:1）：
  uv run tools/worldlabs_gen.py --image 全景.png --pano --name corridor_v3
  uv run tools/worldlabs_gen.py --name corridor --resume <operation_id>     断了接着查
  uv run tools/worldlabs_gen.py --name corridor --world <world_id>          只重新下载

输出到 assets/worldlabs/<name>/：world.json、splat_500k.spz、splat_full.spz、collider.glb、pano.jpg、thumb.jpg
官方价：marble-1.1 / 1.0 每张 1500 积分，marble-1.0-draft 150 积分。
API Key 写在 .env 的 WORLDLABS_API_KEY=。
"""
import argparse, json, os, sys, tempfile, time
from pathlib import Path
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.worldlabs.ai/marble/v1"
MAX_SIDE = 4096


def load_key():
    if os.environ.get("WORLDLABS_API_KEY"):
        return os.environ["WORLDLABS_API_KEY"].strip()
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition("=")
        if k.strip() == "WORLDLABS_API_KEY" and v.strip():
            return v.strip()
    sys.exit("没找到 WORLDLABS_API_KEY，写在 mononoke-game/.env 里")


def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


class WL:
    def __init__(self, key):
        self.s = requests.Session()
        self.s.headers["WLT-Api-Key"] = key

    def call(self, method, path, **kw):
        r = self.s.request(method, f"{BASE}{path}", timeout=120, **kw)
        if not r.ok:
            sys.exit(f"{method} {path} → {r.status_code}: {r.text[:400]}")
        return r.json()

    def upload_image(self, path):
        im = Image.open(path).convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        tmp = Path(tempfile.mkdtemp()) / "scene.jpg"
        im.save(tmp, quality=92)
        prep = self.call("POST", "/media-assets:prepare_upload",
                         json={"file_name": "scene.jpg", "kind": "image", "extension": "jpg"})
        up = prep["upload_info"]
        r = requests.request(up.get("upload_method", "PUT"), up["upload_url"],
                             headers=up.get("required_headers", {}), data=tmp.read_bytes(), timeout=300)
        r.raise_for_status()
        aid = prep["media_asset"]["media_asset_id"]
        log(f"图片已上传 {im.size[0]}x{im.size[1]} → media_asset {aid}")
        return aid

    def generate(self, asset_id, name, model, prompt, seed, multi=None, pano=False):
        if multi:  # [(asset_id, azimuth), ...]
            wp = {"type": "multi-image", "reconstruct_images": False,
                  "multi_image_prompt": [{"azimuth": az, "content": {"source": "media_asset", "media_asset_id": aid}} for aid, az in multi]}
        else:
            wp = {"type": "image", "is_pano": pano,
                  "image_prompt": {"source": "media_asset", "media_asset_id": asset_id}}
        body = {"display_name": name[:64], "model": model, "world_prompt": wp}
        if prompt:
            body["world_prompt"]["text_prompt"] = prompt
        if seed is not None:
            body["seed"] = seed
        op = None
        for attempt in range(12):  # 素材要先变成 READY，不然 400/422，最多等 1 分钟
            r = self.s.post(f"{BASE}/worlds:generate", json=body, timeout=120)
            if r.ok:
                op = r.json(); break
            if r.status_code in (400, 422) and attempt < 11 and "READY" in r.text.upper():
                log(f"素材还没就绪，5 秒后重试：{r.text[:120]}"); time.sleep(5); continue
            sys.exit(f"POST /worlds:generate → {r.status_code}: {r.text[:400]}")
        log(f"已提交 operation {op['operation_id']}（{model}）")
        return op["operation_id"]

    def wait(self, op_id):
        last = None
        while True:
            op = self.call("GET", f"/operations/{op_id}")
            if op.get("done"):
                if op.get("error"):
                    sys.exit(f"生成失败：{op['error']}")
                cost = (op.get("cost") or {}).get("total_credits")
                log(f"完成，花费 {cost} 积分")
                return op
            p = (op.get("metadata") or {}).get("progress") or {}
            cur = f"{p.get('status', '')} {p.get('description', '')}".strip()
            if cur != last:
                log(f"进行中 {cur}")
                last = cur
            time.sleep(15)

    def download(self, url, dest):
        if not url:
            return
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        log(f"→ {dest.relative_to(ROOT)}（{dest.stat().st_size / 1e6:.1f} MB）")


def save_world(api, world_id, out):
    world = api.call("GET", f"/worlds/{world_id}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "world.json").write_text(json.dumps(world, ensure_ascii=False, indent=2), encoding="utf-8")
    a = world.get("assets") or {}
    spz = (a.get("splats") or {}).get("spz_urls") or {}
    api.download(spz.get("500k"), out / "splat_500k.spz")
    api.download(spz.get("full_res"), out / "splat_full.spz")
    api.download((a.get("mesh") or {}).get("collider_mesh_url"), out / "collider.glb")
    api.download((a.get("imagery") or {}).get("pano_url"), out / "pano.jpg")
    api.download(a.get("thumbnail_url"), out / "thumb.jpg")
    log(f"网页查看：{world.get('world_marble_url')}")
    log(f"metric_scale_factor={((a.get('splats') or {}).get('semantics_metadata') or {}).get('metric_scale_factor')}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image")
    p.add_argument("--multi", nargs="+", help="多张 图片路径:方位角")
    p.add_argument("--pano", action="store_true", help="--image 是等距柱状 360 全景图")
    p.add_argument("--name", required=True)
    p.add_argument("--model", default="marble-1.1")
    p.add_argument("--prompt", default="")
    p.add_argument("--seed", type=int)
    p.add_argument("--resume", help="operation_id")
    p.add_argument("--world", help="world_id，只下载")
    a = p.parse_args()
    api = WL(load_key())
    out = ROOT / "assets/worldlabs" / a.name
    if a.world:
        return save_world(api, a.world, out)
    if a.resume:
        op_id = a.resume
    else:
        if a.multi:
            multi = []
            for item in a.multi:
                path, _, az = item.rpartition(":")
                multi.append((api.upload_image(ROOT / path), float(az)))
            time.sleep(5)
            op_id = api.generate(None, a.name, a.model, a.prompt, a.seed, multi=multi)
        elif a.image:
            asset_id = api.upload_image(ROOT / a.image)
            op_id = api.generate(asset_id, a.name, a.model, a.prompt, a.seed, pano=a.pano)
        else:
            sys.exit("要么给 --image / --multi，要么给 --resume / --world")
        out.mkdir(parents=True, exist_ok=True)
        (out / "operation_id.txt").write_text(op_id)
    op = api.wait(op_id)
    world_id = (op.get("metadata") or {}).get("world_id") or (op.get("response") or {}).get("id")
    save_world(api, world_id, out)


if __name__ == "__main__":
    main()
