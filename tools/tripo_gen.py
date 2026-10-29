# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
用 Tripo API 批量生成 tools/assets.json 里的素材。

每个素材分三步：
  1. 概念图：拿参考图（黏土哈利）当风格参考，用 image-to-image 生成这个道具的黏土风格图
             → assets/concept/gen/<id>.png
  2. 3D 模型：用概念图做 image-to-model → assets/tripo_raw/<id>.glb
  3. 绑骨（只有标了 rig 的角色）：rig-check + rig，Unity Humanoid 骨骼命名
             → 绑好的覆盖 assets/tripo_raw/<id>.glb，没绑的留在 assets/tripo_raw/_static/

进度存在 assets/tripo_state.json。中途断了重跑会接着之前的任务查结果，不会重复扣积分。
失败的任务 Tripo 不扣积分，重跑时会重新提交。

API Key：在 mononoke-game/.env 里写一行 TRIPO_API_KEY=你的key（.env 不要外传）。

用法（在 hogwarts-game 目录下）：
  uv run tools/tripo_gen.py --plan                    只看清单和进度，不联网、不花钱
  uv run tools/tripo_gen.py --balance                 查余额
  uv run tools/tripo_gen.py --batch 1 --stage concept 只出第一批的概念图（便宜，先看风格对不对）
  uv run tools/tripo_gen.py --batch 1                 第一批走完全部步骤
  uv run tools/tripo_gen.py --only sorting_hat --redo concept   不满意，重出这张概念图（模型也会跟着重做）
"""

import argparse
import fcntl
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tools/assets.json"
STATE = ROOT / "assets/tripo_state.json"
CONCEPT_DIR = ROOT / "assets/concept/gen"
RAW_DIR = ROOT / "assets/tripo_raw"
HOSTS = {"ov": "https://openapi.tripo3d.ai/v3", "cn": "https://openapi.tripo3d.com/v3"}

IMAGE_MODEL = "seedream_v5"
RIG = {"model": "v3.0-20260909", "rig_type": "biped", "spec": "unity", "out_format": "glb"}
POLL_SEC = 5
TIMEOUT_SEC = 20 * 60
MODEL_WORKERS = 4  # 图片类任务账号并发只有 1，所以概念图一张张来；3D 和绑骨可以并行

lock = threading.Lock()


# ---------- 状态文件 ----------

def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


# 这次运行负责的素材 id。保存时只写回这些素材，其他素材以磁盘上的为准，
# 这样两个窗口同时跑不同批次也不会互相覆盖进度（覆盖了会导致重复提交、重复扣积分）
OWNED = set()


def save_state(state):
    with lock:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE.with_suffix(".lock"), "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)  # 跨进程加锁，读-合并-写之间不会被别的进程插进来
            disk = load_state()
            for k in OWNED:
                if k in state:
                    disk[k] = state[k]
                else:
                    disk.pop(k, None)
            tmp = STATE.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(disk, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(STATE)


def log(asset_id, msg):
    with lock:
        print(f"[{time.strftime('%H:%M:%S')}] {asset_id:<18} {msg}", flush=True)


# ---------- API ----------

class TripoError(Exception):
    pass


class Tripo:
    def __init__(self, key, region=None):
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {key}"
        # TRIPO_BASE_URL 只在测试时用，平时不用设
        self.base = os.environ.get("TRIPO_BASE_URL") or (HOSTS[region] if region else self._detect_region())

    def _detect_region(self):
        # 国际站和国内站的 key 不通用，用查余额试一下哪个认这个 key
        for region, base in HOSTS.items():
            try:
                r = self.s.get(f"{base}/account/balance", timeout=15)
                if r.ok and r.json().get("code") == 0:
                    return base
            except requests.RequestException:
                pass
        raise TripoError("两个站点都不认这个 API Key，检查一下 .env 里的 TRIPO_API_KEY")

    def _call(self, method, path, **kw):
        delay = 5
        for _ in range(8):
            r = self.s.request(method, f"{self.base}{path}", timeout=60, **kw)
            try:
                body = r.json()
            except ValueError:
                body = {}
            code = body.get("code")
            # 1007 频率超限，2000 并发占满：等一会儿再试
            if r.status_code == 429 or code in (1007, 2000) or r.status_code >= 500:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if code != 0:
                raise TripoError(f"{path} 出错 {code}: {body.get('message')}（{body.get('suggestion', '')}）")
            return body["data"]
        raise TripoError(f"{path} 重试多次仍然失败（限流或服务器错误）")

    def balance(self):
        return self._call("GET", "/account/balance")

    def upload(self, path):
        with open(path, "rb") as f:
            return self._call("POST", "/files", files={"file": (Path(path).name, f)})["file_token"]

    def create(self, endpoint, payload):
        return self._call("POST", endpoint, json=payload)["task_id"]

    def wait(self, task_id, asset_id, label):
        start = time.time()
        last = None
        while time.time() - start < TIMEOUT_SEC:
            t = self._call("GET", f"/tasks/{task_id}")
            st = t["status"]
            if st == "success":
                return t
            if st in ("failed", "cancelled"):
                raise TripoError(f"{label}任务{st}：{t.get('error_code')} {t.get('error_message', '')}")
            p = t.get("progress", 0)
            if (st, p // 25) != last:
                log(asset_id, f"{label} {st} {p}%")
                last = (st, p // 25)
            time.sleep(POLL_SEC)
        raise TripoError(f"{label}超过 {TIMEOUT_SEC // 60} 分钟还没完成，任务号 {task_id}，稍后重跑会接着查")

    def download(self, url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.s.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
            tmp.replace(dest)


# ---------- 每一步 ----------

def run_task(api, state, asset_id, step, endpoint, payload):
    """提交（或接着查）一个任务。已经有任务号的就不再提交，避免重复扣积分。"""
    st = state.setdefault(asset_id, {})
    task_id = st.get(f"{step}_task")
    if not task_id:
        task_id = api.create(endpoint, payload)
        st[f"{step}_task"] = task_id
        save_state(state)
        log(asset_id, f"{step} 已提交 {task_id}")
    try:
        t = api.wait(task_id, asset_id, step)
    except TripoError:
        st.pop(f"{step}_task", None)  # 失败不扣积分，清掉任务号，下次重跑会重新提交
        save_state(state)
        raise
    st.setdefault("credits", {})[step] = t.get("credits_consumed", 0)
    save_state(state)
    return t


class Uploads:
    def __init__(self, api):
        self.api, self.cache = api, {}

    def token(self, rel):
        path = ROOT / rel
        digest = hashlib.sha1(path.read_bytes()).hexdigest()
        if digest not in self.cache:
            self.cache[digest] = self.api.upload(path)
        return self.cache[digest]


def do_concept(api, uploads, spec, a, state):
    st = state.setdefault(a["id"], {})
    if st.get("concept_file") and (ROOT / st["concept_file"]).exists():
        return
    if a.get("source") and not a.get("edit_prompt"):
        st["concept_file"] = a["source"]  # 直接用原图，不需要生成
        save_state(state)
        return
    if a.get("source"):
        payload = {"model": IMAGE_MODEL, "input": uploads.token(a["source"]), "prompt": a["edit_prompt"]}
    else:
        # 素材可以单独指定参考图（比如主视觉里切出来的浮岛），让道具的造型和配色跟主视觉一致
        ref = a.get("style_ref", spec["style_ref"])
        prompt = spec.get("set_prompt" if a.get("style_ref") else "prop_prompt", spec["prop_prompt"])
        payload = {"model": IMAGE_MODEL, "input": uploads.token(ref), "prompt": prompt.format(subject=a["subject"])}
    t = run_task(api, state, a["id"], "concept", "/generation/image-to-image", payload)
    dest = CONCEPT_DIR / f"{a['id']}.png"
    api.download(t["output"]["generated_image_url"], dest)
    st["concept_file"] = str(dest.relative_to(ROOT))
    save_state(state)
    log(a["id"], f"概念图 → {st['concept_file']}")


def do_model(api, uploads, spec, a, state):
    st = state.setdefault(a["id"], {})
    final = RAW_DIR / f"{a['id']}.glb"
    static = (RAW_DIR / "_static" / f"{a['id']}.glb") if a.get("rig") else final

    if not (st.get("model_file") and (ROOT / st["model_file"]).exists()):
        if a.get("source") and not a.get("edit_prompt"):
            src = uploads.token(a["source"])
        elif st.get("concept_task"):
            src = st["concept_task"]  # 直接引用概念图任务，省一次上传
        elif st.get("concept_file"):
            src = uploads.token(st["concept_file"])
        else:
            raise TripoError("还没有概念图，先跑 --stage concept")
        payload = dict(spec["model_defaults"])
        payload.update({"input": src, "face_limit": a["tris"]})
        if a.get("texture_quality"):
            payload["texture_quality"] = a["texture_quality"]
        t = run_task(api, state, a["id"], "model", "/generation/image-to-model", payload)
        api.download(t["output"]["model_url"], static)
        if t["output"].get("rendered_image_url"):
            api.download(t["output"]["rendered_image_url"], RAW_DIR / "_preview" / f"{a['id']}.png")
        st["model_file"] = str(static.relative_to(ROOT))
        save_state(state)
        log(a["id"], f"模型 → {st['model_file']}")

    if not a.get("rig") or (st.get("rig_file") and (ROOT / st["rig_file"]).exists()):
        return
    check = run_task(api, state, a["id"], "rigcheck", "/animations/rig-check", {"input": st["model_task"]})
    if not check["output"].get("riggable"):
        raise TripoError(f"Tripo 认为这个模型没法绑骨（判断为 {check['output'].get('rig_type')}），未绑骨的模型在 {st['model_file']}")
    t = run_task(api, state, a["id"], "rig", "/animations/rig", {"input": st["model_task"], **RIG})
    api.download(t["output"]["model_url"], final)
    st["rig_file"] = str(final.relative_to(ROOT))
    save_state(state)
    log(a["id"], f"绑骨 → {st['rig_file']}")


# ---------- 命令行 ----------

def select(spec, args):
    assets = spec["assets"]
    if args.only:
        ids = set(args.only.split(","))
        unknown = ids - {a["id"] for a in assets}
        if unknown:
            sys.exit(f"assets.json 里没有：{', '.join(sorted(unknown))}")
        return [a for a in assets if a["id"] in ids]
    if args.batch:
        return [a for a in assets if a["batch"] == args.batch]
    return [a for a in assets if not a.get("later")]


def step_status(a, st):
    def done(step):
        f = st.get(f"{step}_file")
        if f and (ROOT / f).exists():
            return "✓"
        return "…" if st.get(f"{step}_task") else "·"
    concept = "原图" if a.get("source") and not a.get("edit_prompt") else done("concept")
    rig = done("rig") if a.get("rig") else "-"
    return concept, done("model"), rig


def do_anims(api, a, state):
    """给已绑骨的角色套 Tripo 预设动画，每个动画单独存一个 FBX：<id>@<动作>.fbx（Unity 的命名习惯）"""
    st = state.setdefault(a["id"], {})
    if not st.get("rig_task"):
        raise TripoError("还没绑骨，先跑完 model 阶段")
    for preset in a.get("anims", []):
        name = preset.split(":")[-1]
        step = f"anim_{name}"
        dest = RAW_DIR / "anims" / f"{a['id']}@{name}.fbx"
        if st.get(f"{step}_file") and (ROOT / st[f"{step}_file"]).exists():
            continue
        payload = {"input": st["rig_task"], "animation": preset, "out_format": "fbx",
                   "animate_in_place": True}  # 原地动画：位移交给角色控制器，不让动画自己往前走
        t = run_task(api, state, a["id"], step, "/animations/retarget", payload)
        api.download(t["output"]["model_url"], dest)
        st[f"{step}_file"] = str(dest.relative_to(ROOT))
        save_state(state)
        log(a["id"], f"动画 {name} → {st[f'{step}_file']}")


def print_plan(spec, chosen, state):
    print(f"{'id':<18}{'批次':<5}{'概念图':<7}{'模型':<6}{'绑骨':<6}{'面数':>7}  {'贴图':<9}说明")
    for a in chosen:
        c, m, r = step_status(a, state.get(a["id"], {}))
        q = a.get("texture_quality", spec["model_defaults"]["texture_quality"])
        print(f"{a['id']:<18}{a['batch']:<6}{c:<8}{m:<7}{r:<7}{a['tris']:>6}  {q:<10}{a.get('note', '')}")
    n_img = sum(1 for a in chosen if not (a.get("source") and not a.get("edit_prompt")))
    n_rig = sum(1 for a in chosen if a.get("rig"))
    print(f"\n共 {len(chosen)} 个素材：图片任务 {n_img} 个，3D 任务 {len(chosen)} 个，绑骨 {n_rig} 个")
    print("✓ 已完成  … 进行中或失败待重跑  · 未开始  - 不需要")


def load_key():
    if os.environ.get("TRIPO_API_KEY"):
        return os.environ["TRIPO_API_KEY"].strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "TRIPO_API_KEY" and v.strip():
                return v.strip().strip('"').strip("'")
    sys.exit("没找到 API Key：在 mononoke-game/.env 里写一行 TRIPO_API_KEY=你的key")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", action="store_true", help="只显示清单和进度")
    p.add_argument("--balance", action="store_true", help="查余额")
    p.add_argument("--batch", type=int)
    p.add_argument("--only", help="逗号分隔的 id")
    p.add_argument("--stage", choices=["concept", "model", "anim", "all"], default="all")
    p.add_argument("--redo", choices=["concept", "model"], help="清掉这一步（及之后）的结果重新生成，需配合 --only")
    p.add_argument("--region", choices=["ov", "cn"], help="不填会自动判断")
    args = p.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    chosen = select(spec, args)
    OWNED.update(a["id"] for a in chosen)
    state = load_state()

    if args.redo:
        if not args.only:
            sys.exit("--redo 要配合 --only 指定素材，避免误删")
        drop = {"concept": ["concept", "model", "rigcheck", "rig"], "model": ["model", "rigcheck", "rig"]}[args.redo]
        for a in chosen:
            st = state.get(a["id"], {})
            for step in drop:
                st.pop(f"{step}_task", None)
                st.pop(f"{step}_file", None)
                st.get("credits", {}).pop(step, None)
        save_state(state)

    if args.plan:
        print_plan(spec, chosen, state)
        return

    api = Tripo(load_key(), args.region)
    bal = api.balance()
    print(f"站点 {api.base}  可用积分 {bal['balance']}（冻结 {bal['frozen']}）")
    if args.balance:
        return

    uploads = Uploads(api)
    failed = {}

    if args.stage in ("concept", "all"):
        for a in chosen:  # 图片任务账号并发为 1，一张张来
            try:
                do_concept(api, uploads, spec, a, state)
            except (TripoError, requests.RequestException) as e:
                failed[a["id"]] = f"概念图：{e}"
                log(a["id"], f"失败 {e}")

    if args.stage in ("model", "all"):
        todo = [a for a in chosen if a["id"] not in failed]
        with ThreadPoolExecutor(MODEL_WORKERS) as pool:
            futs = {pool.submit(do_model, api, uploads, spec, a, state): a for a in todo}
            for f in as_completed(futs):
                a = futs[f]
                try:
                    f.result()
                except (TripoError, requests.RequestException) as e:
                    failed[a["id"]] = f"模型：{e}"
                    log(a["id"], f"失败 {e}")

    if args.stage in ("anim", "all"):
        for a in chosen:
            if not a.get("anims") or a["id"] in failed:
                continue
            try:
                do_anims(api, a, state)
            except (TripoError, requests.RequestException) as e:
                failed[a["id"]] = f"动画：{e}"
                log(a["id"], f"失败 {e}")

    print()
    print_plan(spec, chosen, state)
    spent = sum(sum(state.get(a["id"], {}).get("credits", {}).values()) for a in chosen)
    print(f"\n这些素材累计消耗积分 {spent:g}；当前余额 {api.balance()['balance']}")
    for k, v in failed.items():
        print(f"失败 {k}：{v}")
    if failed:
        print("修好原因后直接重跑同一条命令，已完成的步骤会跳过。")


if __name__ == "__main__":
    main()
