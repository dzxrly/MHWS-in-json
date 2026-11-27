import type { SiteDefinition } from "../../site_types";
import type { MissionListCatalog } from "./catalog";

export default {
  id: "missions",
  path: "/missions/",
  title: "任务信息",
  icon: "target",
  description: "按游戏分类查找任务，查看目标血量、动作速度、多人修正和报酬。",
  routes: [
    {
      path: "",
      name: "missions",
      component: () => import("./MissionsPage.vue"),
      beforeEnter: (to) => {
        const { quest, ...query } = to.query;
        if (typeof quest === "string" && quest) {
          return { name: "mission", params: { questId: quest }, query, replace: true };
        }
      },
    },
    {
      path: ":questId",
      name: "mission",
      component: () => import("./MissionPage.vue"),
      props: true,
      meta: {
        staticParams: (readJson) => readJson<MissionListCatalog>("missions/index.json").quests.map(
          ({ id }) => ({ questId: id }),
        ),
      },
    },
  ],
} satisfies SiteDefinition;
