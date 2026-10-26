const ENEMY_ID = "EM\\d{4}_\\d{2}_\\d+";

export default {
  id: "enemy_battle_logic",
  path: "/enemy_battle_logic/",
  title: "怪物行动逻辑",
  icon: "tree",
  description: "每只怪物的出招决策树，可按距离、角度和状态筛选。",
  routes: [
    { path: "", component: () => import("./MonsterIndexPage.vue") },
    // Pages of the former single-file site.
    { path: "index.html", redirect: "/enemy_battle_logic/" },
    {
      path: `:file(${ENEMY_ID}\\.html)`,
      redirect: (to) => `/enemy_battle_logic/${to.params.file.replace(/\.html$/, "")}`,
    },
    {
      path: `:enemyId(${ENEMY_ID})`,
      component: () => import("./MonsterPage.vue"),
      props: true,
      meta: { workspace: true },
    },
  ],
};
