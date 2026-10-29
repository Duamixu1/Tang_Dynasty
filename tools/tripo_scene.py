# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pillow"]
# ///
"""
生成场景概念图（只出图，不做 3D）。清单在 tools/scenes.json，输出到 assets/concept/scenes/<id>.png。
已经有图的会跳过；想重出某一张，加 --redo。旧图会挪到 assets/concept/scenes/_旧版/。

用法（在 hogwarts-game 目录下）：
  uv run tools/tripo_scene.py                    生成所有还没有的
  uv run tools/tripo_scene.py --only 01_礼堂全景 --redo
  出一个对比版本（不覆盖原图）：
  uv run tools/tripo_scene.py --only 01_礼堂全景 --model chat_image_2.5_sunburst --quality high --tag sunburst
"""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tripo_gen import IMAGE_MODEL, ROOT, Tripo, TripoError, load_key, log  # noqa: E402

SPEC = ROOT / "tools/scenes.json"
OUT = ROOT / "assets/concept/scenes"
REF_MAX = 2048  # 参考图缩到这个尺寸再传：4K 的 PNG 一张就 10MB，几张加起来会超出图片模型的输入上限，任务直接失败


def shrink(path, tmpdir):
    im = Image.open(path).convert("RGB")
    im.thumbnail((REF_MAX, REF_MAX))
    out = Path(tmpdir) / (path.stem + ".jpg")
    im.save(out, quality=92)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="逗号分隔的 id")
    p.add_argument("--redo", action="store_true")
    p.add_argument("--model", help="覆盖图片模型，如 seedream_v5、chat_image_2.5_sunburst、banana_pro")
    p.add_argument("--quality", help="只有 chat_image 系列支持：low/medium/high/xhigh/max")
    p.add_argument("--size", help="覆盖输出尺寸，如 4096x2304")
    p.add_argument("--tag", help="另存为 <id>__<tag>.png，不覆盖原图，用来对比")
    args = p.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    scenes = spec["scenes"]
    if args.only:
        ids = set(args.only.split(","))
        scenes = [s for s in scenes if s["id"] in ids]
        if not scenes:
            sys.exit(f"scenes.json 里没有：{args.only}")

    api = Tripo(load_key())
    start = api.balance()["balance"]
    tokens = {}
    failed = []
    tmpdir = tempfile.mkdtemp(prefix="tripo_refs_")
    for s in scenes:  # 图片任务账号并发为 1，一张张来
        dest = OUT / (f"{s['id']}__{args.tag}.png" if args.tag else f"{s['id']}.png")
        suffix = spec.get(s["suffix"] + "_suffix", spec["style_suffix"]) if s.get("suffix") else spec["style_suffix"]  # 建模参考图用 model_suffix：不画纸纹和阴影
        prompt = f"{s['prompt']} {spec.get('canon', '')} {suffix}"
        if len(prompt) > 1800:  # Tripo 的上限，超了会直接被拒
            failed.append(s["id"])
            log(s["id"], f"提示词 {len(prompt)} 字符，超过 1800 上限，先删短")
            continue
        if dest.exists():
            if not args.redo:
                log(s["id"], "已有，跳过")
                continue
            old = OUT / "_旧版" / f"{s['id']}_{time.strftime('%m%d%H%M%S')}.png"
            old.parent.mkdir(parents=True, exist_ok=True)
            dest.replace(old)
        try:
            refs = []
            for r in s["refs"]:
                if r not in tokens:
                    tokens[r] = api.upload(shrink(ROOT / r, tmpdir))
                refs.append(tokens[r])
            payload = {"model": args.model or s.get("model", IMAGE_MODEL), "inputs": refs,
                       "size": args.size or s.get("size", "2048x2048"),
                       "prompt": prompt}
            if args.quality or s.get("quality"):
                payload["quality"] = args.quality or s["quality"]
            task_id = api.create("/generation/image-to-image", payload)
            log(s["id"], f"已提交 {task_id}（{payload['model']} {payload['size']}）")
            t = api.wait(task_id, s["id"], "出图")
            api.download(t["output"]["generated_image_url"], dest)
            log(s["id"], f"→ {dest.relative_to(ROOT)}（{t.get('credits_consumed', 0):g} 积分）")
        except TripoError as e:
            failed.append(s["id"])
            log(s["id"], f"失败 {e}")

    end = api.balance()["balance"]
    print(f"\n本次消耗 {start - end:g} 积分，余额 {end}")
    if failed:
        print("失败：" + "、".join(failed))


if __name__ == "__main__":
    main()
