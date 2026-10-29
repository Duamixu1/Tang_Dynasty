import * as THREE from "three";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";

// 查看 World Labs 生成的走廊泼溅。文件在 ../assets/worldlabs/<name>/splat_*.spz，通过 Vite 的 fs.allow 直接读上级目录。
const params = new URLSearchParams(location.search);
const name = params.get("world") || "corridor_v1";
const quality = params.get("q") || "500k";
const url = params.get("url") || `/@fs${ASSETS_DIR}/worldlabs/${name}/splat_${quality}.spz`;  // ?url= 可以直接加载任意 spz，用来测查看器本身
const status = document.getElementById("status");

const scene = new THREE.Scene();
scene.background = new THREE.Color("#F1E9DA");
const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.02, 500);
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
scene.add(new SparkRenderer({ renderer }));

const splat = new SplatMesh({
  url,
  onLoad: () => { status.textContent = `已加载 ${params.get("url") ? "外部文件" : name + " (" + quality + ")"}，点数 ${splat.numSplats ?? "?"}`; },
});
// World Labs / Spark 的 .spz 是 y 向下的 OpenCV 相机系，绕 X 转 180° 变成 three 的 y 向上
splat.quaternion.set(1, 0, 0, 0);
scene.add(splat);

// 预设机位：1 原始相机位置，2 往前走到走廊中段，3 回头
const presets = [
  { pos: [0, 0, 0], yaw: 0, pitch: 0 },
  { pos: [0, 0, -3], yaw: 0, pitch: 0 },
  { pos: [0, 0, -3], yaw: Math.PI, pitch: 0 },
];
let yaw = 0, pitch = 0;
function applyPreset(i) {
  const p = presets[i];
  camera.position.set(...p.pos); yaw = p.yaw; pitch = p.pitch;
}
applyPreset(0);

const keys = new Set();
addEventListener("keydown", (e) => {
  keys.add(e.code);
  if (e.code === "Digit1") applyPreset(0);
  if (e.code === "Digit2") applyPreset(1);
  if (e.code === "Digit3") applyPreset(2);
});
addEventListener("keyup", (e) => keys.delete(e.code));
let dragging = false, lx = 0, ly = 0;
renderer.domElement.addEventListener("mousedown", (e) => { dragging = true; lx = e.clientX; ly = e.clientY; });
addEventListener("mouseup", () => (dragging = false));
addEventListener("mousemove", (e) => {
  if (!dragging) return;
  yaw -= (e.clientX - lx) * 0.004; pitch -= (e.clientY - ly) * 0.004;
  pitch = Math.max(-1.4, Math.min(1.4, pitch)); lx = e.clientX; ly = e.clientY;
});
addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// 调试接口：截图脚本可以直接摆相机
window.__viewer = { camera, splat, setPose(x, y, z, yw, pt) { camera.position.set(x, y, z); yaw = yw; pitch = pt; } };

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1), speed = (keys.has("ShiftLeft") ? 3 : 1.2) * dt;
  camera.rotation.set(0, 0, 0, "YXZ"); camera.rotation.y = yaw; camera.rotation.x = pitch;
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
  const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
  if (keys.has("KeyW")) camera.position.addScaledVector(fwd, speed);
  if (keys.has("KeyS")) camera.position.addScaledVector(fwd, -speed);
  if (keys.has("KeyD")) camera.position.addScaledVector(right, speed);
  if (keys.has("KeyA")) camera.position.addScaledVector(right, -speed);
  if (keys.has("KeyE")) camera.position.y += speed;
  if (keys.has("KeyQ")) camera.position.y -= speed;
  renderer.render(scene, camera);
});
