import type { SiteDefinition } from "../../site_types";

export default {
  id: "weapon_actions",
  path: "/weapon_actions/",
  title: "武器动作值",
  icon: "sword",
  description: "按武器查招式的动作值、眩晕值和各项命中倍率。",
  routes: [{ path: "", component: () => import("./WeaponActionsPage.vue") }],
} satisfies SiteDefinition;
