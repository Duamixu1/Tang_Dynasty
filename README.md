# 唐风志异 ·《画壁》

一个网页 3D 小游戏的留档：画法借怪化猫（纸纹、平涂、彩色描边、屏幕空间纹样），画里的东西换成唐朝，故事取《聊斋志异·画壁》，怪的样子取《山海经》（金甲使者画成陆吾）。

玩家是一个记异的游方书生，腰间一面铜镜：在寺院回廊、客房、僧房、画中殿里找线索，把"镜外"和"镜中"的证物配成对，拼出 **状・事・见** 三个字，落笔把怪定成图谱上的一页。两个结局。

## 目录

| 位置 | 内容 |
|---|---|
| `docs/` | 方案和设定：`08` 转向方案、`09` 玩法与资产清单、`10` 流程与文案、`02_设定` 画风 canon 与唐风 12 色色板、`02_待办` 进度表、`11` 上线规划 |
| `web/` | Three.js + Vite 工程。`game.html` 是灰盒游戏台（一局能从进寺走到图谱页），`character.html` 是角色画风查看页 |
| `tools/` | 素材流水线：Tripo 出 2D 概念图 / 3D 模型（`tripo_scene.py`、`tripo_gen.py`、`tripo_v2.py`），Blender 减面、手 K 动作、挂件、高清脸投影（`blender_*.py`），纹样和纸纹生成（`patterns.py`、`paper.py`） |
| `assets/concept/` | 2D 概念图（`scenes/13` 起是唐风版，`_lineup_tang.png` 是总览） |
| `assets/processed/` | 网页直接用的轻量模型（人物、道具、挂件）和截图 `shots/` |
| `assets/tripo_raw/` | Tripo 原始输出（未减面），留作重新处理用 |

## 跑起来

```bash
cd web && npm install && npm run dev
```

打开 `http://localhost:5173/game.html`。操作：WASD 走、E 互动、Tab 开铜镜、空格推进对话。

重新生成素材需要在根目录建 `.env`（照 `.env.example`），填 Tripo / World Labs 的 API Key。
