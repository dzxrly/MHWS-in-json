import { createMemoryHistory, createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from "vue-router";
import { applySeoMeta, routeSeoMeta } from "./composables/seo";
import HubPage from "./pages/HubPage.vue";
import { sites } from "./sites";

const routes: RouteRecordRaw[] = [
  { path: "/", component: HubPage },
  { path: "/index.html", redirect: "/" },
  ...sites.flatMap((site) =>
    site.routes.map((route) => ({
      ...route,
      path: site.path + route.path,
      meta: { ...route.meta, site },
    })),
  ),
  {
    path: "/:pathMatch(.*)*",
    component: () => import("./pages/NotFoundPage.vue"),
    meta: { title: "页面不存在", indexable: false },
  },
];

export function createAppRouter(history?: RouterHistory) {
  const instance = createRouter({
    history: history ?? (typeof window !== "undefined" ? createWebHistory(import.meta.env.BASE_URL) : createMemoryHistory()),
    routes,
    scrollBehavior: (to, from, saved) =>
      saved || (to.path === from.path ? false : { top: 0 }),
  });

  instance.afterEach((to, from, failure) => {
    if (failure || typeof document === "undefined" || to.path === from.path) return;
    if (!from.matched.length && document.querySelector('#app[data-ssr="1"]')) return;
    applySeoMeta(routeSeoMeta(instance, to));
  });

  return instance;
}

export const router = createAppRouter();
