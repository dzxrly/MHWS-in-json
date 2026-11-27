<script setup lang="ts">
import { computed, nextTick, onMounted, onServerPrefetch, ref, shallowRef, watch } from "vue";
import { useRouter } from "vue-router";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import { getCachedJson, getPreloadedSlice, loadJson, setPreloadedSlice, useSsrDataContext } from "../../composables/data";
import { formatDecimalText } from "../../composables/numbers";
import { usePageHeader } from "../../composables/page_header";
import { useSeoMeta } from "../../composables/seo";
import { SITE_TITLE } from "../../seo/config";
import SkillEffect from "./SkillEffect.vue";
import type { Skill } from "./types";

interface SkillListItem {
  id: string;
  name: string;
  ja: string;
  category: string;
  effectCount: number;
  search: string;
}

interface SkillsState {
  categories: string[];
  items: SkillListItem[];
  fullById: Map<string, Skill> | null;
  preloadCurrent: Skill | null;
}

interface SkillsPreload {
  categories: string[];
  items: Omit<SkillListItem, "search">[];
  current: Skill | null;
}

const props = defineProps({ skillId: { type: String, default: "" } });
const router = useRouter();
const ssr = useSsrDataContext();

function toFullState(loaded: { categories: string[]; skills: Skill[] }): SkillsState {
  const items: SkillListItem[] = loaded.skills.map((skill) => ({
    id: skill.id,
    name: skill.name,
    ja: skill.ja,
    category: skill.category,
    effectCount: skill.effects.length,
    search: [
      skill.name,
      skill.ja,
      skill.id,
      skill.explain,
      skill.category,
      ...skill.levels.map((l) => l.explain),
      ...skill.effects.flatMap((e) => [
        e.name,
        e.code,
        ...Object.values(e.meaning),
        ...e.rows.flatMap((r) => [r.applies, r.situation]),
      ]),
    ]
      .join("\n")
      .toLocaleLowerCase(),
  }));
  return {
    categories: loaded.categories,
    items,
    fullById: new Map(loaded.skills.map((s) => [s.id, s])),
    preloadCurrent: null,
  };
}

function toPreload(loaded: { categories: string[]; skills: Skill[] }, skillId: string): SkillsPreload {
  const found = skillId
    ? loaded.skills.find((s) => s.id === skillId) ?? null
    : loaded.skills.find((s) => s.effects.length) ?? loaded.skills[0] ?? null;
  return {
    categories: loaded.categories,
    items: loaded.skills.map((s) => ({
      id: s.id,
      name: s.name,
      ja: s.ja,
      category: s.category,
      effectCount: s.effects.length,
    })),
    current: found,
  };
}

function fromPreload(preload: SkillsPreload): SkillsState {
  return {
    categories: preload.categories,
    items: preload.items.map((item) => ({
      ...item,
      search: `${item.name}\n${item.ja}\n${item.id}\n${item.category}`.toLocaleLowerCase(),
    })),
    fullById: null,
    preloadCurrent: preload.current,
  };
}

const preloadKey = computed(() => `skills:page:${props.skillId}`);
function initialSkillsState(): SkillsState | null {
  const full = getCachedJson<{ categories: string[]; skills: Skill[] }>("skill_details/skills.json");
  if (full) return toFullState(full);
  const preloaded = getPreloadedSlice<SkillsPreload>(preloadKey.value, ssr);
  if (preloaded) return fromPreload(preloaded);
  return null;
}

const data = shallowRef<SkillsState | null>(initialSkillsState());
const error = ref<Error | null>(null);
const query = ref("");
const category = ref("");
const initialTarget = data.value
  ? data.value.fullById
    ? (props.skillId ? data.value.fullById.get(props.skillId) : [...data.value.fullById.values()].find((s) => s.effects.length) ?? [...data.value.fullById.values()][0])
    : data.value.preloadCurrent
  : null;
const showEmpty = ref(Boolean(initialTarget && !initialTarget.effects.length));
const list = ref<HTMLElement | null>(null);
const detail = ref<HTMLElement | null>(null);
const heading = ref<HTMLElement | null>(null);
usePageHeader("技能效果数值", heading);

onServerPrefetch(async () => {
  const loaded = await loadJson<{ categories: string[]; skills: Skill[] }>("skill_details/skills.json", ssr);
  const preload = toPreload(loaded, props.skillId);
  setPreloadedSlice(preloadKey.value, preload, ssr);
  data.value = fromPreload(preload);
  if (preload.current && !preload.current.effects.length) {
    showEmpty.value = true;
  }
});

onMounted(() => {
  if (!getCachedJson("skill_details/skills.json")) {
    loadJson<{ categories: string[]; skills: Skill[] }>("skill_details/skills.json").then(
      (loaded) => {
        data.value = toFullState(loaded);
        if (current.value && !current.value.effects.length) showEmpty.value = true;
      },
      (failure) => {
        if (!data.value) error.value = failure;
      },
    );
  }
});

const current = computed<Skill | null>(() => {
  if (!data.value) return null;
  if (data.value.fullById) {
    if (props.skillId) return data.value.fullById.get(props.skillId) ?? null;
    for (const skill of data.value.fullById.values()) {
      if (skill.effects.length) return skill;
    }
    return data.value.fullById.values().next().value ?? null;
  }
  return data.value.preloadCurrent;
});
const missingSkill = computed(() => Boolean(data.value && props.skillId && !current.value));
const withEffects = computed(() => data.value?.items.filter((s) => s.effectCount > 0).length ?? 0);

useSeoMeta(() => {
  const skill = current.value;
  if (!props.skillId) {
    return {
      ...data.value && {
        description: `查询怪物猎人：荒野 ${data.value.items.length} 个技能的等级效果、触发条件与适用武器（已提取 ${withEffects.value} 个技能的详细数值）。`,
      },
      ...skill && { canonicalPath: router.resolve({ name: "skill_details", params: { skillId: skill.id } }).path },
      indexable: false,
    };
  }
  if (!data.value) return {};
  if (!skill) {
    return {
      title: `未找到技能 · 技能效果数值 · ${SITE_TITLE}`,
      description: `技能列表中没有编号为 ${props.skillId} 的技能。`,
      indexable: false,
    };
  }
  const hasEffects = skill.effects.length > 0;
  const maxLevel = skill.levelColumns.length ? Math.max(...skill.levelColumns) : skill.levels.length;
  const effectNames = skill.effects.map((e) => e.name).slice(0, 4).join("、");
  const titleName = skill.ja ? `${skill.name}（${skill.ja}）` : skill.name;
  const description = hasEffects
    ? `怪物猎人：荒野技能「${skill.name}」（${skill.category}，最高 Lv.${maxLevel}）：${skill.explain} 包含效果：${effectNames}。`
    : `怪物猎人：荒野技能「${skill.name}」（${skill.category}）：${skill.explain || "暂未提取到独立效果数值"}。`;
  return {
    title: `${titleName}技能效果数值 · ${SITE_TITLE}`,
    description,
    indexable: hasEffects,
    ogType: "article",
    breadcrumbName: skill.name,
  };
});

const groups = computed(() => {
  const text = query.value.trim().toLocaleLowerCase();
  const { categories, items } = data.value ?? { categories: [], items: [] };
  return categories
    .map((name) => ({
      name,
      skills: items.filter(
        (s) => s.category === name && (showEmpty.value || s.effectCount > 0) && (!category.value || s.category === category.value) && (!text || s.search.includes(text)),
      ),
    }))
    .filter((group) => group.skills.length);
});
const shown = computed(() => groups.value.reduce((n, group) => n + group.skills.length, 0));
const total = computed(() => data.value?.items.filter((s) => showEmpty.value || s.effectCount > 0).length ?? 0);

watch(
  () => data.value && current.value,
  async (skill, previous) => {
    if (!skill || typeof window === "undefined") return;
    await nextTick();
    // Keep the chosen skill in view in the list; on narrow screens the list
    // sits above the detail, so move to the detail instead.
    const box = list.value;
    const link = box?.querySelector<HTMLElement>('[aria-current="page"]');
    if (box && link) {
      if (link.offsetTop < box.scrollTop + 30 || link.offsetTop + link.offsetHeight > box.scrollTop + box.clientHeight)
        box.scrollTop = link.offsetTop - box.clientHeight / 2;
    }
    if (previous && matchMedia("(max-width: 899px)").matches) {
      const behavior = matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
      detail.value?.scrollIntoView({ behavior });
    }
  },
  { immediate: true },
);
</script>

<template>
  <div class="page skills-page">
    <div ref="heading" class="page-heading">
      <div>
        <p class="page-title">技能效果数值</p>
      </div>
      <span v-if="data" class="count-label">{{ data.items.length }} 个技能 · {{ withEffects }} 个有数值</span>
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
              :to="{ name: 'skill_details', params: { skillId: skill.id } }"
              class="nav-option"
              :class="{ empty: !skill.effectCount }"
              :aria-current="skill.id === current?.id ? 'page' : undefined"
            >
              <span class="name">{{ skill.name }}</span>
              <span class="n">{{ skill.effectCount ? `${skill.effectCount} 项` : "无数值" }}</span>
            </RouterLink>
          </section>
          <p v-if="!shown" class="empty-state">没有匹配的技能。</p>
        </nav>
      </aside>
      <div v-if="current" ref="detail" class="skill-detail">
        <header class="skill-head surface">
          <p class="kicker mono">{{ current.category }} · {{ current.id }}</p>
          <h1>{{ current.name }}<span v-if="current.ja" class="ja">{{ current.ja }}</span></h1>
          <p v-if="current.explain" class="explain">{{ formatDecimalText(current.explain) }}</p>
          <p v-if="current.mappedSkill" class="aside-note">
            对应技能：<RouterLink class="mapped-skill" :to="{ name: 'skill_details', params: { skillId: current.mappedSkill.id } }">{{ current.mappedSkill.name }}（{{ current.mappedSkill.id }}）</RouterLink>。等级与效果见对应技能。
          </p>
          <p v-for="reference in current.resourceOpenSkills || []" :key="`${reference.id}-${reference.level}`" class="aside-note">
            资源中的打开技能指向：{{ reference.name }}（{{ reference.id }}）Lv.{{ reference.level }} 指向此编号；当前代码未确认此编号的对应技能。
          </p>
          <p v-if="current.openSkills" class="aside-note">打开技能：{{ current.openSkills }}</p>
          <p v-for="note in current.notes" :key="note" class="aside-note">{{ note }}</p>
          <ul v-if="current.levels.some((l) => l.explain)" class="levels">
            <li v-for="level in current.levels" :key="level.level">
              <b>Lv.{{ level.level }}</b><span>{{ formatDecimalText(level.explain) }}</span>
            </li>
          </ul>
        </header>
        <div v-if="current.effects.length" class="effects">
          <SkillEffect v-for="effect in current.effects" :key="effect.key" :effect="effect" :levels="current.levelColumns" />
        </div>
        <p v-else-if="current.mappedSkill" class="no-values">此编号的等级与效果见上方对应技能。</p>
        <p v-else class="no-values">未提取到数值：当前离线结果未提供该技能的效果数值。</p>
      </div>
      <div v-else-if="missingSkill" class="skill-detail">
        <div class="surface skill-head">
          <h1>未找到技能</h1>
          <p class="explain">技能目录中没有编号为 {{ props.skillId }} 的技能。</p>
        </div>
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
  border-bottom: 1px solid var(--divider);
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
  gap: 8px;
}
.skill-list .n {
  color: var(--on-surface-variant);
  font-size: 12px;
  font-weight: 400;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.skill-list a.empty:not([aria-current="page"]) .name {
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
.skill-head h1,
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
  border-radius: var(--shape-l-plus);
  background: var(--surface-high);
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
  border-radius: var(--radius);
  color: var(--on-surface-variant);
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
  .skill-head h1,
  .skill-head h2 {
    font-size: 24px;
  }
}
</style>
