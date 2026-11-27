import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { SiteInfo, SsrDataContext } from "../src/composables/data";
import type { RedirectRule } from "../src/seo/types";

const WEB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DIST_DIR = resolve(WEB_DIR, "dist");
const SSR_DIR = resolve(WEB_DIR, "../.tmp/web-ssr");
const DATA_DIR = join(DIST_DIR, "data");

const jsonMemoryCache = new Map<string, unknown>();

function readJson<T>(relPath: string): T {
  if (jsonMemoryCache.has(relPath)) {
    return jsonMemoryCache.get(relPath) as T;
  }
  try {
    const parsed = JSON.parse(readFileSync(join(DATA_DIR, relPath), "utf8")) as T;
    jsonMemoryCache.set(relPath, parsed);
    return parsed;
  } catch (cause) {
    throw new Error(`无法读取网站数据：${relPath}`, { cause });
  }
}

function escapeXml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function buildSitemapXml(urls: Set<string>) {
  const entries = [...urls]
    .map((url) => `  <url><loc>${escapeXml(url)}</loc></url>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</urlset>\n`;
}

function buildRobotsTxt(sitemapUrl: string, preview: boolean) {
  if (preview) {
    return "User-agent: *\nDisallow: /\n";
  }
  return `User-agent: *\nAllow: /\nDisallow: /data/\n\nSitemap: ${sitemapUrl}\n`;
}

function buildRedirects(redirects: RedirectRule[]) {
  return (
    redirects
      .map((rule) => `${rule.from} ${rule.to} 301`)
      .join("\n") + "\n"
  );
}

function buildHeaders(preview: boolean) {
  const blocks = [
    "/assets/*\n  Cache-Control: public, max-age=31536000, immutable",
    "/data/*\n  Cache-Control: public, no-cache",
  ];
  if (preview) {
    blocks.unshift("/*\n  X-Robots-Tag: noindex, nofollow");
  }
  return blocks.join("\n\n") + "\n";
}

function stripTemplateSeoTags(template: string) {
  return template
    .replace(/<meta\s+name="description"[^>]*>\s*/i, "")
    .replace(/<meta\s+property="og:type"[^>]*>\s*/i, "")
    .replace(/<meta\s+property="og:site_name"[^>]*>\s*/i, "")
    .replace(/<meta\s+property="og:locale"[^>]*>\s*/i, "")
    .replace(/<meta\s+name="twitter:card"[^>]*>\s*/i, "")
    .replace(/<title>[\s\S]*?<\/title>\s*/i, "");
}

function outputFileForPath(routePath: string) {
  if (routePath === "/") return join(DIST_DIR, "index.html");
  const clean = routePath.replace(/^\/+/, "");
  if (clean.endsWith("/")) {
    return join(DIST_DIR, clean, "index.html");
  }
  return join(DIST_DIR, `${clean}.html`);
}

function renderDocument(template: string, headTags: string, appHtml: string, preloaded: SsrDataContext["preloaded"]) {
  const preloadKeys = Object.keys(preloaded);
  const preloadScript = preloadKeys.length
    ? `<script>window.__PRELOADED_DATA__=${JSON.stringify(preloaded).replace(/</g, "\\u003c")}</script>`
    : "";
  return template
    .replace("</head>", () => `    ${headTags}\n  </head>`)
    .replace(
      '<div id="app"></div>',
      () => `${preloadScript}<div id="app" data-ssr="1">${appHtml}</div>`,
    );
}

async function main() {
  const start = Date.now();
  try {
    writeFileSync(join(SSR_DIR, "package.json"), '{"type":"module"}\n', "utf8");
    const mod: typeof import("../src/entry-server") = await import(pathToFileURL(join(SSR_DIR, "entry-server.js")).href);
    const { paths, redirects } = mod.collectStaticSite(readJson);
    const template = stripTemplateSeoTags(readFileSync(join(DIST_DIR, "index.html"), "utf8"));
    const preview = process.env.MHWS_SITE_PREVIEW === "1" || readJson<SiteInfo>("site.json").preview === true;
    const urls = new Set<string>();

    for (const path of paths) {
      const rendered = await mod.renderRoute(path, readJson);
      if (!preview && rendered.seoMeta.indexable !== false) {
        urls.add(mod.buildAbsoluteUrl(rendered.seoMeta.canonicalPath));
      }
      const headTags = mod.buildHeadTags(rendered.seoMeta);
      const outPath = outputFileForPath(path);
      mkdirSync(dirname(outPath), { recursive: true });
      writeFileSync(outPath, renderDocument(template, headTags, rendered.html, rendered.preloaded), "utf8");
    }

    const notFound = await mod.renderRoute("/404", readJson);
    const notFoundHead = mod.buildHeadTags(notFound.seoMeta);
    writeFileSync(
      join(DIST_DIR, "404.html"),
      renderDocument(template, notFoundHead, notFound.html, notFound.preloaded),
      "utf8",
    );

    writeFileSync(join(DIST_DIR, "robots.txt"), buildRobotsTxt(mod.buildAbsoluteUrl("/sitemap.xml"), preview), "utf8");
    writeFileSync(join(DIST_DIR, "sitemap.xml"), buildSitemapXml(urls), "utf8");
    writeFileSync(join(DIST_DIR, "_redirects"), buildRedirects(redirects), "utf8");
    writeFileSync(join(DIST_DIR, "_headers"), buildHeaders(preview), "utf8");

    const elapsedSec = ((Date.now() - start) / 1000).toFixed(2);
    console.log(
      `[prerender] Rendered ${paths.size} routes + 404.html in ${elapsedSec}s (${urls.size} indexable in sitemap.xml, ${redirects.length} redirects${preview ? ", preview noindex" : ""}).`,
    );
  } finally {
    rmSync(SSR_DIR, { recursive: true, force: true });
  }
}

await main();
