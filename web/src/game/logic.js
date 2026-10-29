/**
 * 玩法逻辑层：状态机、铜镜引导、镜外 / 镜中配对、入画、提示。纯函数，不依赖 Three.js。
 * 数据来自 web/src/data/script.json（文字）和 web/src/data/clues.json（线索位置与条件）。
 * 流程和文案的写法见 docs/10_画壁_流程与文案.md。
 *
 * 用法：
 *   const g = createGame(script, clues);
 *   g.talk('meng') → { lines, gained }
 *   g.interact('E1') → { ok, lines }
 *   g.enterPainting() / g.leavePainting() → { ok, lines }
 *   g.put('E1'); g.put('E2'); g.weigh() → { result:'balanced', lights:'zhuang', lines }
 *   g.scaleSignal([x,y,z]) → { target, distance, amplitude, ring }（铜镜起雾的程度）
 *   g.nextStep() → 'pick_E1' 等提示 id（攻略和防卡关用）
 *
 * pans 的 left / right 就是镜外 / 镜中，名字沿用天秤时代，界面上的字从 script.ui.pan_left / pan_right 来。
 */

export const THREE = ["zhuang", "shi", "jian"];

export function initialState() {
  return {
    phase: "play",            // play | brush（落笔过场）| ending
    zone: "Z0_gate",
    gateOpened: false,
    scaleIntro: false,        // 书生说过 scale_first
    enteredPainting: false,   // 进过画中殿（之后里面的线索才算“可发现”）
    inPainting: false,
    met: { meng: false, monk: false, tiannv: false },
    has: {},                  // 证物 id → true
    lit: { zhuang: false, shi: false, jian: false },
    pans: { left: null, right: null },
    ending: null,             // 'A' | 'B'
    lastRing: 0,              // 铜镜上一次起雾的档位
    counters: { wrongPairs: 0, talks: 0 },
    log: [],                  // 事件记录，调试和攻略统计用
  };
}

function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

export function createGame(script, cluesData, state = initialState()) {
  const clues = cluesData.clues;
  const scaleCfg = cluesData.scale;
  const painting = cluesData.painting;
  const say = script.scholar;
  const log = (type, data) => state.log.push({ type, ...data });
  const met = (paths) => paths.every((p) => Boolean(getPath(state, p)));

  function litCount() { return THREE.filter((k) => state.lit[k]).length; }

  function available(id) {
    const c = clues[id];
    if (!c || state.has[id]) return false;
    return met(c.requires);
  }

  function availableClues() { return Object.keys(clues).filter(available); }

  function cluePosition(id, npcPositions) {
    const c = clues[id];
    if (c.position) return c.position;
    if (c.npc && npcPositions && npcPositions[c.npc]) return npcPositions[c.npc].position;
    return null;
  }

  /** 铜镜：指向最近的“可发现且未拿到”的线索。覆盖层打开时调用方自己不调它。 */
  function scaleSignal(pos, npcPositions) {
    let best = null;
    for (const id of availableClues()) {
      if (id === "E6b" && state.has.E6a) continue;   // 已拿一件候选，镜子不再催另一件
      if (id === "E6a" && state.has.E6b) continue;
      const p = cluePosition(id, npcPositions);
      if (!p) continue;
      const d = Math.hypot(p[0] - pos[0], p[2] - pos[2]);   // 只算水平距离
      if (!best || d < best.distance) best = { target: id, distance: d };
    }
    if (!best) return { target: null, distance: Infinity, amplitude: 0, ring: 0 };
    const amplitude = Math.max(0, Math.min(1, 1 - best.distance / scaleCfg.radius));
    let ring = 0;
    scaleCfg.ringSteps.forEach((s, i) => { if (amplitude >= s) ring = i + 1; });
    const stepUp = ring > state.lastRing;        // 刚进入更近一档，UI 在这一帧响
    state.lastRing = ring;
    return { ...best, amplitude, ring, stepUp };
  }

  function gain(id) {
    if (state.has[id]) return false;
    state.has[id] = true;
    log("gain", { id });
    return true;
  }

  /** 对话：按状态选 script.npc[id] 里的哪一段，返回台词并推进状态。 */
  function talk(npc) {
    const n = script.npc[npc];
    if (!n) return { lines: [], gained: null };
    state.counters.talks++;
    const lines = [];
    let gained = null;
    const first = !state.met[npc];
    if (first) { state.met[npc] = true; lines.push(...n.first); log("meet", { npc }); }
    const waitingForPainting = state.lit.shi && !state.enteredPainting;
    if (npc === "meng") {
      if (!state.has.E3) { lines.push(...n.testimony, ...n.give_e3); gain("E3"); gained = "E3"; }
      else if (state.enteredPainting) lines.push(...n.after_painting);
      else if (waitingForPainting) lines.push(...n.hint_painting);
      else lines.push(...n.after_e3);
    } else if (npc === "monk") {
      if (waitingForPainting) lines.push(...n.hint_painting);
      else if (state.has.E4) lines.push(...n.after_e4);
      else if (!first) lines.push(...n.repeat);   // 第一次只有 first 那两句；之后提醒案上的东西
    } else if (npc === "tiannv") {
      if (!state.has.E6a) { lines.push(...n.give_e6a); gain("E6a"); gained = "E6a"; }
      else lines.push(...n.after_e6a);
    }
    return { lines, gained };
  }

  /**
   * 互动：target 是线索 id（E1 拾幞头、E2 对壁举镜、E4 翻题记、E5 拾金链、E6b 对榻举镜）或 'gate'。
   * 条件没满足时返回 ok=false，附带 clues.json 里 locked 指向的那句书生台词。
   */
  function interact(target) {
    if (target === "gate") {
      if (!state.gateOpened) { state.gateOpened = true; state.zone = "Z1_corridor"; log("gate", {}); return { ok: true, lines: [say.gate] }; }
      return { ok: true, lines: [] };
    }
    const c = clues[target];
    if (!c || state.has[target]) return { ok: false, lines: [] };
    if (!met(c.requires)) return { ok: false, lines: c.locked ? [say[c.locked]] : [] };
    const lines = [];
    if (!state.scaleIntro) { state.scaleIntro = true; lines.push(say.scale_first); }
    gain(target);
    return { ok: true, lines, gained: target };
  }

  // ---------- 入画 ----------
  function canEnterPainting() { return met(painting.requires); }

  function enterPainting() {
    if (!canEnterPainting()) return { ok: false, lines: [say[painting.locked]] };
    const firstTime = !state.enteredPainting;
    state.enteredPainting = true; state.inPainting = true;
    log("enter_painting", {});
    return { ok: true, lines: firstTime ? [say.enter_painting] : [] };
  }

  function leavePainting() {
    if (!state.inPainting) return { ok: false, lines: [] };
    state.inPainting = false;
    return { ok: true, lines: [say.leave_painting] };
  }

  // ---------- 镜外 / 镜中配对 ----------
  function put(id) {
    const e = script.evidence[id];
    if (!e || !state.has[id]) return { ok: false, reason: "not_owned" };
    if (state.lit[e.for]) return { ok: false, reason: "already_lit" };   // 已亮的字对应的证物不能再放
    if (state.pans[e.pan]) return { ok: false, reason: "pan_full" };
    state.pans[e.pan] = id;
    return { ok: true };
  }

  function takeBack(pan) {
    const id = state.pans[pan];
    state.pans[pan] = null;
    return id;
  }

  function weigh() {
    const { left, right } = state.pans;
    if (!left || !right) return { result: "incomplete" };
    const pair = script.pairs.find((p) => p.left === left && p.right === right);
    state.pans = { left: null, right: null };
    if (!pair) {
      state.counters.wrongPairs++;
      log("wrong", { left, right });
      return { result: "wrong", line: say.wrong };
    }
    state.lit[pair.lights] = true;
    if (pair.ending) state.ending = pair.ending;
    log("lit", { which: pair.lights, left, right });
    const lines = [pair.line, say[pair.lights]];
    if (litCount() === 3) { state.phase = "brush"; lines.push(say.all_three); }
    return { result: "balanced", lights: pair.lights, ending: pair.ending || null, lines, allThree: litCount() === 3 };
  }

  function finishBrush() { if (state.phase === "brush") state.phase = "ending"; return state.phase; }

  function endingCard() {
    if (!state.ending) return null;
    const e = script.endings[state.ending];
    const other = state.ending === "A" ? "E6b" : "E6a";
    return { card: e.card, lines: e.lines, other: state.has[other] ? e.other : null };
  }

  /** 下一步提示 id：攻略生成和防卡关都用它。顺序就是推荐路线。 */
  function nextStep() {
    if (state.phase === "brush") return "watch_brush";
    if (state.phase === "ending") return "save_card";
    if (!state.gateOpened) return "open_gate";
    if (!state.lit.zhuang) {
      if (!state.has.E1) return "pick_E1";
      if (!state.has.E2) return "look_mural_E2";
      return "weigh_E1_E2";
    }
    if (!state.lit.shi) {
      if (!state.has.E3) return "talk_meng_E3";
      if (!state.met.monk) return "talk_monk";
      if (!state.has.E4) return "read_desk_E4";
      return "weigh_E3_E4";
    }
    if (!state.lit.jian) {
      if (!state.enteredPainting) return "enter_painting";
      if (!state.has.E5) return "pick_E5";
      if (!state.has.E6a && !state.has.E6b) return "talk_tiannv";
      return "weigh_E5_E6";
    }
    return "done";
  }

  return {
    state, availableClues, available, scaleSignal, talk, interact, canEnterPainting, enterPainting, leavePainting,
    put, takeBack, weigh, finishBrush, endingCard, nextStep, litCount,
  };
}
