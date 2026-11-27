import { execSync } from "node:child_process";
import { cpSync, createReadStream, existsSync, statSync } from "node:fs";
import { join, resolve, sep } from "node:path";
import { defineConfig, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";

// The site reads only the committed JSON in src/site_data/data (or another
// folder, e.g. a preview, via MHWS_SITE_DATA); the build copies it into data/.
// It never imports src or sdk and runs no Python.
const DATA_DIR = resolve(process.env.MHWS_SITE_DATA || resolve(import.meta.dirname, "../src/site_data/data"));
const siteOrigin = new URL(process.env.SITE_ORIGIN || "https://mhws-info.eggtargaryen.com");
if (siteOrigin.protocol !== "https:" && siteOrigin.protocol !== "http:") {
  throw new Error("SITE_ORIGIN 必须使用 HTTP 或 HTTPS");
}

function siteData(): Plugin {
  let outDir: string;
  let isSsr = false;
  function requireData() {
    if (!existsSync(join(DATA_DIR, "site.json")))
      throw new Error(`缺少网站数据 ${DATA_DIR}：用 MHWS_SITE_DATA 指定数据目录`);
  }
  return {
    name: "site-data",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
      isSsr = Boolean(config.build.ssr);
      if (config.command === "build") requireData();
    },
    configureServer(server) {
      requireData();
      server.middlewares.use("/data", (request, response, next) => {
        const path = resolve(DATA_DIR, "." + decodeURIComponent((request.url ?? "/").split("?")[0]));
        if (!path.startsWith(DATA_DIR + sep) || !path.endsWith(".json") || !existsSync(path) || !statSync(path).isFile()) return next();
        response.setHeader("Content-Type", "application/json; charset=utf-8");
        createReadStream(path).pipe(response);
      });
    },
    closeBundle() {
      if (isSsr) return;
      cpSync(DATA_DIR, join(outDir, "data"), {
        recursive: true,
        filter: (source) => source.endsWith(".json") || statSync(source).isDirectory(),
      });
    },
  };
}

// The footer's deploy date and commit belong to this build, not to the data.
function commit() {
  if (process.env.CF_PAGES_COMMIT_SHA || process.env.GITHUB_SHA)
    return process.env.CF_PAGES_COMMIT_SHA || process.env.GITHUB_SHA;
  try {
    return execSync("git rev-parse HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

export default defineConfig({
  plugins: [vue(), siteData()],
  define: {
    __BUILD__: JSON.stringify({ date: new Date().toISOString().slice(0, 10), commit: commit() }),
    __SITE_ORIGIN__: JSON.stringify(siteOrigin.origin),
  },
  build: {
    // ELK alone is about 1.5 MB and loads only with the flow chart.
    chunkSizeWarningLimit: 2000,
  },
  ssr: {
    noExternal: true,
  },
});
