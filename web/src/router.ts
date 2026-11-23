import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import HubPage from "./pages/HubPage.vue";
import { sites } from "./sites";

export const SITE_TITLE = "MHWS 数据站";

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
    meta: { title: "页面不存在" },
  },
];

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior: (to, from, saved) =>
    saved || (to.path === from.path ? false : { top: 0 }),
});

router.afterEach((to, _from, failure) => {
  if (failure) return;
  const title = to.meta.title || to.meta.site?.title;
  document.title = title ? `${title} · ${SITE_TITLE}` : SITE_TITLE;
});
