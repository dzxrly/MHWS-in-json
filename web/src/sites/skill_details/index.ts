import type { RouteLocation, RouteLocationRaw } from "vue-router";
import type { SiteDefinition } from "../../site_types";
import type { Skill } from "./types";

export function legacySkillLocation(to: Pick<RouteLocation, "name" | "params" | "hash" | "query">): RouteLocationRaw | undefined {
  if (to.name !== "legacy_skill_details" && (to.name !== "skill_details" || to.params.skillId)) return;
  const skillId = /^#(HunterSkill_\d+)$/.exec(to.hash)?.[1];
  if (skillId) return { name: "skill_details", params: { skillId }, query: to.query, hash: "" };
}

export default {
  id: "skill_details",
  path: "/skill_details/",
  title: "技能效果数值",
  icon: "skill",
  description: "每个技能在各等级下的效果数值与生效条件。",
  routes: [
    {
      path: ":skillId?",
      name: "skill_details",
      component: () => import("./SkillsPage.vue"),
      props: true,
      meta: {
        staticParams: (readJson) => readJson<{ skills: Skill[] }>("skill_details/skills.json").skills.map(
          ({ id }) => ({ skillId: id }),
        ),
      },
    },
    // The former single-file page addressed skills by hash.
    {
      path: "index.html",
      name: "legacy_skill_details",
      redirect: (to) => legacySkillLocation(to) ?? { name: "skill_details", hash: "" },
    },
  ],
} satisfies SiteDefinition;
