import * as THREE from "three";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { makeToonMaterial, setPatternsEnabled, patternsEnabled, isFaceMaterial, FACE_TOON } from "./style/toon.js";
import { PaperOutlinePost } from "./style/post.js";
import { createGame } from "./game/logic.js";
import { buildGraybox, inRect, CHAR_PATTERNS } from "./world/graybox.js";
import { CameraDirector } from "./world/camera_director.js";
import { Dialogue, ScaleHud, ScalePanel, Prompt, fusumaWipe, toast, endingCard } from "./ui/overlay.js";
import { runBrushCutscene, preloadBrushCutscene } from "./game/cutscene.js";
import { updateActors, playOnce } from "./world/actors.js";
import { attachProps } from "./world/attach.js";
import script from "./data/script.json";
import clues from "./data/clues.json";
import cams from "./world/cameras.json";

// 灰盒游戏台（唐风《画壁》）：回廊 + 房间是方块加 Tripo 道具，书生是 Tripo 轻量模型，逻辑走 logic.js，界面和机位按 cameras.json。
// 操作：WASD 走，E 互动/说话，Tab 开铜镜（界面还叫天秤，第 24 项换），对话里空格/点击推进。?nopost=1 关后期。
const params = new URLSearchParams(location.search);
const status = document.getElementById("status");

const scene = new THREE.Scene();
scene.background = new THREE.Color("#EFE4CC");
const camera = new THREE.PerspectiveCamera(28, innerWidth / innerHeight, 0.1, 120);
const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.getElementById("stage").appendChild(renderer.domElement);
const light = new THREE.DirectionalLight(0xffffff, 1); light.position.set(-1.5, 3, 2.5); scene.add(light);

const world = buildGraybox(scene, cams, clues);
// World Labs 泼溅（走廊一块、房间各一块）。原始帧 y 向下、正前方沿 +z；绕 X 转 180° 变成 y 向上、正前方沿 -z，
// 再绕 Y 转 yawDeg 对准房间朝向，缩放，最后平移到 layout 里写的位置
const splats = [];
const splatList = cams.layout.splats || (cams.layout.splat ? [cams.layout.splat] : []);
let spark = null;
if (splatList.length) { spark = new SparkRenderer({ renderer }); scene.add(spark); }
for (const S of splatList) {
  const m = new SplatMesh({ url: `/@fs${ASSETS_DIR}/worldlabs/${S.name}/splat_${S.quality || "500k"}.spz` });
  const flip = new THREE.Quaternion(1, 0, 0, 0);
  const yaw = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), THREE.MathUtils.degToRad(S.yawDeg || 0));
  m.quaternion.copy(yaw.multiply(flip));
  m.scale.setScalar(S.scale);
  m.frustumCulled = false;   // Spark 算的包围盒不对，镜头一偏泼溅整个被剔掉，画面只剩背景色
  m.position.set(...S.position);
  m.userData.for = S.for || "corridor";
  // 房间泼溅门外那截脑补走廊已经用 tools/spz_clip.py 在文件层面裁掉（quality 指向裁过的文件）。
  // 注意：不要在运行时改泼溅的 visible / opacity / position，也不要挂 SplatEdit：Spark 会把可见点数算成 0，整个泼溅系统停摆（都试过）。
  scene.add(m); splats.push(m);
}
const splat = splats[0] || null;
const game = createGame(script, clues);
// 画中殿只能从东壁进出：yuki 房的门洞不算可走（画中殿就是 yuki 房），东壁前和殿里各放一个"入画 / 出画"点
const yukiDoorZ = cams.layout.rooms.yuki.door[2];
world.walk.doors = world.walk.doors.filter((r) => !(r.x0 > 0 && Math.abs((r.z0 + r.z1) / 2 - yukiDoorZ) < 0.01));
world.interact.push(
  { id: "enter_painting", kind: "portal", position: clues.painting.outside, radius: 1.4, label: "enter_painting", to: clues.painting.inside, enter: true },
  { id: "leave_painting", kind: "portal", position: clues.painting.inside, radius: 1.1, label: "leave_painting", to: clues.painting.outside, enter: false },
  { id: "censer", kind: "look", position: [cams.layout.courtyard.well[0], 0, cams.layout.courtyard.well[2] + 1.0], radius: 1.4, label: "interact", line: "censer" },
);
const dialogue = new Dialogue();
const prompt = new Prompt();
const director = new CameraDirector(camera, cams, { onTransition: (apply) => fusumaWipe(apply) });
for (const [id, obj] of Object.entries(world.npcs)) director.registerAnchor(id, obj);
const hud = new ScaleHud(script, { onOpen: () => panel.toggle() });
const panel = new ScalePanel(script, game, { dialogue, hud, onAllThree: startBrush });
preloadBrushCutscene(scene);   // 金甲使者模型先载好，落笔过场一开始就能出壁
const post = new PaperOutlinePost(renderer, scene, camera);
post.setFlags({ outline: true, paper: true, letterbox: true });
post.exclude.push(...splats);
const usePost = params.get("nopost") !== "1";

// 角色纹样表 CHAR_PATTERNS 在 graybox.js（和 NPC 共用）：按贴图颜色最接近哪个唐色板色来铺，屏幕空间

// ---- 角色 ----
const player = new THREE.Group(); player.position.set(...(cams.layout.gate.start || [0, 0, cams.layout.gate.position[2] + 2.2])); scene.add(player);
player.rotation.y = Math.PI;   // 开场背对寺门、面朝回廊里的镜头：背后的竹笈和伞盖不挡脸
let mixer = null, actions = {}, current = null;
// 动作名：手 K 版叫 idle_k / walk_k / exorcise_k，Tripo 预设叫 idle / walk / slash，哪个有用哪个
const ALIAS = { idle: ["idle_k", "idle"], walk: ["walk_k", "walk"], brush: ["brush_k"] };
function play(name) {
  const key = (ALIAS[name] || [name]).find((k) => actions[k]) || name;
  const a = actions[key]; if (!a || a === current) return;
  if (current) current.fadeOut(0.2);
  a.reset().fadeIn(0.2).play(); current = a;
}
const modelParam = params.get("model") || "processed/scholar_posed.glb";   // 书生 + 手 K 动作（idle_k / walk_k / nod_k / brush_k）和挂点，tools/poses/scholar.json
const playerLoader = new GLTFLoader().setDRACOLoader(new DRACOLoader().setDecoderPath("/draco/"));
playerLoader.load(`/@fs${ASSETS_DIR}/${modelParam}`, (gltf) => {
  const m = gltf.scene;
  m.traverse((o) => { if (o.isMesh) { o.frustumCulled = false; const map = o.material.map; if (map) map.colorSpace = THREE.SRGBColorSpace; o.material = makeToonMaterial({ map, shadeColor: "#74457A", shadeMix: 0.35, threshold: 0.42, pattern: { space: "screen", scale: 120, byPalette: CHAR_PATTERNS }, ...(isFaceMaterial(o.material) ? FACE_TOON : {}) }); } });
  const box = new THREE.Box3().setFromObject(m), h = box.max.y - box.min.y, s = 1.7 / h;
  m.scale.setScalar(s); m.position.set(-(box.min.x + box.max.x) / 2 * s, -box.min.y * s, -(box.min.z + box.max.z) / 2 * s);
  player.add(m);
  // 兽首笔、书箧、铜镜按挂点挂上（data/attach.json），材质和角色一样走平涂，不铺纹样
  attachProps(m, playerLoader, (u) => `/@fs${ASSETS_DIR}/${u}`, (o) => { const map = o.material.map; if (map) map.colorSpace = THREE.SRGBColorSpace; o.material = makeToonMaterial({ map, shadeColor: "#74457A", shadeMix: 0.35, threshold: 0.42 }); })
    .catch((e) => console.warn("道具挂载失败", e.message));
  if (gltf.animations.length) {
    mixer = new THREE.AnimationMixer(m);
    for (const clip of gltf.animations) {
      const name = clip.name.replace(/^preset:(biped:)?/, "").replace(/\|.*$/, "").toLowerCase();
      actions[name] = mixer.clipAction(clip);
      if (name === "brush_k") { actions[name].setLoop(THREE.LoopOnce); actions[name].clampWhenFinished = true; }   // 落笔只走一遍，停在最后一拍
    }
    play("idle");
  }
  status.textContent = `${script.title.name}`;
}, undefined, (e) => { status.textContent = "模型加载失败：" + e.message; });

// ---- 输入与移动 ----
const keys = new Set();
addEventListener("keydown", (e) => {
  if (e.repeat) return;
  hud.ensureAudio();
  if (dialogue.open) { if (["Space", "KeyE", "Enter"].includes(e.code)) { e.preventDefault(); dialogue.advance(); } return; }
  if (panel.open) { if (e.code === "Tab" || e.code === "Escape") { e.preventDefault(); panel.close(); } return; }
  if (game.state.phase !== "play") return;
  if (e.code === "KeyN") { setPatternsEnabled(!patternsEnabled()); return; }
  if (e.code === "Tab") { e.preventDefault(); panel.show(); return; }
  if (e.code === "KeyE" || e.code === "Enter") { e.preventDefault(); doInteract(); return; }
  keys.add(e.code);
});
addEventListener("keyup", (e) => keys.delete(e.code));
addEventListener("blur", () => keys.clear());

const walkRects = () => [game.state.gateOpened ? world.walk.corridor : null, world.walk.gate, ...world.walk.doors, ...world.walk.rooms].filter(Boolean);
function canStand(p) { return walkRects().some((r) => inRect(p, r)); }
function move(dt) {
  if (cutscene) return;                              // 过场里动作由过场控制
  if (dialogue.open || panel.open || game.state.phase !== "play") { play("idle"); return; }
  const d = new THREE.Vector3((keys.has("KeyD") ? 1 : 0) - (keys.has("KeyA") ? 1 : 0), 0, (keys.has("KeyS") ? 1 : 0) - (keys.has("KeyW") ? 1 : 0));
  if (d.lengthSq() === 0) { play("idle"); return; }
  d.normalize().multiplyScalar(1.6 * dt);
  const p = player.position, nx = p.clone().add(new THREE.Vector3(d.x, 0, 0)), nz = p.clone().add(new THREE.Vector3(0, 0, d.z));
  if (canStand(nx)) p.x = nx.x;
  if (canStand(nz)) p.z = nz.z;
  player.rotation.y = Math.atan2(d.x, d.z);
  play("walk");
}

// ---- 区域与机位 ----
function zoneFor(p) {
  for (const r of world.zoneRects) if (inRect(p, r)) return r.zone;
  return game.state.gateOpened ? "Z1_corridor" : "Z0_gate";
}
director.setZone("Z0_gate", { immediate: true });

// ---- 交互 ----
function nearest() {
  let best = null;
  for (const it of world.interact) {
    if (it.kind === "gate" && game.state.gateOpened) continue;
    if (it.kind !== "gate" && !game.state.gateOpened) continue;   // 门没推开之前只认推门
    if (it.kind === "clue" && game.state.has[it.id]) continue;
    // 入画点在拿到 E2 之后才出现（还没齐时互动会说"墙就是墙"），出画点只在画里出现
    if (it.kind === "portal" && (it.enter ? game.state.inPainting || !game.state.has.E2 : !game.state.inPainting)) continue;
    const d = Math.hypot(it.position[0] - player.position.x, it.position[2] - player.position.z);
    if (d <= it.radius && (!best || d < best.d)) best = { it, d };
  }
  return best && best.it;
}
let lastProgress = performance.now(), hintLevel = 0;
function progressed() { lastProgress = performance.now(); hintLevel = 0; hud.showHint(""); }

async function doInteract() {
  const it = nearest(); if (!it) return;
  if (it.kind === "npc") {
    director.pushOverlay("Z4_dialogue", it.object);
    playOnce(it.id, "talk_k");
    const r = game.talk(it.id);
    await dialogue.say(script.npc[it.id].name, r.lines);
    director.popOverlay();
    if (r.gained) gained(r.gained);
    progressed();
    return;
  }
  if (it.kind === "gate") {
    const r = game.interact("gate");
    world.gate.visible = false;
    await dialogue.say(null, r.lines);
    progressed();
    return;
  }
  if (it.kind === "portal") {
    const r = it.enter ? game.enterPainting() : game.leavePainting();
    if (r.ok) {
      await fusumaWipe(() => { player.position.set(...it.to); player.rotation.y = it.enter ? Math.PI / 2 : -Math.PI / 2; });
      progressed();
    }
    await dialogue.say(null, r.lines);
    return;
  }
  if (it.kind === "look") { await dialogue.say(null, [script.scholar[it.line]]); return; }
  // 线索（条件不满足时逻辑层返回书生的拒绝台词，比如老僧的案"先打个招呼"）
  if (it.overlay) director.pushOverlay(it.overlay);
  const r = game.interact(it.id);
  if (!r.ok) { await dialogue.say(null, r.lines); director.popOverlay(); return; }
  if (it.mesh) it.mesh.visible = false;
  gained(it.id);
  await dialogue.say(null, [...r.lines, script.evidence[it.id].desc]);
  director.popOverlay();
  progressed();
}
function gained(id) { toast(`${script.ui.gained}：${script.evidence[id].name}`, 2200, id); }

let cutscene = null;
async function startBrush() {
  prompt.set("");
  cutscene = runBrushCutscene({ scene, camera, director, player, play, hud, script, cams });
  await cutscene.promise;
  cutscene = null;
  game.finishBrush();
  endingCard(script, game.endingCard(), game.state.lit);
}

// ---- 防卡关提示 ----
function hintTick() {
  if (game.state.phase !== "play" || dialogue.open || panel.open) return;
  const idle = (performance.now() - lastProgress) / 1000;
  const id = game.nextStep(), text = script.hints[id];
  if (idle > 150 && hintLevel < 2) { hintLevel = 2; hud.showHint(text ? text + " " + script.ui.hint_more : ""); }
  else if (idle > 90 && hintLevel < 1) { hintLevel = 1; hud.showHint(text || ""); }
}

addEventListener("resize", () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); post.resize(); });
window.__game = { game, player, camera, director, dialogue, panel, world, splat, spark, play, interact: doInteract, renderer, scene, post, setPatterns: setPatternsEnabled, startBrush,
  // 把 3D 画面存到 assets/processed/shots/<name>.jpg（开发服务器的 /__shot 接口）
  async shot(name) { const r = await fetch("/__shot", { method: "POST", body: JSON.stringify({ name, data: renderer.domElement.toDataURL("image/jpeg", 0.92) }) }); return r.json(); } };

// 关于 Spark 的排序：它回读 GPU 深度靠定时器轮询，页面在后台（浏览器面板隐藏）时定时器被限到 1 秒甚至 1 分钟一次，
// 一次排序要几秒到几分钟，期间活跃点数是 0、泼溅整块不画。这不是故障，页面可见时排序只要几毫秒。
// 不要加"排序卡住就复位"的看门狗：复位会打断进行中的回读，结果永远是 0。

const clock = new THREE.Clock();
let currentZone = null;
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  move(dt);
  if (mixer) mixer.update(dt);
  updateActors(dt);
  if (cutscene) cutscene.update(performance.now());
  const z = zoneFor(player.position);
  if (z !== currentZone && !director.overlay && !cutscene) { currentZone = z; director.setZone(z); }   // 过场里自己摆相机，不切区不擦除
  director.update(player);
  if (!cutscene) player.visible = !(director.overlay && cams.zones[director.overlay.id].hidePlayer);
  const it = nearest();
  prompt.set(it && !dialogue.open && !panel.open && game.state.phase === "play" ? `E　${it.kind === "npc" ? script.ui.talk + " · " + script.npc[it.id].name : script.ui[it.label]}` : "");
  const signal = dialogue.open || panel.open ? null : game.scaleSignal([player.position.x, 0, player.position.z], cams.npc_positions);
  hud.update(signal, dt);
  hintTick();
  if (usePost) post.render(); else renderer.render(scene, camera);
});
