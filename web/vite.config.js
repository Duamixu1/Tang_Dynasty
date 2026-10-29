import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
const assetsDir = path.resolve(root, "../assets");

// 开发期截图接口：页面里 POST /__shot {name, data(dataURL)} → 存到 ../assets/processed/shots/<name>.jpg
// 用来把查看器里的画面存进项目做对比，不用浏览器下载。
import fs from "node:fs";
function shotSaver() {
  return {
    name: "shot-saver",
    configureServer(server) {
      server.middlewares.use("/__shot", (req, res) => {
        if (req.method !== "POST") { res.statusCode = 405; return res.end(); }
        let body = "";
        req.on("data", (c) => (body += c));
        req.on("end", () => {
          try {
            const { name, data } = JSON.parse(body);
            const safe = String(name).replace(/[^\w\u4e00-\u9fff.-]/g, "_");
            const dir = path.resolve(assetsDir, "processed/shots");
            fs.mkdirSync(dir, { recursive: true });
            const file = path.join(dir, safe + ".jpg");
            fs.writeFileSync(file, Buffer.from(data.split(",")[1], "base64"));
            res.setHeader("content-type", "application/json");
            res.end(JSON.stringify({ ok: true, file }));
          } catch (e) { res.statusCode = 500; res.end(String(e)); }
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [shotSaver()],
  define: { ASSETS_DIR: JSON.stringify(assetsDir) },
  server: { port: 5173, fs: { allow: [root, assetsDir] } },
  optimizeDeps: { exclude: ["@sparkjsdev/spark"] },
  build: { rollupOptions: { input: { index: path.resolve(root, "index.html"), character: path.resolve(root, "character.html"), game: path.resolve(root, "game.html") } } },
});
