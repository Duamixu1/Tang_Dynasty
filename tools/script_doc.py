"""把 web/src/data/script.json 导出成可读的 docs/06_文字.md。改文字改 json，再跑一次这个脚本。
用法：python3 tools/script_doc.py"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
s = json.loads((ROOT / "web/src/data/script.json").read_text(encoding="utf-8"))
L = ["# 游戏文字（由 tools/script_doc.py 从 web/src/data/script.json 导出，不要直接改这个文件）", ""]
L += ["## 开场卡", "", f"**{s['title']['name']}**　{s['title']['sub']}", ""] + [f"> {x}" for x in s["title"]["opening"]] + [""]
L += ["## 书生", "", "| 时机 | 台词 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in s["scholar"].items()] + [""]
b = s.get("brush", {})
if b:
    L += ["## 落笔过场字卡", "", f"- 使者出壁：{b['envoy']}", f"- 定形：{b['settle']}", ""]
L += ["## NPC", ""]
for key, n in s["npc"].items():
    L += [f"### {n['name']}", ""]
    for k, lines in n.items():
        if k == "name": continue
        L += [f"- **{k}**：" + " / ".join(lines)]
    L += [""]
L += ["## 证物", "", "| # | 名 | 在哪 | 说明 | 面 | 用于 |", "|---|---|---|---|---|---|"]
L += [f"| {k} | {e['name']} | {e['where']} | {e['desc']} | {s['ui']['pan_' + e['pan']]} | {s['ui'][e['for']]}{'（结局 ' + e['ending'] + '）' if 'ending' in e else ''} |" for k, e in s["evidence"].items()] + [""]
L += ["## 配对", "", "| 镜外 | 镜中 | 亮起 | 镜面清了以后一句 |", "|---|---|---|---|"]
L += [f"| {p['left']} | {p['right']} | {s['ui'][p['lights']]} | {p['line']} |" for p in s["pairs"]] + [""]
L += ["## 结局", ""]
for k, e in s["endings"].items():
    L += [f"### 结局 {k}", "", f"图谱页：**{e['card']}**", ""] + [f"> {x}" for x in e["lines"]] + ["", f"（另一件：{e['other']}）", ""]
L += ["## 界面用字", "", "、".join(f"{k}={v}" for k, v in s["ui"].items()), ""]
(ROOT / "docs/06_文字.md").write_text("\n".join(L), encoding="utf-8")
print("docs/06_文字.md")
