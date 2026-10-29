// 运行：cd web && node --test src/game/logic.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createGame } from "./logic.js";

const here = new URL(".", import.meta.url);
const script = JSON.parse(readFileSync(new URL("../data/script.json", here), "utf8"));
const clues = JSON.parse(readFileSync(new URL("../data/clues.json", here), "utf8"));
const cams = JSON.parse(readFileSync(new URL("../world/cameras.json", here), "utf8"));
const npcPos = cams.npc_positions;

function playToShi(g) {
  g.interact("gate");
  g.interact("E1"); g.interact("E2");
  g.put("E1"); g.put("E2");
  assert.equal(g.weigh().lights, "zhuang");
  g.talk("meng");
  g.talk("monk"); g.interact("E4");
  g.put("E3"); g.put("E4");
  assert.equal(g.weigh().lights, "shi");
}

test("完整通关 结局 A（人归）", () => {
  const g = createGame(script, clues);
  assert.equal(g.nextStep(), "open_gate");
  playToShi(g);
  assert.equal(g.nextStep(), "enter_painting");
  assert.ok(g.enterPainting().ok);
  assert.equal(g.nextStep(), "pick_E5");
  assert.ok(g.interact("E5").ok);
  assert.equal(g.talk("tiannv").gained, "E6a");
  g.put("E5"); g.put("E6a");
  const r = g.weigh();
  assert.equal(r.lights, "jian"); assert.equal(r.ending, "A"); assert.ok(r.allThree);
  assert.equal(g.state.phase, "brush");
  assert.equal(g.nextStep(), "watch_brush");
  g.finishBrush();
  assert.equal(g.endingCard().card, script.endings.A.card);
  assert.equal(g.endingCard().other, null, "没照榻下就不提另一件");
});

test("结局 B 且两件都拿时结果卡提另一件", () => {
  const g = createGame(script, clues);
  playToShi(g);
  g.enterPainting();
  g.interact("E5"); g.talk("tiannv"); g.interact("E6b");
  g.put("E5"); g.put("E6b");
  assert.equal(g.weigh().ending, "B");
  g.finishBrush();
  assert.equal(g.endingCard().other, script.endings.B.other);
});

test("状、事没齐之前进不了画", () => {
  const g = createGame(script, clues);
  g.interact("gate");
  const r = g.enterPainting();
  assert.equal(r.ok, false); assert.equal(r.lines[0], script.scholar.painting_before);
  assert.equal(g.state.enteredPainting, false);
});

test("进出画：第一次进有一句，出来有一句，再进不重复", () => {
  const g = createGame(script, clues);
  playToShi(g);
  assert.deepEqual(g.enterPainting().lines, [script.scholar.enter_painting]);
  assert.deepEqual(g.leavePainting().lines, [script.scholar.leave_painting]);
  assert.equal(g.state.inPainting, false);
  assert.deepEqual(g.enterPainting().lines, []);
  assert.equal(g.leavePainting().ok, true);
  assert.equal(g.leavePainting().ok, false, "不在画里时出不了画");
});

test("放错回弹、不扣证物、计数", () => {
  const g = createGame(script, clues);
  g.interact("gate"); g.interact("E1"); g.talk("meng");          // 有 E1 和 E3，都是镜外
  assert.equal(g.put("E1").ok, true);
  assert.equal(g.put("E3").ok, false, "镜外已满");
  g.takeBack("left"); g.put("E3");
  g.interact("E2"); g.put("E2");                                 // E3 + E2 是错的
  const r = g.weigh();
  assert.equal(r.result, "wrong"); assert.equal(r.line, script.scholar.wrong);
  assert.equal(g.state.counters.wrongPairs, 1);
  assert.ok(g.state.has.E3 && g.state.has.E2);
  assert.deepEqual(g.state.pans, { left: null, right: null });
});

test("已亮的字对应证物不能再放", () => {
  const g = createGame(script, clues);
  g.interact("gate"); g.interact("E1"); g.interact("E2"); g.put("E1"); g.put("E2"); g.weigh();
  assert.equal(g.put("E1").reason, "already_lit");
});

test("铜镜指向最近的可发现线索，画中殿的线索进画前不算", () => {
  const g = createGame(script, clues);
  g.interact("gate");
  let s = g.scaleSignal([-1, 0, -3], npcPos);
  assert.equal(s.target, "E1");
  assert.ok(s.amplitude > 0.5);
  s = g.scaleSignal([7.6, 0, -12], npcPos);       // 站在榻边，但还没进过画
  assert.ok(!["E5", "E6a", "E6b"].includes(s.target));
  playToShi(g);
  g.enterPainting();
  s = g.scaleSignal([7.6, 0, -12], npcPos);
  assert.equal(s.target, "E6b");
});

test("铜镜档位只在变近时报 stepUp", () => {
  const g = createGame(script, clues);
  g.interact("gate");
  const far = g.scaleSignal([0, 0, 6], npcPos);     // 离 E1 约 11 米，超出半径
  assert.equal(far.ring, 0);
  const near = g.scaleSignal([-1.4, 0, -4.2], npcPos);
  assert.ok(near.ring >= 3 && near.stepUp);
  const again = g.scaleSignal([-1.4, 0, -4.2], npcPos);
  assert.equal(again.stepUp, false);
});

test("孟龙潭的话随进度变化", () => {
  const g = createGame(script, clues);
  g.interact("gate");
  let t = g.talk("meng");
  assert.deepEqual(t.lines, [...script.npc.meng.first, ...script.npc.meng.testimony, ...script.npc.meng.give_e3]);
  assert.equal(t.gained, "E3");
  assert.deepEqual(g.talk("meng").lines, script.npc.meng.after_e3);
  g.interact("E1"); g.interact("E2"); g.put("E1"); g.put("E2"); g.weigh();
  g.talk("monk"); g.interact("E4"); g.put("E3"); g.put("E4"); g.weigh();
  assert.deepEqual(g.talk("meng").lines, script.npc.meng.hint_painting);
  g.enterPainting(); g.leavePainting();
  assert.deepEqual(g.talk("meng").lines, script.npc.meng.after_painting);
});

test("老僧：先见面才能翻题记，翻完说幻由人生，事亮后指路入画", () => {
  const g = createGame(script, clues);
  g.interact("gate");
  const locked = g.interact("E4");
  assert.equal(locked.ok, false); assert.deepEqual(locked.lines, [script.scholar.desk_before]);
  assert.deepEqual(g.talk("monk").lines, script.npc.monk.first);
  assert.deepEqual(g.talk("monk").lines, script.npc.monk.repeat);
  assert.equal(g.interact("E4").ok, true);
  assert.deepEqual(g.talk("monk").lines, script.npc.monk.after_e4);
  g.interact("E1"); g.interact("E2"); g.put("E1"); g.put("E2"); g.weigh();
  g.talk("meng"); g.put("E3"); g.put("E4"); g.weigh();
  assert.deepEqual(g.talk("monk").lines, script.npc.monk.hint_painting);
});

test("天女第一次说话给镜中的螺髻，之后只剩一句", () => {
  const g = createGame(script, clues);
  playToShi(g); g.enterPainting();
  const t = g.talk("tiannv");
  assert.equal(t.gained, "E6a");
  assert.deepEqual(t.lines, [...script.npc.tiannv.first, ...script.npc.tiannv.give_e6a]);
  assert.deepEqual(g.talk("tiannv").lines, script.npc.tiannv.after_e6a);
});

test("nextStep 推荐路线覆盖全部状态", () => {
  const g = createGame(script, clues);
  const seen = [g.nextStep()];
  g.interact("gate"); seen.push(g.nextStep());
  g.interact("E1"); seen.push(g.nextStep());
  g.interact("E2"); seen.push(g.nextStep());
  g.put("E1"); g.put("E2"); g.weigh(); seen.push(g.nextStep());
  g.talk("meng"); seen.push(g.nextStep());
  g.talk("monk"); seen.push(g.nextStep());
  g.interact("E4"); seen.push(g.nextStep());
  g.put("E3"); g.put("E4"); g.weigh(); seen.push(g.nextStep());
  g.enterPainting(); seen.push(g.nextStep());
  g.interact("E5"); seen.push(g.nextStep());
  g.talk("tiannv"); seen.push(g.nextStep());
  g.put("E5"); g.put("E6a"); g.weigh(); seen.push(g.nextStep());
  g.finishBrush(); seen.push(g.nextStep());
  assert.deepEqual(seen, ["open_gate", "pick_E1", "look_mural_E2", "weigh_E1_E2", "talk_meng_E3", "talk_monk",
    "read_desk_E4", "weigh_E3_E4", "enter_painting", "pick_E5", "talk_tiannv", "weigh_E5_E6", "watch_brush", "save_card"]);
});

test("每个提示 id 都有文字，每个配对的证物都存在", () => {
  for (const id of ["open_gate", "pick_E1", "look_mural_E2", "weigh_E1_E2", "talk_meng_E3", "talk_monk", "read_desk_E4",
    "weigh_E3_E4", "enter_painting", "pick_E5", "talk_tiannv", "weigh_E5_E6"]) assert.ok(script.hints[id], id);
  for (const p of script.pairs) {
    assert.equal(script.evidence[p.left].pan, "left", p.left);
    assert.equal(script.evidence[p.right].pan, "right", p.right);
    assert.ok(script.scholar[p.lights] && script.ui[p.lights], p.lights);
  }
  for (const [id, c] of Object.entries(clues.clues)) if (c.locked) assert.ok(script.scholar[c.locked], id);
});
