import type { RouteRecordRaw } from "vue-router";

export interface SiteDefinition {
  id: string;
  path: string;
  title: string;
  icon: string;
  description: string;
  routes: RouteRecordRaw[];
}

declare module "vue-router" {
  interface RouteMeta {
    site?: SiteDefinition;
    title?: string;
    workspace?: boolean;
    backwards?: boolean;
  }
}
