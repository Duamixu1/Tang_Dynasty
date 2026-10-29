// 游戏界面层：对话框、铜镜配对面板（镜外 / 镜中，类名沿用天秤时代的 scale / pan）、右下角铜镜指示、提示、拉门擦除、落笔占位、结尾卡（图谱页）。
// 全部是 DOM，不碰 Three.js。文字一律从 script.json 来，这里不写死任何一句。
// 用法见 src/game.js。
import { THREE } from "../game/logic.js";

const $ = (sel) => document.querySelector(sel);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/** 对话框：say(name, lines) 一句句显示，点击 / 空格 / E / 回车推进，全部说完 resolve。 */
export class Dialogue {
  constructor() {
    this.el = $("#dialogue"); this.nameEl = $("#dialogue .name"); this.textEl = $("#dialogue .text");
    this.open = false; this._resolve = null; this._queue = [];
    this.el.addEventListener("click", () => this.advance());
  }
  say(name, lines) {
    if (!lines || !lines.length) return Promise.resolve();
    this.open = true;
    this.el.classList.add("show");
    this.nameEl.textContent = name || "";
    this.nameEl.style.display = name ? "" : "none";
    this._queue = [...lines];
    this._next();
    return new Promise((r) => (this._resolve = r));
  }
  _next() {
    this.textEl.textContent = this._queue.shift();
    this.el.classList.toggle("last", this._queue.length === 0);
  }
  advance() {
    if (!this.open) return;
    if (this._queue.length) return this._next();
    this.open = false;
    this.el.classList.remove("show");
    const r = this._resolve; this._resolve = null; r && r();
  }
}

/** 右下角：形 / 真 / 理 三个字 + 天秤图标。update(signal) 每帧调，振幅越大抖得越厉害，升档时响铃。 */
export class ScaleHud {
  constructor(script, { onOpen } = {}) {
    this.el = $("#hud-scale"); this.icon = $("#hud-scale .icon"); this.hint = $("#hint");
    // 三个字按顺序对应 logic.js 的 THREE（状・事・见），不依赖 game.html 里 span 的 class 名
    const spans = document.querySelectorAll("#hud-scale .three span");
    this.chars = Object.fromEntries(THREE.map((k, i) => [k, spans[i]]));
    for (const k of THREE) this.chars[k].textContent = script.ui[k];
    this.el.addEventListener("click", () => onOpen && onOpen());
    this.t = 0; this.audio = null;
  }
  ensureAudio() {
    if (this.audio) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) this.audio = new AC();
  }
  /** 铃：一个正弦加泛音，快速衰减。档位越高音越高。 */
  ring(level = 1) {
    this.ensureAudio(); if (!this.audio) return;
    const ac = this.audio, t = ac.currentTime, g = ac.createGain();
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
    g.connect(ac.destination);
    for (const [mult, amp] of [[1, 1], [2.76, 0.4], [5.4, 0.15]]) {
      const o = ac.createOscillator(); const og = ac.createGain();
      o.frequency.value = (1760 + level * 220) * mult; og.gain.value = amp;
      o.connect(og); og.connect(g); o.start(t); o.stop(t + 1);
    }
  }
  setLit(lit) { for (const k in this.chars) this.chars[k].classList.toggle("lit", Boolean(lit[k])); }
  update(signal, dt) {
    this.t += dt;
    const a = signal ? signal.amplitude : 0;
    const ang = Math.sin(this.t * (8 + a * 20)) * a * 14;      // 度
    this.icon.style.transform = `rotate(${ang}deg)`;
    this.el.classList.toggle("near", a > 0.66);
    if (signal && signal.stepUp) this.ring(signal.ring);
  }
  showHint(text) { this.hint.textContent = text || ""; this.hint.classList.toggle("show", Boolean(text)); }
}

/** 天秤配对面板。open() 后玩家点证物放盘，两盘满了自动称。 */
export class ScalePanel {
  constructor(script, game, { dialogue, hud, onAllThree } = {}) {
    this.script = script; this.game = game; this.dialogue = dialogue; this.hud = hud; this.onAllThree = onAllThree;
    this.el = $("#scale-panel"); this.inv = $("#scale-panel .inventory"); this.result = $("#scale-panel .result");
    this.pans = { left: $("#scale-panel .pan.left .slot"), right: $("#scale-panel .pan.right .slot") };
    this.mirror = $("#scale-panel .mirror");   // 一面铜镜，左右两格；放错起雾晃一下，配对成功镜面清
    $("#scale-panel .close").addEventListener("click", () => this.close());
    $("#scale-panel .title").textContent = script.ui.scale;
    $("#scale-panel .close").textContent = "×";
    $("#scale-panel .pan.left .side").textContent = script.ui.pan_left; $("#scale-panel .pan.right .side").textContent = script.ui.pan_right;
    for (const side of ["left", "right"]) this.pans[side].addEventListener("click", () => this.takeBack(side));
    this.open = false; this.busy = false;
  }
  show() { this.open = true; this.el.classList.add("show"); this.result.textContent = ""; this.render(); }
  close() { if (this.busy) return; this.open = false; this.el.classList.remove("show"); }
  toggle() { this.open ? this.close() : this.show(); }
  render() {
    const { state } = this.game, ev = this.script.evidence;
    this.inv.innerHTML = "";
    for (const id of Object.keys(ev)) {
      if (!state.has[id]) continue;
      const e = ev[id], used = state.lit[e.for], onPan = state.pans.left === id || state.pans.right === id;
      const b = document.createElement("button");
      b.className = "item" + (used ? " used" : "") + (onPan ? " onpan" : "");
      b.innerHTML = `<img src="/icons/${id}.png" alt=""><div><b>${e.name}</b><span>${e.desc}</span></div>`;
      b.title = e.pan === "left" ? `← ${this.script.ui.pan_left}` : `${this.script.ui.pan_right} →`;
      b.disabled = used || onPan;
      b.addEventListener("click", () => this.put(id));
      this.inv.appendChild(b);
    }
    for (const side of ["left", "right"]) {
      const id = state.pans[side];
      this.pans[side].innerHTML = id ? `<img src="/icons/${id}.png" alt=""><span>${ev[id].name}</span>` : "";
      this.pans[side].classList.toggle("filled", Boolean(id));
    }
  }
  put(id) {
    if (this.busy) return;
    const r = this.game.put(id);
    if (!r.ok) { this.result.textContent = r.reason === "pan_full" ? this.script.ui.pan_full : ""; return; }
    this.result.textContent = "";
    this.render();
    const { left, right } = this.game.state.pans;
    if (left && right) this.weigh();
  }
  takeBack(side) {
    if (this.busy || !this.game.state.pans[side]) return;
    this.game.takeBack(side); this.render();
  }
  async weigh() {
    this.busy = true;
    const r = this.game.weigh();                       // 逻辑层已经清空两盘、记好状态
    if (r.result === "balanced") {
      this.el.classList.add("balanced");                // 镜面清
      this.result.textContent = this.script.ui.balanced;
      this.hud.setLit(this.game.state.lit);
      await wait(700);
      this.el.classList.remove("balanced");
      this.render();
      this.busy = false;
      this.close();                                    // 面板盖在对话框上面，先收起来再说台词
      await this.dialogue.say(null, r.lines);
      if (r.allThree) this.onAllThree && this.onAllThree();
    } else {
      this.el.classList.add("wrong");                   // 起雾，镜子晃一下
      await wait(800);
      this.el.classList.remove("wrong");
      this.render();
      this.result.textContent = r.line;
      this.busy = false;
    }
  }
}

/** 拉门擦除：一块纸色从左滑到右再滑走，中点时回调（切机位）。 */
export function fusumaWipe(midCallback, duration = 600) {
  const el = $("#wipe");
  el.style.transition = "none"; el.style.transform = "translateX(-100%)";
  void el.offsetWidth;
  el.style.transition = `transform ${duration / 2}ms ease-in`; el.style.transform = "translateX(0)";
  return new Promise((resolve) => {
    setTimeout(() => {
      midCallback && midCallback();
      el.style.transition = `transform ${duration / 2}ms ease-out`; el.style.transform = "translateX(100%)";
      setTimeout(resolve, duration / 2);
    }, duration / 2);
  });
}

/** 居中底部的交互提示："E 推门" 这类。 */
export class Prompt {
  constructor() { this.el = $("#prompt"); }
  set(text) { this.el.textContent = text || ""; this.el.classList.toggle("show", Boolean(text)); }
}

/** 小提示（拿到证物）：右上角淡入淡出。 */
export function toast(text, ms = 1800, icon = null) {
  const el = $("#toast"); el.innerHTML = (icon ? `<img src="/icons/${icon}.png" alt="">` : "") + `<span>${text}</span>`; el.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove("show"), ms);
}

/** 结尾卡：三个字 + 结果句 + 三行 + 另一件；"保存结果"画到 canvas 下载 PNG。 */
export function endingCard(script, card, lit) {
  const el = $("#ending");
  el.querySelector(".three").innerHTML = THREE.map((k) => `<span class="${lit[k] ? "lit" : ""}">${script.ui[k]}</span>`).join("");
  el.querySelector(".card").textContent = card.card;
  el.querySelector(".lines").innerHTML = card.lines.map((l) => `<p>${l}</p>`).join("");
  el.querySelector(".other").textContent = card.other || "";
  el.querySelector(".brand").textContent = `${script.title.name} · ${script.title.sub}`;
  const btn = el.querySelector(".save"); btn.textContent = script.ui.save_card;
  btn.onclick = () => downloadCard(script, card);
  el.classList.add("show");
}

function downloadCard(script, card) {
  const W = 1600, H = 900, c = document.createElement("canvas"); c.width = W; c.height = H;
  const g = c.getContext("2d");
  g.fillStyle = "#EFE4CC"; g.fillRect(0, 0, W, H);
  // 和纸颗粒：随机小点
  g.fillStyle = "rgba(50,45,72,0.05)";
  for (let i = 0; i < 6000; i++) g.fillRect(Math.random() * W, Math.random() * H, 2, 1);
  g.strokeStyle = "#4A2C1E"; g.lineWidth = 6; g.strokeRect(40, 40, W - 80, H - 80);
  g.fillStyle = "#4A2C1E"; g.textAlign = "center";
  g.font = "bold 150px 'Hiragino Mincho ProN', 'Songti SC', serif";
  g.fillText(THREE.map((k) => script.ui[k]).join("　"), W / 2, 300);
  g.font = "52px 'Hiragino Mincho ProN', 'Songti SC', serif";
  // 图谱句比画布宽：按字量宽度折行，尽量在句号后折
  const rows = [];
  let row = "";
  for (const ch of card.card) {
    if (g.measureText(row + ch).width > W - 240) { const cut = row.lastIndexOf("。") + 1; rows.push(cut > row.length / 2 ? row.slice(0, cut) : row); row = (cut > row.length / 2 ? row.slice(cut) : "") + ch; }
    else row += ch;
  }
  if (row) rows.push(row);
  rows.forEach((r, i) => g.fillText(r, W / 2, 410 + i * 66));
  g.font = "34px 'Hiragino Mincho ProN', 'Songti SC', serif"; g.fillStyle = "#74457A";
  const y0 = 410 + rows.length * 66 + 40;
  card.lines.forEach((l, i) => g.fillText(l, W / 2, y0 + i * 54));
  g.font = "26px 'Hiragino Sans GB', sans-serif"; g.fillStyle = "#9C3A2F";
  g.fillText(`${script.title.name} · ${script.title.sub}`, W / 2, H - 90);
  const a = document.createElement("a"); a.download = `${script.title.name}_结局.png`; a.href = c.toDataURL("image/png"); a.click();
}
