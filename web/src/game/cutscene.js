import * as THREE from "three";
import { loadActor } from "../world/graybox.js";
import { playOnce } from "../world/actors.js";

// 落笔过场（实时版）。五个镜头，总长约 15 秒，Space / Esc 跳过。
// 正式版换成 Blender 渲的视频时，只换 runBrushCutscene 的实现，调用方不动。
//   1  书生站在东壁前，字卡"状、事、见，都齐了"（镜头在书生身后）
//   2  金甲使者从壁画里鼓出来：起先是扁的、贴在墙上，一边往外走一边变厚（镜头慢推）
//   3  使者正面，低机位仰拍，字卡"壁中有神……"
//   4  落笔三拍：书生的手 K 动作 brush_k（取笔 / 悬腕 / 落），落的那一下屏幕上一笔墨划过，白闪
//   5  定形：使者被压回墙里，变成壁画上的一幅画，夜色退去
// 使者模型在开局 preloadBrushCutscene() 预载，过场结束后留在墙上（扁的），算壁画的一部分。
const $ = (s) => document.querySelector(s);
const ease = (t) => t * t * (3 - 2 * t);
const INK = "#2E2723";

let envoy = null;   // { wrap, ready }：wrap 不转，只沿世界 x 压扁（东壁法线就是 x）；里面的人物转 90° 面向回廊
export function preloadBrushCutscene(scene) {
  if (envoy) return envoy;
  const wrap = new THREE.Group(), inner = new THREE.Group();
  inner.rotation.y = Math.PI / 2;            // blender_lite 导出的人物面朝 +z，转到面朝 +x（从东壁看向回廊）
  wrap.add(inner); wrap.visible = false; scene.add(wrap);
  envoy = { wrap, ready: false };
  inner.add(loadActor("envoy", { height: 2.6, onLoad: () => (envoy.ready = true) }));
  return envoy;
}

// 屏幕上的一笔墨：一条粗笔画 + 一条细一点、稍错开的"飞白"，用 stroke-dashoffset 从左往右画出来
function inkLayer() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 1600 900"); svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
  Object.assign(svg.style, { position: "fixed", inset: "0", width: "100%", height: "100%", pointerEvents: "none", zIndex: 30 });
  const mk = (d, w, op) => {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d); p.setAttribute("fill", "none"); p.setAttribute("stroke", INK); p.setAttribute("stroke-width", w);
    p.setAttribute("stroke-linecap", "round"); p.setAttribute("stroke-linejoin", "round"); p.setAttribute("opacity", op);
    svg.appendChild(p); return p;
  };
  const main = mk("M360 330 C 580 350, 830 430, 1010 520 S 1260 640, 1300 610", 96, 0.95);
  const dry = mk("M372 360 C 600 385, 840 465, 1020 555 S 1250 668, 1290 646", 22, 0.5);
  const len = [main.getTotalLength(), dry.getTotalLength()];
  [main, dry].forEach((p, i) => { p.style.strokeDasharray = len[i]; p.style.strokeDashoffset = len[i]; });
  document.body.appendChild(svg);
  return {
    stroke(t) { const k = ease(t); main.style.strokeDashoffset = len[0] * (1 - k); dry.style.strokeDashoffset = len[1] * (1 - Math.min(1, k * 1.08)); },
    fade(t) { svg.style.opacity = 1 - t; },
    remove() { svg.remove(); },
  };
}

export function runBrushCutscene({ scene, camera, director, player, play, hud, script, cams }) {
  const night = $("#night"), flash = $("#flash"), text = $("#cut-text");
  const S = script.brush;
  const wallX = cams.layout.mural_kata.position[0], muralZ = cams.layout.mural_kata.position[2];
  const outX = wallX + 1.1;                  // 使者走出来站的位置，离墙 1.1 米
  const flatX = wallX + 0.17;                // 压扁时贴在壁画平面（墙 + 0.12）前面一点，像画在画上
  const standX = wallX + 3.4;                // 书生站在回廊中线附近，面向东壁（回廊只有 ±2.2 米宽，镜头都要留在里面）
  player.position.set(standX, 0, muralZ + 0.3); player.rotation.y = -Math.PI / 2; player.visible = true;
  play("idle");
  const e = preloadBrushCutscene(scene);
  e.wrap.visible = true; e.wrap.position.set(flatX, 0, muralZ); e.wrap.scale.set(0.03, 1, 1);
  director.manual = true;
  document.body.classList.add("cutscene");
  const ink = inkLayer();
  const say = (s, ms) => {
    text.textContent = s; text.style.fontSize = "";
    const w = text.offsetWidth, max = document.documentElement.clientWidth * 0.9;   // 字卡不换行，比画面宽就按比例缩字号
    if (w > max) text.style.fontSize = `${parseFloat(getComputedStyle(text).fontSize) * max / w}px`;
    text.classList.add("show"); if (ms) setTimeout(() => text.classList.remove("show"), ms);
  };
  const look = (p, q, fov) => { if (fov && camera.fov !== fov) { camera.fov = fov; camera.updateProjectionMatrix(); } camera.position.set(...p); camera.lookAt(...q); };
  const behind = [standX + 1.2, 2.0, muralZ + 3.4], wallMid = [wallX, 1.5, muralZ - 0.2];   // 书生右后方过肩
  let flashed = false;

  const shots = [
    { dur: 2.6, enter() { night.style.opacity = 0.35; say(script.scholar.all_three, 2100); },
      update(t) { look([behind[0], behind[1], behind[2] + 0.3 * t], wallMid, 40); } },
    { dur: 3.4, enter() { if (hud) hud.ring(2); },
      update(t) {
        const k = ease(t);
        e.wrap.position.x = THREE.MathUtils.lerp(flatX, outX, k);
        e.wrap.scale.x = THREE.MathUtils.lerp(0.03, 1, Math.min(1, k * 1.4));   // 先鼓出来，再往前走
        look([behind[0] - 0.8 * k, behind[1] - 0.1 * k, behind[2] - 0.6 * k], [wallX + 0.6 * k, 1.6, muralZ], 40 - 4 * k);
      } },
    { dur: 2.4, enter() { night.style.opacity = 0.5; say(S.envoy, 2000); if (hud) hud.ring(3); playOnce("envoy", "roar_k"); },
      update(t) { look([outX + 3.0, 0.75, muralZ + 1.9 - 0.3 * t], [outX, 2.05, muralZ], 34); } },   // 低机位仰拍，脸要进画
    // 落笔三拍是书生的手 K 动作 brush_k（tools/poses/scholar.json，24 帧/秒）：取笔 0.75 秒、悬腕 1.9–2.8 秒、落 3.1 秒、收 5 秒
    { dur: 4.4, enter() { text.classList.remove("show"); play("brush"); },
      update(t) {
        const sec = t * 4.4;
        if (sec < 2.7) look([standX - 1.6, 1.45, muralZ + 2.4], [standX, 1.4, muralZ], 32);         // 书生侧前方，看取笔、悬腕
        else look([standX - 0.6, 1.6, muralZ - 3.0], [standX - 1.2, 1.4, muralZ + 0.2], 40);       // 切到右侧远景：书生和使者同框，看落
        if (sec > 2.95) ink.stroke(Math.min(1, (sec - 2.95) / 0.5));
        if (sec > 3.3 && !flashed) { flashed = true; flash.style.opacity = 1; setTimeout(() => (flash.style.opacity = 0), 160); }
      } },
    { dur: 2.8, enter() { text.classList.remove("show"); setTimeout(() => say(S.settle, 1800), 500); },
      update(t) {
        const k = ease(t);
        e.wrap.position.x = THREE.MathUtils.lerp(outX, flatX, k);
        e.wrap.scale.x = THREE.MathUtils.lerp(1, 0.03, k);
        ink.fade(Math.min(1, t * 2));
        night.style.opacity = 0.5 * (1 - k);
        look([standX + 1.4, 2.0, muralZ + 1.8], [wallX, 1.5, muralZ - 0.3], 44);   // 书生身后斜看东壁，书生在画面右下
      } },
  ];

  let i = -1, t0 = 0, done = false, resolve;
  const promise = new Promise((r) => (resolve = r));
  const skip = (ev) => { if (ev.code === "Space" || ev.code === "Escape") finish(); };
  addEventListener("keydown", skip);
  function next(now) { i++; if (i >= shots.length) return finish(); t0 = now; shots[i].enter(); }
  function finish() {
    if (done) return; done = true;
    removeEventListener("keydown", skip);
    e.wrap.position.x = flatX; e.wrap.scale.x = 0.03;   // 跳过时也落到"画在墙上"的终态
    ink.remove();
    director.manual = false;
    document.body.classList.remove("cutscene");
    text.classList.remove("show"); night.style.opacity = 0; flash.style.opacity = 0;
    play("idle");
    resolve();
  }
  // 调用方每帧调 update(performance.now())，promise 在过场结束或跳过时 resolve
  return {
    promise,
    get active() { return !done; },
    update(now) {
      if (done) return;
      if (i < 0) return next(now);
      const t = (now - t0) / 1000 / shots[i].dur;
      if (t >= 1) { shots[i].update(1); return next(now); }
      shots[i].update(t);
    },
  };
}
