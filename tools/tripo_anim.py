# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
把一个现成的 GLB 传回 Tripo，自动绑骨并套预设动作（v3 接口）。

  1. presign 上传（大文件）→ file_token
  2. /models/import           → 模型任务号（可复用）
  3. /animations/rig-check     → 能不能绑
  4. /animations/rig           → 绑骨 GLB（默认绑骨模型 v1.0，biped，才有 90 多个预设）
  5. /animations/retarget      → 一次最多 5 个动作，带几何、原地播放
进度存 assets/tripo_anim_state.json，断了重跑接着来。跑前跑后各打一次余额。

用法（在 mononoke-game 目录）：
  uv run tools/tripo_anim.py --in assets/tripo_raw/kusuriuri_v1.glb --name kusuriuri_v1 \
      --anims idle walk turn look_around slash
  uv run tools/tripo_anim.py --name kusuriuri_v1 --anims cast_a_spell agree fold_arms   再加一批
"""
import argparse, json, sys, time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tripo_gen import Tripo, TripoError, load_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "assets/tripo_anim_state.json"
OUT = ROOT / "assets/tripo_raw/anims"
RIG_MODEL = "v1.0-20240301"


def log(msg):
    print(f"[anim] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def presign_upload(api, path):
    fmt = Path(path).suffix.lstrip(".").lower()
    d = api._call("POST", "/files/presign", json={"format": fmt})
    with open(path, "rb") as f:
        r = requests.put(d["presigned_url"], data=f, headers={"Content-Type": "application/octet-stream"}, timeout=600)
    r.raise_for_status()
    return d["file_token"]


def run(api, state, key, endpoint, payload, label):
    """提交任务并等完成；state[key] 已有任务号就只查结果"""
    tid = state.get(key)
    if not tid:
        tid = api.create(endpoint, payload)
        state[key] = tid
        save_state(state)
        log(f"{label} 已提交 {tid}")
    t = api.wait(tid, label, label)
    log(f"{label} 完成，扣 {t.get('credits_consumed', '?')} 积分")
    return t


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp")
    p.add_argument("--name", required=True)
    p.add_argument("--anims", nargs="+", default=["idle", "walk", "turn", "look_around", "slash"])
    p.add_argument("--rig-model", default=RIG_MODEL)
    a = p.parse_args()
    if len(a.anims) > 5:
        sys.exit("一次最多 5 个动作")

    api = Tripo(load_key())
    state_all = load_state()
    st = state_all.setdefault(a.name, {})
    bal0 = api.balance()["balance"]
    log(f"余额 {bal0}")

    if not st.get("import_task"):
        if not a.inp:
            sys.exit("第一次要给 --in 文件")
        log(f"上传 {a.inp}（{Path(a.inp).stat().st_size/1e6:.0f} MB）…")
        token = presign_upload(api, a.inp)
        log(f"上传完成 {token}")
        t = run(api, st, "import_task", "/models/import", {"input": token}, "导入")
        st["normalize_scale"] = t["output"].get("normalize_scale")
        save_state(state_all)

    if "riggable" not in st:
        t = run(api, st, "rigcheck_task", "/animations/rig-check", {"input": st["import_task"]}, "绑骨检查")
        st["riggable"] = t["output"].get("riggable")
        st["rig_type"] = t["output"].get("rig_type")
        save_state(state_all)
        log(f"riggable={st['riggable']} rig_type={st['rig_type']}")
        if not st["riggable"]:
            log("Tripo 判断不好绑，但文档说仍可尝试，继续")

    rig_file = OUT / f"{a.name}_rigged.glb"
    if not st.get("rig_file") or not (ROOT / st["rig_file"]).exists():
        t = run(api, st, "rig_task", "/animations/rig",
                {"input": st["import_task"], "model": a.rig_model, "rig_type": "biped", "spec": "tripo", "out_format": "glb"}, "绑骨")
        api.download(t["output"]["model_url"], rig_file)
        st["rig_file"] = str(rig_file.relative_to(ROOT))
        save_state(state_all)
        log(f"绑骨模型 → {st['rig_file']} ({rig_file.stat().st_size/1e6:.0f} MB)")

    batch = "+".join(a.anims)
    key = f"retarget_{batch}"
    dest = OUT / f"{a.name}_anim_{batch}.glb"
    if not st.get(key + "_file") or not (ROOT / st[key + "_file"]).exists():
        presets = [f"preset:biped:{n}" for n in a.anims]
        t = run(api, st, key, "/animations/retarget",
                {"input": st["rig_task"], "animations": presets, "out_format": "glb", "animate_in_place": True, "export_with_geometry": True},
                f"重定向 {batch}")
        api.download(t["output"]["model_url"], dest)
        st[key + "_file"] = str(dest.relative_to(ROOT))
        save_state(state_all)
        log(f"动画模型 → {st[key + '_file']} ({dest.stat().st_size/1e6:.0f} MB)")

    bal1 = api.balance()["balance"]
    log(f"余额 {bal1}，本次共花 {bal0 - bal1}")


if __name__ == "__main__":
    try:
        main()
    except TripoError as e:
        sys.exit(f"[anim] 出错：{e}")
