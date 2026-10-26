import { cpSync, createReadStream, existsSync, statSync } from "node:fs";
import { join, resolve, sep } from "node:path";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// The site reads only the JSON that `python -m src.site_data` writes into
// src/site_data/data (or the website/ folder of a PROCESSED_DATA release); the
// build copies it into data/. It never imports src or sdk.
const DATA_DIR = resolve(process.env.MHWS_SITE_DATA || resolve(import.meta.dirname, "../src/site_data/data"));

function siteData() {
  let outDir;
  function requireData() {
    if (!existsSync(join(DATA_DIR, "site.json")))
      throw new Error(`缺少网站数据 ${DATA_DIR}：先运行 python -m src.site_data，或用 MHWS_SITE_DATA 指定数据目录`);
  }
  return {
    name: "site-data",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
      if (config.command === "build") requireData();
    },
    configureServer(server) {
      requireData();
      server.middlewares.use("/data", (request, response, next) => {
        const path = resolve(DATA_DIR, "." + decodeURIComponent(request.url.split("?")[0]));
        if (!path.startsWith(DATA_DIR + sep) || !existsSync(path) || !statSync(path).isFile()) return next();
        response.setHeader("Content-Type", "application/json; charset=utf-8");
        createReadStream(path).pipe(response);
      });
    },
    closeBundle() {
      cpSync(DATA_DIR, join(outDir, "data"), { recursive: true });
    },
  };
}

export default defineConfig({
  plugins: [vue(), siteData()],
  build: {
    // ELK alone is about 1.5 MB and loads only with the flow chart.
    chunkSizeWarningLimit: 2000,
  },
});
