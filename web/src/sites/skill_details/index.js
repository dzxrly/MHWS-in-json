export default {
  id: "skill_details",
  path: "/skill_details/",
  title: "技能效果数值",
  icon: "skill",
  description: "每个技能在各等级下的效果数值与生效条件。",
  routes: [
    { path: ":skillId?", component: () => import("./SkillsPage.vue"), props: true },
    // The former single-file page addressed skills by hash.
    {
      path: "index.html",
      redirect: (to) => ({ path: `/skill_details/${to.hash.slice(1)}`, hash: "" }),
    },
  ],
};
