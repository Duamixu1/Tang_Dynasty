import * as THREE from "three";

// 机位调度：读 cameras.json 的 zones，按类型摆相机。
//   fixed    固定位置 + 注视点
//   dolly    沿某轴跟随角色，落后 followOffset，始终朝 lookDirection
//   anchored 挂在某个物体（NPC、天秤）的局部坐标上，用于覆盖层
// 区由外面（game.js 按角色所在区域）决定，这里只负责"切"和"每帧更新"。切区时调用 onTransition 做擦除。
export class CameraDirector {
  constructor(camera, cams, { onTransition } = {}) {
    this.camera = camera; this.cams = cams; this.zones = cams.zones;
    this.onTransition = onTransition;
    this.current = null; this.overlay = null; this.anchors = {};
    camera.fov = cams.fov; camera.near = cams.near; camera.far = cams.far; camera.updateProjectionMatrix();
    this._tmp = new THREE.Vector3(); this._tmp2 = new THREE.Vector3();
  }
  registerAnchor(name, object3d) { this.anchors[name] = object3d; }

  /** 切主区。immediate 不做擦除（开场用）。 */
  async setZone(id, { immediate = false } = {}) {
    if (id === this.current) return;
    const apply = () => { this.current = id; this.apply(id, null); };
    if (immediate || !this.onTransition) apply();
    else await this.onTransition(apply);
  }
  /** 覆盖层机位（看壁画、对话），退出时回主区。anchorObj 可以临时指定锚点物体。 */
  pushOverlay(id, anchorObj = null) { this.overlay = { id, anchorObj }; }
  popOverlay() { this.overlay = null; }

  apply(id, player) {
    const z = this.zones[id]; if (!z) return;
    const cam = this.camera;
    const fov = z.fov || this.cams.fov;
    if (cam.fov !== fov) { cam.fov = fov; cam.updateProjectionMatrix(); }
    if (z.type === "fixed") {
      cam.position.set(...z.position); cam.lookAt(...z.lookAt);
    } else if (z.type === "dolly" && player) {
      const p = player.position;
      const along = THREE.MathUtils.clamp(p.z + z.followOffset, z.range[0], z.range[1]);
      cam.position.set(z.x, z.height, along);
      this._tmp.set(...z.lookDirection).normalize().add(cam.position);
      cam.lookAt(this._tmp);
    } else if (z.type === "anchored") {
      const a = (this.overlay && this.overlay.anchorObj) || this.anchors[z.anchor]; if (!a) return;
      a.updateWorldMatrix(true, false);
      cam.position.copy(this._tmp.set(...z.offset).applyMatrix4(a.matrixWorld));
      cam.lookAt(this._tmp2.set(...z.lookAtOffset).applyMatrix4(a.matrixWorld));
    }
  }
  update(player) {
    if (this.manual) return;                       // 过场自己摆相机
    if (this.overlay) this.apply(this.overlay.id, player);
    else if (this.current) this.apply(this.current, player);
  }
}
