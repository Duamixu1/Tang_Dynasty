import ATTACH from "../data/attach.json";

// 按挂点名把道具挂到角色身上（兽首笔 → 右手，竹笈 → 背，铜镜 → 左胯）。道具的原点和朝向在 Blender 里已经对好挂点，
// 这里只找挂点、换材质（dress 回调，和角色共用平涂材质），模型里没有挂点就跳过。
export async function attachProps(model, loader, assetUrl, dress) {
  const attached = {};
  for (const [id, d] of Object.entries(ATTACH)) {
    if (id.startsWith("_")) continue;
    const socket = model.getObjectByName(d.socket);
    if (!socket) continue;
    const gltf = await loader.loadAsync(assetUrl(d.url));
    const prop = gltf.scene;
    prop.name = `prop_${id}`;
    prop.traverse((o) => { if (o.isMesh) { o.frustumCulled = false; dress(o); } });
    socket.add(prop);
    attached[id] = prop;
  }
  return attached;
}
