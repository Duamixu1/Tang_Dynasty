# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
药贩子 v2：三视图切片 → Tripo 多视图生成 → 自动绑骨（v1.0 biped，才能和姿势库的骨骼名对上）。

  uv run tools/tripo_v2.py --name kusuriuri_v2 --views assets/concept/scenes/11_split \
      [--texture-quality detailed] [--face-limit 0]
进度存 assets/tripo_v2_state.json，断了重跑接着来。跑前跑后打余额。
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tripo_gen import Tripo, TripoError, load_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "assets/tripo_v2_state.json"
OUT = ROOT / "assets/tripo_raw"


def log(msg): print(f"[v2] {time.strftime('%H:%M:%S')} {msg}", flush=True)
def load_state(): return json.loads(STATE.read_text()) if STATE.exists() else {}
def save_state(s): STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def run(api, st, key, endpoint, payload, label):
    tid = st.get(key)
    if not tid:
        tid = api.create(endpoint, payload); st[key] = tid; save_state(STATE_ALL); log(f"{label} 已提交 {tid}")
    t = api.wait(tid, label, label)
    log(f"{label} 完成，扣 {t.get('credits_consumed', '?')} 积分")
    return t


def main():
    global STATE_ALL
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--views", required=True, help="目录，里面有 front/left/back/right .png（front 必须，其余可缺）")
    p.add_argument("--model", default="v3.1-20260211")
    p.add_argument("--texture-quality", default="detailed")
    p.add_argument("--face-limit", type=int, default=0, help="0 = 自适应")
    p.add_argument("--rig-model", default="v1.0-20240301")
    a = p.parse_args()

    api = Tripo(load_key())
    STATE_ALL = load_state(); st = STATE_ALL.setdefault(a.name, {})
    bal0 = api.balance()["balance"]; log(f"余额 {bal0}")

    # 1. 多视图生成
    model_file = OUT / f"{a.name}.glb"
    if not st.get("model_file") or not (ROOT / st["model_file"]).exists():
        inputs = []
        for view in ["front", "left", "back", "right"]:
            f = Path(a.views) / f"{view}.png"
            if f.exists():
                tok = api.upload(f); inputs.append({view: tok}); log(f"上传 {view} → {tok}")
        payload = {"inputs": inputs, "model": a.model, "texture": True, "pbr": False,
                   "texture_quality": a.texture_quality, "texture_alignment": "original_image"}
        if a.face_limit: payload["face_limit"] = a.face_limit
        t = run(api, st, "model_task", "/generation/multiview-to-model", payload, "多视图生成")
        api.download(t["output"]["model_url"], model_file)
        if t["output"].get("rendered_image_url"):
            api.download(t["output"]["rendered_image_url"], OUT / f"{a.name}_preview.webp")
        st["model_file"] = str(model_file.relative_to(ROOT)); save_state(STATE_ALL)
        log(f"模型 → {st['model_file']} ({model_file.stat().st_size/1e6:.0f} MB)")

    # 2. 绑骨
    rig_file = OUT / "anims" / f"{a.name}_rigged.glb"
    if not st.get("rig_file") or not (ROOT / st["rig_file"]).exists():
        t = run(api, st, "rigcheck_task", "/animations/rig-check", {"input": st["model_task"]}, "绑骨检查")
        log(f"riggable={t['output'].get('riggable')} rig_type={t['output'].get('rig_type')}")
        t = run(api, st, "rig_task", "/animations/rig",
                {"input": st["model_task"], "model": a.rig_model, "rig_type": "biped", "spec": "tripo", "out_format": "glb"}, "绑骨")
        api.download(t["output"]["model_url"], rig_file)
        st["rig_file"] = str(rig_file.relative_to(ROOT)); save_state(STATE_ALL)
        log(f"绑骨模型 → {st['rig_file']} ({rig_file.stat().st_size/1e6:.0f} MB)")

    bal1 = api.balance()["balance"]
    log(f"余额 {bal1}，本次共花 {bal0 - bal1}")


if __name__ == "__main__":
    try: main()
    except TripoError as e: sys.exit(f"[v2] 出错：{e}")
