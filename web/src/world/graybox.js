import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { makeToonMaterial, isFaceMaterial, FACE_TOON } from "../style/toon.js";
import { POSED, registerActor } from "./actors.js";

// 灰盒场景（唐风《画壁》）：按 cameras.json 的 layout 用方块拼回廊、三间房、院子，颜色只用唐风 12 色（docs/02_设定.md）。
// Tripo 出的道具（assets/processed/props/）和 NPC 模型（assets/processed/<id>_lite.glb）异步加载后摆进来，没加载完之前先是方块。
// 返回：可走区域矩形、可交互点（线索、NPC、门）、可按需隐藏的物体。以后换成正式场景只要保持这些接口。
const C = { paper: "#EFE4CC", cinnabar: "#D9503C", earth: "#9C3A2F", gold: "#D7A54A", malachite: "#5FA07A", azurite: "#3A5BA0", purple: "#74457A", ochre: "#A0623A", black: "#2E2723", skin: "#F3DCC8", rouge: "#E48C92", ink: "#4A2C1E" };
export const PALETTE = C;
// 灰盒各颜色默认铺什么纹样（世界空间，scale 单位米），按 docs/02 的纹样分配表
const PATTERN_BY_COLOR = {
  [C.malachite]: { tile: "baoxianghua", scale: 0.9, color: C.paper, mix: 0.55 },   // 地砖：莲花 / 宝相花
  [C.earth]: { tile: "lianzhu", scale: 0.6, color: C.gold, mix: 0.6 },             // 砖道：联珠
  [C.paper]: { tile: "rendong", scale: 1.4, color: C.skin, mix: 0.35 },            // 墙：忍冬，很淡
  [C.purple]: { tile: "baoxianghua", scale: 1.0, color: C.gold, mix: 0.5 },        // 藻井：宝相花
  [C.azurite]: { tile: "lianzhu", scale: 0.5, color: C.paper, mix: 0.6 },          // 经幡
  [C.cinnabar]: { tile: "lianzhu", scale: 0.5, color: C.paper, mix: 0.5 },
  [C.ochre]: { tile: "rendong", scale: 0.8, color: C.gold, mix: 0.18 },            // 木头
  [C.gold]: { tile: "juancao", scale: 0.4, color: C.earth, mix: 0.5 },
};
// 角色纹样：按贴图颜色最接近哪个色板色来铺，屏幕空间（原作"纹样贴在屏幕上"的做法）。scale 是一个周期多少 CSS 像素
export const CHAR_PATTERNS = [
  { color: C.azurite, tile: "lianzhu", patColor: C.paper, mix: 0.8 },      // 青袍：联珠团窠
  { color: C.cinnabar, tile: "baoxianghua", patColor: C.gold, mix: 0.7 },  // 朱砂半臂：宝相花
  { color: C.earth, tile: "baoxianghua", patColor: C.rouge, mix: 0.5 },
  { color: C.gold, tile: "juancao", patColor: C.earth, mix: 0.5 },         // 领袖缘：卷草
  { color: C.ochre, tile: "rendong", patColor: C.gold, mix: 0.4 },         // 书箧、袈裟：忍冬
  { color: C.rouge, tile: "lianzhu", patColor: C.paper, mix: 0.5 },        // 天女的裙
  { color: C.paper }, { color: C.skin }, { color: C.black }, { color: C.purple }, { color: C.malachite }, { color: C.ink },
];
const mat = (color, pattern = PATTERN_BY_COLOR[color]) => makeToonMaterial({ color, shadeColor: C.purple, shadeMix: 0.3, threshold: 0.35, pattern: pattern ? { space: "world", ...pattern } : null });
const box = (w, h, d, color) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));

const loader = new GLTFLoader().setDRACOLoader(new DRACOLoader().setDecoderPath("/draco/"));
const CHAR_TOON = { shadeColor: C.purple, shadeMix: 0.35, threshold: 0.42, pattern: { space: "screen", scale: 120, byPalette: CHAR_PATTERNS } };
const PROP_TOON = { shadeColor: C.purple, shadeMix: 0.3, threshold: 0.4, pattern: null };
function toonify(root, opts) {
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.frustumCulled = false;
    const map = o.material.map; if (map) map.colorSpace = THREE.SRGBColorSpace;
    o.material = makeToonMaterial({ map, ...opts, ...(isFaceMaterial(o.material) ? FACE_TOON : {}) });
  });
}
// 道具：blender_lite.py 已把原点放在脚底中心、高度按 assets.json 统一，直接摆。height 可再缩放到场景需要的高度
export function loadProp(name, { position = [0, 0, 0], rotationY = 0, height = null, onLoad = null } = {}) {
  const grp = new THREE.Group(); grp.position.set(...position); grp.rotation.y = rotationY;
  loader.load(`/@fs${ASSETS_DIR}/processed/props/${name}.glb`, (gltf) => {
    const m = gltf.scene; toonify(m, PROP_TOON);
    if (height) { const b = new THREE.Box3().setFromObject(m); m.scale.setScalar(height / (b.max.y - b.min.y)); }
    grp.add(m); onLoad && onLoad(m);
  }, undefined, (e) => console.warn("道具加载失败", name, e.message));
  return grp;
}
// 人物：脚底对齐原点，统一 height 米；替换掉占位方块。有手 K 动作的（actors.js 的 POSED）读 <id>_posed.glb 并注册动作
export function loadActor(name, { height = 1.7, onLoad = null } = {}) {
  const grp = new THREE.Group();
  loader.load(`/@fs${ASSETS_DIR}/processed/${name}${POSED.has(name) ? "_posed" : "_lite"}.glb`, (gltf) => {
    const m = gltf.scene; toonify(m, CHAR_TOON);
    const b = new THREE.Box3().setFromObject(m), s = height / (b.max.y - b.min.y);
    m.scale.setScalar(s); m.position.set(-(b.min.x + b.max.x) / 2 * s, -b.min.y * s, -(b.min.z + b.max.z) / 2 * s);
    grp.add(m); registerActor(name, m, gltf.animations); onLoad && onLoad(m, gltf);
  }, undefined, (e) => console.warn("人物加载失败", name, e.message));
  return grp;
}

export function buildGraybox(scene, cams, clues) {
  const L = cams.layout, H = L.corridor.ceiling;
  const g = new THREE.Group(); scene.add(g);
  const put = (m, x, y, z) => { m.position.set(x, y, z); g.add(m); return m; };
  const [cx0, cx1] = L.corridor.x, [cz0, cz1] = L.corridor.z;
  const cw = cx1 - cx0, cl = cz1 - cz0, cmz = (cz0 + cz1) / 2;

  const splatList = L.splats || (L.splat ? [{ ...L.splat, for: "corridor" }] : []);
  const splatFor = new Set(splatList.map((s) => s.for));
  const splat = splatFor.has("corridor");   // 回廊是 World Labs 泼溅时，灰盒只建门、房间和院子
  const hasSplat = (room) => splatFor.has(room);
  if (!splat) {
    // 回廊：石绿莲花方砖地 + 中央土红砖道 + 两侧金边
    put(box(cw, 0.1, cl, C.malachite), 0, -0.05, cmz);
    put(box(1.6, 0.02, cl, C.earth), 0, 0.011, cmz);
    put(box(0.08, 0.025, cl, C.gold), -0.84, 0.012, cmz); put(box(0.08, 0.025, cl, C.gold), 0.84, 0.012, cmz);
    // 平棊藻井：绛紫底宝相花
    put(box(cw, 0.1, cl, C.purple), 0, H + 0.05, cmz);
    // 尽头墙 + 金格殿门两扇（道具）
    put(box(cw, H, 0.2, C.paper), 0, H / 2, cz0 - 0.1);
    put(loadProp("hall_door", { height: 3.0, rotationY: Math.PI / 2 + 0.35 }), -0.62, 0, cz0 + 0.1);   // 左扇，半开
    put(loadProp("hall_door", { height: 3.0, rotationY: -Math.PI / 2 - 0.35 }), 0.62, 0, cz0 + 0.1);
    put(box(1.3, 0.05, 0.05, C.gold), 0, 3.05, cz0 + 0.05);
    // 门口墙（门两侧）
    put(box((cw - 1.8) / 2, H, 0.2, C.paper), cx0 + (cw - 1.8) / 4, H / 2, cz1 + 0.1);
    put(box((cw - 1.8) / 2, H, 0.2, C.paper), cx1 - (cw - 1.8) / 4, H / 2, cz1 + 0.1);
    put(box(cw, H - 2.4, 0.2, C.paper), 0, H - (H - 2.4) / 2, cz1 + 0.1);
  }
  const gate = new THREE.Group();
  if (!splat) {   // 寺门：两扇朱砂木门，推开后隐藏
    gate.add(put(box(0.9, 2.4, 0.12, C.cinnabar), -0.45, 1.2, cz1 + 0.1));
    gate.add(put(box(0.9, 2.4, 0.12, C.cinnabar), 0.45, 1.2, cz1 + 0.1));
  }
  g.add(gate);
  if (!splat) put(box(cw, 0.1, 4, C.ochre), 0, -0.05, cz1 + 2);   // 门外一小块地

  // 墙：按门洞切段。左墙只有院子一个门洞，右墙三个
  function wallWithDoors(x, doorsZ, color) {
    const edges = [cz0, ...doorsZ.flatMap((z) => [z - 0.9, z + 0.9]).sort((a, b) => a - b), cz1];
    for (let i = 0; i < edges.length; i += 2) {
      const a = edges[i], b = edges[i + 1]; if (b - a < 0.01) continue;
      put(box(0.2, H, b - a, color), x, H / 2, (a + b) / 2);
    }
    for (const z of doorsZ) put(box(0.2, H - 2.2, 1.8, color), x, H - (H - 2.2) / 2, z);   // 门楣
  }
  const rooms = L.rooms, cy = L.courtyard;
  let mural = null;
  if (!splat) {
    // 右墙：客房、僧房开门洞；画中殿（yuki）只能从东壁入画，不开门洞，封成墙
    wallWithDoors(cx1, Object.entries(rooms).filter(([k]) => k !== "yuki").map(([, r]) => r.door[2]), C.paper);
    wallWithDoors(cx0, [cy.door[2]], C.paper);
    // 壁画（左墙上，状的线索 E2）：土红底卷草，中间天女的位置先用一个胭脂色圆
    mural = put(new THREE.Mesh(new THREE.PlaneGeometry(3.2, 2.2), mat(C.earth, { tile: "juancao", scale: 0.7, color: C.gold, mix: 0.7 })), L.mural_kata.position[0] + 0.12, L.mural_kata.position[1], L.mural_kata.position[2]);
    mural.rotation.y = Math.PI / 2;
    const girl = put(new THREE.Mesh(new THREE.CircleGeometry(0.35, 24), mat(C.rouge)), L.mural_kata.position[0] + 0.13, 1.3, L.mural_kata.position[2] + 0.6);
    girl.rotation.y = Math.PI / 2;
    // 两侧壁画的大色块（其它墙段）：每 3 米一块土红画面，让墙不是整面白
    for (let z = cz1 - 1.5; z > cz0 + 1; z -= 3) for (const [x, ry] of [[cx0 + 0.11, Math.PI / 2], [cx1 - 0.11, -Math.PI / 2]]) {
      if (Math.abs(z - L.mural_kata.position[2]) < 1.8 && x < 0) continue;
      const p = put(new THREE.Mesh(new THREE.PlaneGeometry(2.4, 2.0), mat(C.earth, { tile: "juancao", scale: 0.7, color: C.gold, mix: 0.5 })), x, 2.6, z);
      p.rotation.y = ry;
    }
  }
  // 回廊两侧：朱砂柱（道具）、石灯（道具）、檐下经幡（道具，石青 / 朱砂交替）
  if (!splat) {
    let k = 0;
    for (let z = cz1 - 1.0; z > cz0 + 0.5; z -= 3, k++) {
      for (const x of [cx0 + 0.35, cx1 - 0.35]) {
        put(loadProp("column", { height: H }), x, 0, z);
        // 东壁（壁画）前不放石灯：落笔过场的仰拍和壁画特写会被它挡住下角
        if (x < 0 && Math.abs(z - 1.5 - L.mural_kata.position[2]) < 2.2) continue;
        put(loadProp("stone_lantern", { height: 1.3 }), x + (x < 0 ? 0.6 : -0.6), 0, z - 1.5);
      }
      const banner = put(loadProp("banner", { height: 2.4, onLoad: (m) => { if (k % 2) m.traverse((o) => { if (o.isMesh) o.material.uniforms.uColor.value.set(C.cinnabar).multiplyScalar(1.0); }); } }), (k % 2 ? -1 : 1) * 0.9, H - 0.3 - 2.4, z - 1.5);
      banner.userData.k = k;
    }
  }

  // 房间：地面 + 三面墙 + 藻井
  function room(r, floorColor, key, floorPattern) {
    if (hasSplat(key)) return;
    const [x0, x1] = r.x, [z0, z1] = r.z, w = x1 - x0, d = z1 - z0, mx = (x0 + x1) / 2, mz = (z0 + z1) / 2;
    put(new THREE.Mesh(new THREE.BoxGeometry(w, 0.1, d), mat(floorColor, floorPattern)), mx, -0.05, mz);
    if (splat) {   // 靠回廊一侧的墙，留门洞（没泼溅时这面墙由回廊的 wallWithDoors 建）
      const dz = r.door[2];
      put(box(0.2, H, dz - 0.9 - z0, C.paper), x0 - 0.1, H / 2, (z0 + dz - 0.9) / 2);
      put(box(0.2, H, z1 - (dz + 0.9), C.paper), x0 - 0.1, H / 2, (dz + 0.9 + z1) / 2);
      put(box(0.2, H - 2.2, 1.8, C.paper), x0 - 0.1, H - (H - 2.2) / 2, dz);
    }
    put(box(w, 0.1, d, C.purple), mx, H + 0.05, mz);
    put(box(0.2, H, d, C.paper), x1 + 0.1, H / 2, mz);
    put(box(w, H, 0.2, C.paper), mx, H / 2, z0 - 0.1);
    put(box(w, H, 0.2, C.paper), mx, H / 2, z1 + 0.1);
    put(loadProp("column", { height: H }), x1 - 0.35, 0, z0 + 0.35);
  }
  // maids = 客房（孟龙潭），utayama = 僧房（老僧），yuki = 画中殿（天女）。id 还是手鞠案的，第 24 项换文字时一起改
  room(rooms.maids, C.ochre, "maids");
  room(rooms.utayama, C.ochre, "utayama");
  room(rooms.yuki, C.malachite, "yuki", { tile: "baoxianghua", scale: 0.9, color: C.rouge, mix: 0.7 });   // 画中殿：纹样更密更艳
  // 房间里的东西：客房两张矮桌；僧房的案（道具）+ 题记（E4）；画中殿的禅床（道具，E6b 对榻举镜）和门边的断链（E5）
  if (!hasSplat("maids")) { const m = rooms.maids; put(box(1.0, 0.3, 0.6, C.ochre), m.x[0] + 1.5, 0.15, m.z[1] - 0.8); put(box(1.0, 0.3, 0.6, C.ochre), m.x[0] + 4, 0.15, m.z[0] + 0.8); }
  // 线索位置都从 clues.json 读；npc 类线索（E3、E6a）没有坐标，不摆东西
  const pos = (id, fallback) => clues.clues[id]?.position || fallback;
  const e4 = pos("E4", [6, 0, -6.8]);
  const desk = put(loadProp("desk_fish", { height: 0.45, rotationY: Math.PI }), e4[0], 0, e4[2]);
  const ledger = put(box(0.4, 0.04, 0.3, C.paper), desk.position.x - 0.35, 0.47, desk.position.z);
  const y = rooms.yuki;
  const e6b = pos("E6b", [y.x[1] - 1.3, 0, (y.z[0] + y.z[1]) / 2]);
  put(loadProp("bed", { height: 0.7, rotationY: Math.PI / 2 }), e6b[0], 0, e6b[2]);
  const e5 = pos("E5", [y.x[0] + 1.4, 0, y.z[0] + 0.6]);
  const chain = put(new THREE.Mesh(new THREE.TorusGeometry(0.12, 0.03, 8, 16), mat(C.gold)), e5[0], 0.03, e5[2]); chain.rotation.x = Math.PI / 2;

  // 院子：石绿地 + 香炉（道具）+ 四周矮墙 + 桃花，天空开着
  if (!hasSplat("courtyard")) {
    const [x0, x1] = cy.x, [z0, z1] = cy.z, w = x1 - x0, d = z1 - z0, mx = (x0 + x1) / 2, mz = (z0 + z1) / 2;
    put(box(w, 0.1, d, C.malachite), mx, -0.05, mz);
    put(box(0.2, 1.0, d, C.paper), x0 - 0.1, 0.5, mz); put(box(w, 1.0, 0.2, C.paper), mx, 0.5, z0 - 0.1); put(box(w, 1.0, 0.2, C.paper), mx, 0.5, z1 + 0.1);
    put(loadProp("censer", { height: 1.2 }), cy.well[0], 0, cy.well[2]);
    put(new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 0.12, 20), mat(C.paper)), cy.well[0], 0.06, cy.well[2]);
    for (const [x, z] of [[x0 + 1, z0 + 1], [x1 - 1, z1 - 1], [x0 + 1.5, z1 - 1.5]]) {
      put(box(0.14, 1.4, 0.14, C.ochre), x, 0.7, z);
      put(new THREE.Mesh(new THREE.SphereGeometry(0.7, 12, 8), mat(C.rouge)), x, 1.8, z);
    }
    for (const [x, z] of [[x0 + 0.6, mz], [x1 - 0.6, mz]]) put(loadProp("stone_lantern", { height: 1.3 }), x, 0, z);
  }

  // 回廊地上朱生落下的幞头（E1，道具）
  const e1 = pos("E1", [-1.4, 0, -4.6]);
  const futou = put(loadProp("futou", { height: 0.2, rotationY: 0.6 }), e1[0], 0, e1[2]);

  // NPC：Tripo 模型（npc_positions 的 id 就是模型名：meng / monk / tiannv），加载前先是圆柱占位
  const npcs = {};
  for (const [id, n] of Object.entries(cams.npc_positions)) {
    const grp = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.28, 1.25, 14), mat(C.azurite)); body.position.y = 0.62;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.17, 14, 10), mat(C.skin)); head.position.y = 1.45;
    grp.add(body, head);
    grp.add(loadActor(id, { height: id === "tiannv" ? 1.65 : 1.7, onLoad: () => { body.visible = false; head.visible = false; } }));
    grp.position.set(...n.position);
    grp.lookAt(grp.position.x + n.facing[0], grp.position.y, grp.position.z + n.facing[2]);
    g.add(grp); npcs[id] = grp;
  }

  // 可走区域：回廊（门开后含门口）、房间、院子，门洞各一小块连通
  const rect = (x0, x1, z0, z1) => ({ x0, x1, z0, z1 });
  const pad = 0.3;
  const walk = {
    gate: splat ? rect(cx0 + pad, cx1 - pad, cz0 + pad, cz1 - 0.3) : rect(cx0 + pad, cx1 - pad, cz1 + 0.4, cz1 + 3.2),
    corridor: rect(cx0 + pad, cx1 - pad, cz0 + pad, cz1 - 0.1),
    doors: [],
    rooms: [],
  };
  for (const [key, r] of [...Object.entries(rooms), ["courtyard", cy]]) {
    walk.rooms.push(rect(r.x[0] + pad, r.x[1] - pad, r.z[0] + pad, r.z[1] - pad));
    if (key === "yuki") continue;   // 画中殿没有门洞，入画 / 出画由 game.js 按 clues.painting 传送
    const inward = r.door[0] > 0 ? [r.door[0] - 1.3, r.door[0] + 0.6] : [r.door[0] - 0.6, r.door[0] + 1.3];
    walk.doors.push(rect(inward[0], inward[1], r.door[2] - 0.75, r.door[2] + 0.75));
  }

  // 可交互点
  const interact = [
    { id: "gate", kind: "gate", position: L.gate.interact || [0, 0, cz1 + 0.6], radius: 1.6, label: "open_door" },
    { id: "E1", kind: "clue", position: e1, radius: 1.3, label: "pick", mesh: futou },
    { id: "E2", kind: "clue", position: [L.mural_kata.position[0] + 1.0, 0, L.mural_kata.position[2]], radius: 1.6, label: "mirror", overlay: "Z1a_mural" },
    { id: "E4", kind: "clue", position: [desk.position.x, 0, desk.position.z + 0.8], radius: 1.3, label: "mirror", mesh: ledger },
    { id: "E5", kind: "clue", position: e5, radius: 1.3, label: "pick", mesh: chain },
    { id: "E6b", kind: "clue", position: e6b, radius: 1.3, label: "mirror" },
    ...Object.keys(npcs).map((id) => ({ id, kind: "npc", position: cams.npc_positions[id].position, radius: 1.6, label: "talk", object: npcs[id] })),
  ];

  // 区域判定：角色在哪个矩形里就是哪个区
  const zoneRects = [
    ["Z2_maids_room", rooms.maids], ["Z2a_utayama_room", rooms.utayama], ["Z2b_yuki_room", rooms.yuki], ["Z3_courtyard", cy],
  ].map(([zone, r]) => ({ zone, x0: r.x[0], x1: r.x[1], z0: r.z[0], z1: r.z[1] }));

  return { group: g, gate, walk, interact, npcs, zoneRects, mural };
}

export function inRect(p, r) { return p.x >= r.x0 && p.x <= r.x1 && p.z >= r.z0 && p.z <= r.z1; }
