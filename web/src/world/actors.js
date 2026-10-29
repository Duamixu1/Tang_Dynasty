import * as THREE from "three";

// NPC 和使者的手 K 动作（tools/poses/<id>.json → assets/processed/<id>_posed.glb）。
// 每个人物都有 idle_k（循环）和一个一次性动作：孟龙潭 / 老僧 / 天女是 talk_k，使者是 roar_k。
// graybox.loadActor 加载完调 registerActor；游戏每帧调 updateActors(dt)；说话时调 playOnce(id, "talk_k")，播完自动回待机。
export const POSED = new Set(["meng", "monk", "tiannv", "envoy"]);

const actors = {};   // id → { mixer, actions, idle }

export function registerActor(id, model, clips) {
  if (!clips || !clips.length) return;
  const mixer = new THREE.AnimationMixer(model);
  const actions = {};
  for (const clip of clips) actions[clip.name] = mixer.clipAction(clip);
  const idle = actions.idle_k;
  if (idle) { idle.play(); idle.time = Math.random() * idle.getClip().duration; }   // 错开，几个人不同步呼吸
  mixer.addEventListener("finished", (e) => {
    if (e.action === idle || !idle) return;
    e.action.fadeOut(0.3); idle.reset().fadeIn(0.3).play();
  });
  actors[id] = { mixer, actions, idle };
}

export function playOnce(id, name) {
  const a = actors[id]; const act = a && a.actions[name];
  if (!act) return;
  act.reset(); act.setLoop(THREE.LoopOnce, 1); act.clampWhenFinished = true;
  act.fadeIn(0.25).play();
  if (a.idle) a.idle.fadeOut(0.25);
}

export function updateActors(dt) {
  for (const a of Object.values(actors)) a.mixer.update(dt);
}
