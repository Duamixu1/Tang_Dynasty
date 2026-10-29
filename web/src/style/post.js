import * as THREE from "three";

// 描边 + 绢壁后期，一个合成 shader 做完：
//   pass 1  场景法线 + 深度 → normalRT（scene.overrideMaterial = MeshNormalMaterial）
//   pass 2  场景颜色 → colorRT
//   pass 3  全屏合成：深度跳变画粗外轮廓，法线跳变画细内线；再叠屏幕空间绢壁纹（细颗粒 + 淡裂纹 + 零星剥落，tools/paper.py）、暗角、可选宽银幕黑边
// 描边色固定 canon 第 12 色赭墨 #4A2C1E。纸纹贴图按屏幕像素平铺，不跟镜头动。旧和纸在 paper_washi.png。
export class PaperOutlinePost {
  constructor(renderer, scene, camera) {
    this.renderer = renderer; this.scene = scene; this.camera = camera;
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    this.normalRT = new THREE.WebGLRenderTarget(size.x, size.y, { depthTexture: new THREE.DepthTexture(size.x, size.y, THREE.UnsignedIntType) });
    this.colorRT = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType });
    this.normalMat = new THREE.MeshNormalMaterial();
    const paper = new THREE.TextureLoader().load("/textures/paper.png");
    paper.wrapS = paper.wrapT = THREE.RepeatWrapping;
    paper.colorSpace = THREE.NoColorSpace;

    this.quadMat = new THREE.ShaderMaterial({
      uniforms: {
        tColor: { value: this.colorRT.texture },
        tNormal: { value: this.normalRT.texture },
        tDepth: { value: this.normalRT.depthTexture },
        tPaper: { value: paper },
        uRes: { value: size },
        uNear: { value: camera.near }, uFar: { value: camera.far },
        uOutlineColor: { value: new THREE.Color("#4A2C1E") },
        uPaperColor: { value: new THREE.Color("#EFE4CC") },
        uOutline: { value: 1 }, uPaper: { value: 1 }, uLetterbox: { value: 0 },
        uDepthThresh: { value: 0.012 },   // 相对深度差，超过算外轮廓
        uNormalThresh: { value: 0.72 },   // 法线夹角差，超过算内线
        uOuterWidth: { value: 1.6 },      // 外轮廓采样半径（像素）
        uInnerWidth: { value: 0.8 },
        uPaperScale: { value: 1.0 },      // 1 = 纸纹一像素对一像素
        uPaperStrength: { value: 0.15 },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
      `,
      fragmentShader: /* glsl */ `
        uniform sampler2D tColor, tNormal, tDepth, tPaper;
        uniform vec2 uRes;
        uniform float uNear, uFar, uDepthThresh, uNormalThresh, uOuterWidth, uInnerWidth, uPaperScale, uPaperStrength;
        uniform vec3 uOutlineColor, uPaperColor;
        uniform int uOutline, uPaper, uLetterbox;
        varying vec2 vUv;

        float linDepth(vec2 uv) {
          float z = texture2D(tDepth, uv).x * 2.0 - 1.0;
          return (2.0 * uNear * uFar) / (uFar + uNear - z * (uFar - uNear)) / uFar;   // 0..1
        }
        vec3 nrm(vec2 uv) { return texture2D(tNormal, uv).xyz * 2.0 - 1.0; }

        void main() {
          vec3 col = texture2D(tColor, vUv).rgb;
          vec2 px = 1.0 / uRes;

          if (uOutline == 1) {
            // 外轮廓：Roberts cross 取深度差，按中心深度归一化，远处线不会变粗变脏
            vec2 o = px * uOuterWidth;
            float dc = linDepth(vUv);
            float d1 = abs(linDepth(vUv + vec2( o.x,  o.y)) - linDepth(vUv - vec2( o.x,  o.y)));
            float d2 = abs(linDepth(vUv + vec2( o.x, -o.y)) - linDepth(vUv - vec2( o.x, -o.y)));
            float dEdge = smoothstep(uDepthThresh * 0.6, uDepthThresh * 1.4, max(d1, d2) / max(dc, 1e-4));
            // 内线：法线差。背景处法线为 0，用深度 < 1 挡掉天空
            vec2 i = px * uInnerWidth;
            vec3 nc = nrm(vUv);
            float nd = 0.0;
            nd = max(nd, 1.0 - dot(nc, nrm(vUv + vec2(i.x, 0.0))));
            nd = max(nd, 1.0 - dot(nc, nrm(vUv - vec2(i.x, 0.0))));
            nd = max(nd, 1.0 - dot(nc, nrm(vUv + vec2(0.0, i.y))));
            nd = max(nd, 1.0 - dot(nc, nrm(vUv - vec2(0.0, i.y))));
            float nEdge = smoothstep(uNormalThresh * 0.7, uNormalThresh * 1.3, nd) * step(dc, 0.999) * 0.45;
            float edge = clamp(max(dEdge, nEdge), 0.0, 1.0);
            col = mix(col, uOutlineColor, edge);
          }

          if (uPaper == 1) {
            // 和纸：按屏幕像素平铺，不随镜头动。灰度 0.5 为中性，亮的地方往纸白提，暗的地方压暗
            vec2 puv = gl_FragCoord.xy / (1024.0 * uPaperScale);
            float g = texture2D(tPaper, puv).r - 0.5;
            col *= 1.0 + g * uPaperStrength * 2.0;
            col = mix(col, uPaperColor, max(g, 0.0) * uPaperStrength * 0.6);
            // 轻暗角
            vec2 q = vUv - 0.5;
            col *= 1.0 - dot(q, q) * 0.18;
          }

          if (uLetterbox == 1) {
            // 2.39:1 黑边（用描边色，不用纯黑）
            float barH = max(0.0, (1.0 - (uRes.x / uRes.y) / 2.39) * 0.5);
            if (vUv.y < barH || vUv.y > 1.0 - barH) col = uOutlineColor * 0.6;
          }

          gl_FragColor = vec4(col, 1.0);
          #include <colorspace_fragment>
        }
      `,
      depthTest: false, depthWrite: false,
    });
    this.exclude = [];   // 这些物体不进法线/深度通道（高斯泼溅没法走 overrideMaterial，也不需要描边）
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.quadMat);
    this.quadScene = new THREE.Scene(); this.quadScene.add(this.quad);
    this.quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  }

  setFlags({ outline = true, paper = true, letterbox = false }) {
    this.quadMat.uniforms.uOutline.value = outline ? 1 : 0;
    this.quadMat.uniforms.uPaper.value = paper ? 1 : 0;
    this.quadMat.uniforms.uLetterbox.value = letterbox ? 1 : 0;
  }

  resize() {
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    this.normalRT.setSize(size.x, size.y); this.colorRT.setSize(size.x, size.y);
    this.quadMat.uniforms.uRes.value = size;
  }

  render() {
    const { renderer, scene, camera } = this;
    const bg = scene.background;
    scene.background = null;
    scene.overrideMaterial = this.normalMat;
    const hidden = this.exclude.filter((o) => o.visible); hidden.forEach((o) => (o.visible = false));
    renderer.setRenderTarget(this.normalRT);
    renderer.setClearColor(0x000000, 1);
    renderer.clear();
    renderer.render(scene, camera);
    hidden.forEach((o) => (o.visible = true));
    scene.overrideMaterial = null;
    scene.background = bg;
    renderer.setRenderTarget(this.colorRT);
    renderer.render(scene, camera);
    renderer.setRenderTarget(null);
    this.quadMat.uniforms.uNear.value = camera.near; this.quadMat.uniforms.uFar.value = camera.far;
    renderer.render(this.quadScene, this.quadCam);
  }
}
