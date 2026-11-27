import { createSSRApp } from "vue";
import { createMemoryHistory } from "vue-router";
import { renderToString } from "vue/server-renderer";
import App from "./App.vue";
import { SSR_DATA_KEY, type JsonLoader, type SsrDataContext } from "./composables/data";
import { pageHeader } from "./composables/page_header";
import { SEO_CONTEXT_KEY, routeSeoMeta, type SeoContext } from "./composables/seo";
import { createAppRouter } from "./router";
import type { RedirectRule } from "./seo/types";
import { sites } from "./sites";

export { buildAbsoluteUrl, buildHeadTags } from "./composables/seo";

export function collectStaticSite(readJson: <T>(path: string) => T) {
  const router = createAppRouter(createMemoryHistory());
  const paths = new Set(["/"]);
  const redirects: RedirectRule[] = [{ from: "/index.html", to: "/" }];
  for (const site of sites) {
    paths.add(site.path);
    for (const route of site.routes) {
      if (route.path === "index.html") {
        redirects.push({ from: `${site.path}index.html`, to: site.path });
      }
      if (!route.meta?.staticParams) continue;
      if (!route.name) throw new Error(`静态路由缺少名称：${site.path}${route.path}`);
      for (const params of route.meta.staticParams(readJson)) {
        const path: string = router.resolve({ name: route.name, params }).path;
        if (router.resolve(path).name !== route.name || paths.has(path)) {
          throw new Error(`静态路由无效或重复：${path}`);
        }
        paths.add(path);
        if (route.meta.legacyHtml) redirects.push({ from: `${path}.html`, to: path });
      }
    }
  }
  return { paths, redirects };
}

export async function renderRoute(url: string, readJson: JsonLoader) {
  Object.assign(pageHeader, { title: "", condensed: false, tools: false });
  const app = createSSRApp(App);
  const router = createAppRouter(createMemoryHistory());
  const seoContext: SeoContext = {};
  const ssrData: SsrDataContext = { readJson, preloaded: {} };
  const errors: unknown[] = [];
  app.config.errorHandler = (error) => errors.push(error);

  app.provide(SEO_CONTEXT_KEY, seoContext);
  app.provide(SSR_DATA_KEY, ssrData);
  app.use(router);

  await router.push(url);
  await router.isReady();

  const html = await renderToString(app);
  // Vue handles errors from onServerPrefetch and can still return HTML.
  if (errors.length) throw errors[0];
  return {
    html,
    seoMeta: seoContext.readMeta?.() ?? routeSeoMeta(router, router.currentRoute.value),
    preloaded: ssrData.preloaded,
  };
}
