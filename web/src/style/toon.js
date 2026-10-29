import * as THREE from "three";

// 2 阶平涂材质：固有色 + 一层阴影色，没有高光、没有真实光照衰减。
// 阴影色不是把固有色压暗，而是往 canon 里的"绛紫"(#74457A) 偏一点，像赛璐珞的阴影层。
// 只认场景里的第一盏平行光（取 uLightDir）。支持蒙皮（SkinnedMesh 自动走骨骼变形）。
//
// 纹样（pattern）：
//   { tile: "baoxianghua"|"lianzhu"|"juancao"|"rendong", space: "screen"|"world", scale, color, mix }
//     screen：按屏幕像素铺，不跟物体动（原作人物身上纹样"透出来"的做法），scale 是一个周期多少 CSS 像素
//     world：按世界坐标三平面投影，跟着表面走（地面、墙），scale 是一个周期多少米
//   { space, byPalette: [{ color, tile, patColor, mix }, ...] }
//     按贴图颜色最接近哪个色板色来决定铺哪种纹样，给 Tripo 烘好贴图的角色用；没列出的颜色不铺
// setPatternsEnabled(false) 全局关掉，方便对比。

export const PATTERN_NAMES = ["baoxianghua", "lianzhu", "juancao", "rendong"];   // 宝相花、联珠团窠、卷草、忍冬（tools/patterns.py --set tang）
const PATTERN_ASPECT = { baoxianghua: 1, lianzhu: 1, juancao: 0.5, rendong: 0.5 };   // 高/宽，和 tools/patterns.py 输出一致
const ENABLED = { value: 1 };
const PIXEL_RATIO = { value: Math.min(devicePixelRatio || 1, 2) };
let textures = null;
function patternTextures() {
  if (textures) return textures;
  const loader = new THREE.TextureLoader();
  textures = PATTERN_NAMES.map((n) => {
    const t = loader.load(`/textures/patterns/${n}.png`);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.NoColorSpace; t.anisotropy = 4;
    return t;
  });
  return textures;
}
// 脸：tools/blender_face_decal.py 把高清脸单独做成名字以 _face 结尾的材质。脸上几乎不上阴影（网格法线会在脸上切出块状紫影），也不铺纹样
export const isFaceMaterial = (m) => /_face$/.test((m && m.name) || "");
export const FACE_TOON = { shadeMix: 0.06, pattern: null };
export function setPatternsEnabled(v) { ENABLED.value = v ? 1 : 0; }
export function patternsEnabled() { return ENABLED.value === 1; }
const lin = (c) => new THREE.Color(c).convertSRGBToLinear();
const MAXPAL = 12;

export function makeToonMaterial({ map = null, color = "#ffffff", shadeColor = "#74457A", shadeMix = 0.35, threshold = 0.4, softness = 0.02, pattern = null } = {}) {
  const tex = patternTextures();
  const pal = { n: 0, color: [], tile: [], patColor: [], mix: [] };
  if (pattern && pattern.byPalette) {
    for (const e of pattern.byPalette.slice(0, MAXPAL)) {
      pal.color.push(lin(e.color)); pal.tile.push(e.tile ? PATTERN_NAMES.indexOf(e.tile) : -1);
      pal.patColor.push(lin(e.patColor || "#EFE4CC")); pal.mix.push(e.mix ?? 0.4);
    }
    pal.n = pal.color.length;
  }
  while (pal.color.length < MAXPAL) { pal.color.push(new THREE.Color(0, 0, 0)); pal.tile.push(-1); pal.patColor.push(new THREE.Color(0, 0, 0)); pal.mix.push(0); }
  const p = pattern || {};
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      map: { value: map },
      uHasMap: { value: map ? 1 : 0 },
      uColor: { value: new THREE.Color(color) },
      uShade: { value: new THREE.Color(shadeColor) },
      uShadeMix: { value: shadeMix },
      uThreshold: { value: threshold },
      uSoft: { value: softness },
      uLightDir: { value: new THREE.Vector3(-1.5, 3, 2.5).normalize() },
      tPat0: { value: tex[0] }, tPat1: { value: tex[1] }, tPat2: { value: tex[2] }, tPat3: { value: tex[3] },
      uPatAspect: { value: new THREE.Vector4(...PATTERN_NAMES.map((n) => PATTERN_ASPECT[n])) },
      uPatEnabled: ENABLED,
      uPixelRatio: PIXEL_RATIO,
      uPatTile: { value: p.tile ? PATTERN_NAMES.indexOf(p.tile) : -1 },
      uPatSpace: { value: p.space === "world" ? 1 : 0 },
      uPatScale: { value: p.scale ?? (p.space === "world" ? 1.0 : 96) },
      uPatColor: { value: lin(p.color || "#EFE4CC") },
      uPatMix: { value: p.mix ?? 0.4 },
      uPalN: { value: pal.n },
      uPalColor: { value: pal.color }, uPalTile: { value: pal.tile }, uPalPatColor: { value: pal.patColor }, uPalMix: { value: pal.mix },
    },
    vertexShader: /* glsl */ `
      #include <common>
      #include <skinning_pars_vertex>
      varying vec2 vUv;
      varying vec3 vNormalW;
      varying vec3 vWorldPos;
      void main() {
        vUv = uv;
        #include <beginnormal_vertex>
        #include <skinbase_vertex>
        #include <skinnormal_vertex>
        vNormalW = normalize(mat3(modelMatrix) * objectNormal);
        #include <begin_vertex>
        #include <skinning_vertex>
        vWorldPos = (modelMatrix * vec4(transformed, 1.0)).xyz;
        #include <project_vertex>
      }
    `,
    fragmentShader: /* glsl */ `
      uniform sampler2D map;
      uniform int uHasMap;
      uniform vec3 uColor, uShade, uLightDir;
      uniform float uShadeMix, uThreshold, uSoft;
      uniform sampler2D tPat0, tPat1, tPat2, tPat3;
      uniform vec4 uPatAspect;
      uniform int uPatEnabled, uPatTile, uPatSpace, uPalN;
      uniform float uPixelRatio, uPatScale, uPatMix;
      uniform vec3 uPatColor;
      uniform vec3 uPalColor[${MAXPAL}];
      uniform int uPalTile[${MAXPAL}];
      uniform vec3 uPalPatColor[${MAXPAL}];
      uniform float uPalMix[${MAXPAL}];
      varying vec2 vUv;
      varying vec3 vNormalW;
      varying vec3 vWorldPos;

      float tileAt(int t, vec2 uv) {
        if (t == 0) { uv.y /= uPatAspect.x; return texture2D(tPat0, uv).r; }
        if (t == 1) { uv.y /= uPatAspect.y; return texture2D(tPat1, uv).r; }
        if (t == 2) { uv.y /= uPatAspect.z; return texture2D(tPat2, uv).r; }
        uv.y /= uPatAspect.w; return texture2D(tPat3, uv).r;
      }
      // 纹样遮罩：屏幕空间直接按像素铺；世界空间三平面投影，按法线权重混合三个方向
      float patternMask(int t) {
        if (t < 0) return 0.0;
        if (uPatSpace == 0) return tileAt(t, gl_FragCoord.xy / (uPatScale * uPixelRatio));
        vec3 n = abs(normalize(vNormalW)); n = pow(n, vec3(4.0)); n /= (n.x + n.y + n.z);
        vec3 p = vWorldPos / uPatScale;
        return tileAt(t, p.zy) * n.x + tileAt(t, p.xz) * n.y + tileAt(t, p.xy) * n.z;
      }

      void main() {
        vec3 base = uColor;
        if (uHasMap == 1) base *= texture2D(map, vUv).rgb;   // sRGB 贴图由 WebGL2 硬件解成线性
        if (uPatEnabled == 1) {
          if (uPalN > 0) {
            // 按最接近的色板色选纹样。分类用低一级 mip 的模糊采样，否则 Tripo 贴图的噪点会让纹样碎成雪花
            vec3 cls = uHasMap == 1 ? uColor * texture2D(map, vUv, 3.0).rgb : uColor;
            int best = -1; float bd = 1e9;
            for (int i = 0; i < ${MAXPAL}; i++) {
              if (i >= uPalN) break;
              vec3 d = cls - uPalColor[i]; float dd = dot(d, d);
              if (dd < bd) { bd = dd; best = i; }
            }
            for (int i = 0; i < ${MAXPAL}; i++) {
              if (i == best) { float m = patternMask(uPalTile[i]); base = mix(base, uPalPatColor[i], m * uPalMix[i]); }
            }
          } else if (uPatTile >= 0) {
            base = mix(base, uPatColor, patternMask(uPatTile) * uPatMix);
          }
        }
        float ndl = dot(normalize(vNormalW), normalize(uLightDir));
        float lit = smoothstep(uThreshold - uSoft, uThreshold + uSoft, ndl);
        // 阴影层：固有色和阴影色相乘再和固有色混合，保留纹样，只是整体偏紫偏暗
        vec3 shaded = mix(base, base * uShade * 1.6, uShadeMix);
        vec3 c = mix(shaded, base, lit);
        gl_FragColor = vec4(c, 1.0);
      }
    `,
  });
  mat.toonParams = mat.uniforms;
  return mat;
}
