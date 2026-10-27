<script setup>
import { computed, nextTick, ref, shallowRef, watch } from "vue";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import { loadJson } from "../../composables/data.js";
import { usePageHeader } from "../../composables/page_header.js";
import { SITE_TITLE } from "../../router.js";
import SkillEffect from "./SkillEffect.vue";

const props = defineProps({ skillId: { type: String, default: "" } });

const data = shallowRef(null);
const error = ref(null);
const query = ref("");
const category = ref("");
const showEmpty = ref(false);
const list = ref();
const detail = ref();
const heading = ref();
usePageHeader("技能效果数值", heading);

loadJson("skill_details/skills.json").then((loaded) => {
  // Everything a search can match: names, descriptions, effects, weapons and situations.
  for (const skill of loaded.skills) {
    skill.search = [
      skill.name, skill.ja, skill.id, skill.explain, skill.category,
      ...skill.levels.map((l) => l.explain),
      ...skill.effects.flatMap((e) => [e.name, e.code, ...Object.values(e.meaning), ...e.rows.flatMap((r) => [r.applies, r.situation])]),
    ].join("\n").toLocaleLowerCase();
  }
  data.value = loaded;
  if (!current.value.effects.length) showEmpty.value = true;
}, (failure) => (error.value = failure));

const byId = computed(() => new Map((data.value?.skills ?? []).map((s) => [s.id, s])));
const current = computed(() => {
  const skills = data.value.skills;
  return byId.value.get(props.skillId) || skills.find((s) => s.effects.length) || skills[0];
});
const withEffects = computed(() => data.value.skills.filter((s) => s.effects.length).length);
const groups = computed(() => {
  const text = query.value.trim().toLocaleLowerCase();
  return data.value.categories
    .map((name) => ({
      name,
      skills: data.value.skills.filter(
        (s) => s.category === name && (showEmpty.value || s.effects.length) && (!category.value || s.category === category.value) && (!text || s.search.includes(text)),
      ),
    }))
    .filter((group) => group.skills.length);
});
const shown = computed(() => groups.value.reduce((n, group) => n + group.skills.length, 0));
const total = computed(() => data.value.skills.filter((s) => showEmpty.value || s.effects.length).length);

watch(
  () => data.value && current.value,
  async (skill, previous) => {
    if (!skill) return;
    document.title = `${skill.name} · 技能效果数值 · ${SITE_TITLE}`;
    await nextTick();
    // Keep the chosen skill in view in the list; on narrow screens the list
    // sits above the detail, so move to the detail instead.
    const link = list.value?.querySelector('[aria-current="page"]');
    if (link) {
      const box = list.value;
      if (link.offsetTop < box.scrollTop + 30 || link.offsetTop + link.offsetHeight > box.scrollTop + box.clientHeight)
        box.scrollTop = link.offsetTop - box.clientHeight / 2;
    }
    if (previous && matchMedia("(max-width: 899px)").matches) detail.value?.scrollIntoView({ behavior: "smooth" });
  },
  { immediate: true },
);
</script>

<template>
  <div class="page skills-page">
    <div ref="heading" class="page-heading">
      <div>
        <h1>技能效果数值</h1>
      </div>
      <span v-if="data" class="count-label">{{ data.skills.length }} 个技能 · {{ withEffects }} 个有数值</span>
    </div>
    <LoadState v-if="!data" :error="error" />
    <div v-else class="skills-layout">
      <aside class="skill-nav surface">
        <div class="filters">
          <label class="search-field small">
            <Icon name="search" />
            <input v-model="query" type="search" placeholder="搜索技能、效果或武器" aria-label="搜索技能、效果或武器" autocomplete="off" />
          </label>
          <div class="chips" role="group" aria-label="技能类别">
            <button
              v-for="name in ['', ...data.categories]"
              :key="name"
              class="chip small"
              type="button"
              :aria-pressed="category === name"
              @click="category = name"
            >
              {{ name || "全部" }}
            </button>
          </div>
          <label class="switch"><input v-model="showEmpty" type="checkbox" />显示未提取到数值的技能</label>
          <output class="count-label" aria-live="polite">{{ shown === total ? `共 ${total} 个技能` : `${shown} / ${total} 个技能` }}</output>
        </div>
        <nav ref="list" class="skill-list" aria-label="技能列表">
          <section v-for="group in groups" :key="group.name">
            <h2>{{ group.name }} · {{ group.skills.length }}</h2>
            <RouterLink
              v-for="skill in group.skills"
              :key="skill.id"
              :to="`/skill_details/${skill.id}`"
              :class="{ empty: !skill.effects.length }"
              :aria-current="skill === current ? 'page' : undefined"
            >
              <span class="name">{{ skill.name }}</span>
              <span class="n">{{ skill.effects.length ? `${skill.effects.length} 项` : "无数值" }}</span>
            </RouterLink>
          </section>
          <p v-if="!shown" class="empty-state">没有匹配的技能。</p>
        </nav>
      </aside>
      <div ref="detail" class="skill-detail">
        <header class="skill-head surface">
          <p class="kicker mono">{{ current.category }} · {{ current.id }}</p>
          <h2>{{ current.name }}<span v-if="current.ja" class="ja">{{ current.ja }}</span></h2>
          <p v-if="current.explain" class="explain">{{ current.explain }}</p>
          <p v-if="current.mappedSkill" class="aside-note">
            对应技能：<RouterLink class="mapped-skill" :to="`/skill_details/${current.mappedSkill.id}`">{{ current.mappedSkill.name }}（{{ current.mappedSkill.id }}）</RouterLink>。等级与效果见对应技能。
          </p>
          <p v-for="reference in current.resourceOpenSkills || []" :key="`${reference.id}-${reference.level}`" class="aside-note">
            资源中的打开技能指向：{{ reference.name }}（{{ reference.id }}）Lv.{{ reference.level }} 指向此编号；当前代码未确认此编号的对应技能。
          </p>
          <p v-if="current.openSkills" class="aside-note">打开技能：{{ current.openSkills }}</p>
          <p v-for="note in current.notes" :key="note" class="aside-note">{{ note }}</p>
          <ul v-if="current.levels.some((l) => l.explain)" class="levels">
            <li v-for="level in current.levels" :key="level.level">
              <b>Lv.{{ level.level }}</b><span>{{ level.explain }}</span>
            </li>
          </ul>
        </header>
        <div v-if="current.effects.length" class="effects">
          <SkillEffect v-for="effect in current.effects" :key="effect.key" :effect="effect" :levels="current.levelColumns" />
        </div>
        <p v-else-if="current.mappedSkill" class="no-values">此编号的等级与效果见上方对应技能。</p>
        <p v-else class="no-values">未提取到数值：当前离线结果未提供该技能的效果数值。</p>
        <details class="reading surface">
          <summary><Icon name="info" />阅读说明</summary>
          <ul>
            <li v-for="note in data.notes" :key="note">{{ note }}</li>
          </ul>
          <h3>数据说明</h3>
          <ul>
            <li v-for="note in data.generalNotes" :key="note">{{ note }}</li>
          </ul>
        </details>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skills-page {
  max-width: 1360px;
}
.skills-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.skill-nav {
  position: sticky;
  top: calc(var(--header-height) + 16px);
  height: calc(100dvh - var(--header-height) - 32px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.filters {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 18px 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--outline-variant) 60%, transparent);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.skill-list {
  position: relative;
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 20px;
}
/* Each category header covers the list's side padding and stays opaque
   while its own items scroll under it. */
.skill-list h2 {
  position: sticky;
  top: 0;
  z-index: 1;
  margin: 0 -10px;
  padding: 12px 22px 6px;
  background: var(--surface);
  color: var(--primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
}
.skill-list a {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 44px;
  padding: 8px 16px;
  border-radius: 999px;
  transition: background 0.18s var(--motion);
}
.skill-list a:hover {
  background: var(--surface-high);
}
.skill-list a[aria-current="page"] {
  background: var(--secondary-container);
  color: var(--on-secondary-container);
  font-weight: 600;
}
.skill-list .n {
  color: var(--on-surface-variant);
  font-size: 12px;
  font-weight: 400;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.skill-list a.empty .name {
  color: var(--on-surface-variant);
}
.skill-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  scroll-margin-top: calc(var(--header-height) + 16px);
}
.skill-head {
  padding: 28px 30px 24px;
}
.kicker {
  color: var(--on-surface-variant);
  font-size: 12px;
}
.skill-head h2 {
  margin-top: 4px;
  font-size: 30px;
  font-weight: 750;
  letter-spacing: -0.8px;
  line-height: 1.35;
}
.skill-head .ja {
  margin-left: 12px;
  color: var(--on-surface-variant);
  font-size: 15px;
  font-weight: 400;
  letter-spacing: 0;
}
.explain {
  margin-top: 10px;
  font-size: 15px;
  line-height: 1.8;
}
.aside-note {
  margin-top: 6px;
  color: var(--on-surface-variant);
  font-size: 13px;
}
.mapped-skill {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.levels {
  margin: 16px 0 0;
  padding: 14px 18px;
  list-style: none;
  display: grid;
  gap: 6px;
  border-radius: 20px;
  background: color-mix(in srgb, var(--surface-high) 55%, transparent);
}
.levels li {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 8px;
  color: var(--on-surface-variant);
  font-size: 13.5px;
  line-height: 1.7;
}
.levels b {
  color: var(--primary);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.effects {
  display: grid;
  gap: 16px;
}
.no-values {
  padding: 18px 22px;
  border: 1px dashed var(--outline-variant);
  border-radius: 24px;
  color: var(--on-surface-variant);
}
.reading {
  padding: 18px 24px;
  font-size: 13.5px;
}
.reading summary {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.reading summary .icon {
  width: 18px;
  height: 18px;
  color: var(--primary);
}
.reading ul {
  margin: 10px 0 0;
  padding-left: 20px;
  color: var(--on-surface-variant);
  line-height: 1.8;
}
.reading h3 {
  margin-top: 14px;
  font-size: 14px;
}
@media (max-width: 899px) {
  .skills-layout {
    grid-template-columns: 1fr;
  }
  .skill-nav {
    position: static;
    height: auto;
  }
  .skill-list {
    max-height: 44vh;
  }
  .skill-head {
    padding: 22px;
  }
  .skill-head h2 {
    font-size: 24px;
  }
}
</style>
