<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import SiteCard from "../../components/SiteCard.vue";
import SiteSelect from "../../components/SiteSelect.vue";
import { usePageHeader } from "../../composables/page_header";
import MonsterIcon from "./MonsterIcon.vue";
import { catalog, catalogError } from "./catalog";
import { targetName } from "./format";
import "./missions.css";

const route = useRoute();
const router = useRouter();
const heading = ref<HTMLElement | null>(null);
const filters = ref<HTMLElement | null>(null);
usePageHeader("任务信息", heading);

function filterParam(key: "category" | "q" | "stars" | "state") {
  return computed<string>({
    get: () => {
      const value = route.query[key];
      return typeof value === "string" ? value : "";
    },
    set: (value) => router.replace({ query: { ...route.query, [key]: value || undefined } }),
  });
}
const category = filterParam("category");
const query = filterParam("q");
const difficulty = filterParam("stars");
const state = filterParam("state");
const ranks = [
  { name: "下位", stars: [1, 2, 3] },
  { name: "上位", stars: [4, 5, 6, 7, 8, 9, 10] },
];
const difficultyOptions = [
  { value: "", label: "全部星级" },
  ...ranks.flatMap(({ name: group, stars }) => [
    { value: group, label: group + "全部", group },
    ...stars.map(n => ({ value: String(n), label: `★ ${n}`, group })),
  ]),
];
const stateOptions = [
  { value: "", label: "全部目标" },
  { value: "NONE", label: "普通个体" },
  { value: "NORMAL", label: "历战个体" },
  { value: "KING", label: "历战王" },
];

const quests = computed(() => catalog.value?.quests ?? []);
const counts = computed(() => {
  const result = new Map<string, number>();
  for (const quest of quests.value) result.set(quest.category, (result.get(quest.category) || 0) + 1);
  return result;
});
const filtered = computed(() => {
  const text = query.value.trim().toLocaleLowerCase();
  const matches = quests.value.filter((quest) =>
    (!category.value || category.value === quest.category) &&
    (!difficulty.value || difficulty.value === quest.rank || difficulty.value === String(quest.stars)) &&
    (!state.value || quest.targets.some((target) => target.id && target.state === state.value)) &&
    (!text || [quest.name, quest.category, quest.type, quest.id, quest.stage, ...quest.targets.map(targetName)]
      .some((part) => part?.toLocaleLowerCase().includes(text))),
  );
  return category.value ? matches : matches.sort((a, b) => b.stars - a.stars);
});

</script>

<template>
  <div class="page missions-page">
    <header ref="heading" class="page-heading mission-list-heading">
      <h1>任务信息</h1>
      <span v-if="catalog" class="count-label">共 {{ catalog.quests.length }} 项任务</span>
    </header>
    <LoadState v-if="!catalog" :error="catalogError" label="正在读取任务数据…" />
    <div v-else class="mission-layout">
      <aside class="mission-nav surface">
        <h2>任务分类</h2>
        <nav aria-label="游戏内任务分类">
          <button v-for="name in ['', ...catalog.categories]" :key="name" class="nav-option" type="button"
            :aria-pressed="category === name" @click="category = name">
            <span>{{ name || "全部任务" }}</span>
            <span class="count">{{ name ? counts.get(name) : catalog.quests.length }}</span>
          </button>
        </nav>
      </aside>
      <section class="mission-board" aria-label="任务列表">
        <div class="mission-toolbar">
          <label class="search-field small">
            <Icon name="search" />
            <input v-model="query" type="search" placeholder="搜索任务、目标或原野" aria-label="搜索任务、目标或原野" autocomplete="off" />
          </label>
          <div ref="filters" class="mission-filters">
            <SiteSelect v-model="difficulty" label="任务位阶与星级" :options="difficultyOptions" :menu-anchor="filters" />
            <SiteSelect v-model="state" label="目标历战状态" :options="stateOptions" :menu-anchor="filters" />
          </div>
        </div>
        <div class="mission-section-heading">
          <h2>{{ category || "全部任务" }}</h2>
          <output aria-live="polite">{{ filtered.length }} 项</output>
          <button v-if="query || state || difficulty" class="text-button filter-reset" type="button" @click="router.replace({ query: { category: category || undefined } })">清除筛选</button>
        </div>
        <ul v-if="filtered.length" class="mission-cards">
          <li v-for="quest in filtered" :key="quest.id">
            <SiteCard class="mission-card"
              :to="{ name: 'mission', params: { questId: quest.id }, query: route.query }"
              :aria-label="`${quest.name}，${quest.stars} 星，${quest.targets.map(targetName).join('、')}`">
              <span class="card-icons" :class="{ multiple: quest.targets.length > 1 }">
                <MonsterIcon v-for="(target, i) in quest.targets.filter((item) => item.id)" :key="i" :target="target" :title="targetName(target)" />
              </span>
              <span class="mission-stars">★ {{ quest.stars }}</span>
              <strong class="card-title" :style="{ '--title-characters': Array.from(quest.name).length }">{{ quest.name }}</strong>
            </SiteCard>
          </li>
        </ul>
        <div v-else class="mission-empty">
          <p>没有符合条件的任务</p>
          <button type="button" class="tonal-button" @click="router.replace({ query: {} })">查看全部任务</button>
        </div>
      </section>
    </div>
  </div>
</template>
