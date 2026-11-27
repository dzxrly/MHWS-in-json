<script setup lang="ts">
import { computed, onMounted, onServerPrefetch, ref, shallowRef } from "vue";
import { useRouter } from "vue-router";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import { getCachedJson, getPreloadedSlice, loadJson, setPreloadedSlice, useSsrDataContext } from "../../composables/data";
import { formatNumber } from "../../composables/numbers";
import { usePageHeader } from "../../composables/page_header";
import { useSeoMeta } from "../../composables/seo";
import { SITE_TITLE } from "../../seo/config";

interface Hit {
  request: number;
  condition: string | null;
  attack: number;
  fixedElement: { name: string; value: number } | null;
  fixed: number;
  stun: number | null;
  breakRate: number | null;
  elementRate: number | null;
  statusRate: number | null;
}
interface WeaponSheet {
  id: string;
  name: string;
  groups: { name: string; internal: string | null; rows: Hit[] }[];
}
interface WeaponTab {
  id: string;
  name: string;
}
interface WeaponPreload {
  tabs: WeaponTab[];
  sheet: WeaponSheet | null;
}

const props = withDefaults(defineProps<{ weaponId?: string }>(), { weaponId: "" });
const router = useRouter();
const ssr = useSsrDataContext();
const preloadKey = computed(() => `weapons:page:${props.weaponId}`);

const fullSheets = shallowRef<WeaponSheet[] | null>(
  getCachedJson<WeaponSheet[]>("weapon_actions/actions.json") ?? null,
);
const preloaded = shallowRef<WeaponPreload | null>(
  fullSheets.value ? null : getPreloadedSlice<WeaponPreload>(preloadKey.value, ssr) ?? null,
);
const error = shallowRef<Error | null>(null);
const query = ref("");
const heading = ref<HTMLElement | null>(null);

const tabs = computed<WeaponTab[]>(() =>
  fullSheets.value
    ? fullSheets.value.map((s) => ({ id: s.id, name: s.name }))
    : preloaded.value?.tabs ?? [],
);
const targetId = computed(() => props.weaponId || tabs.value[0]?.id);
const sheet = computed<WeaponSheet | null>(() => {
  if (fullSheets.value) {
    return fullSheets.value.find((item) => item.id === targetId.value) ?? null;
  }
  return preloaded.value?.sheet ?? null;
});
const ready = computed(() => Boolean(fullSheets.value || preloaded.value));
const pageHeading = computed(() => (sheet.value ? `${sheet.value.name}动作值` : "武器动作值"));
usePageHeader(pageHeading, heading);

onServerPrefetch(async () => {
  const all = await loadJson<WeaponSheet[]>("weapon_actions/actions.json", ssr);
  const id = props.weaponId || all[0]?.id;
  const payload: WeaponPreload = {
    tabs: all.map((s) => ({ id: s.id, name: s.name })),
    sheet: all.find((s) => s.id === id) ?? null,
  };
  setPreloadedSlice(preloadKey.value, payload, ssr);
  preloaded.value = payload;
});

onMounted(() => {
  if (!fullSheets.value) {
    loadJson<WeaponSheet[]>("weapon_actions/actions.json").then(
      (data) => {
        fullSheets.value = data;
      },
      (failure: unknown) => {
        if (!preloaded.value) {
          error.value = failure instanceof Error ? failure : new Error(String(failure));
        }
      },
    );
  }
});

useSeoMeta(() => {
  if (!props.weaponId) {
    return {
      description: "按武器种类查询怪物猎人：荒野招式的动作值、眩晕值、属性倍率、异常倍率与部位破坏倍率。",
      ...sheet.value && {
        canonicalPath: router.resolve({ name: "weapon_actions", params: { weaponId: sheet.value.id } }).path,
      },
      indexable: false,
    };
  }
  if (!ready.value) return {};
  if (!sheet.value) {
    return {
      title: `未找到武器动作值 · ${SITE_TITLE}`,
      description: `未找到编号为 ${props.weaponId} 的武器动作值数据。`,
      indexable: false,
    };
  }
  const hitCount = sheet.value.groups.reduce((sum, group) => sum + group.rows.length, 0);
  return {
    title: `${sheet.value.name}动作值与倍率表 · ${SITE_TITLE}`,
    description: `怪物猎人：荒野「${sheet.value.name}」共 ${sheet.value.groups.length} 组招式、${hitCount} 条命中判定记录，含动作值、固定伤害、眩晕值、部位破坏、属性与异常倍率。`,
    ogType: "article",
    breadcrumbName: sheet.value.name,
  };
});

const groups = computed(() => {
  const text = query.value.trim().toLowerCase();
  return (sheet.value?.groups ?? []).filter((group) =>
    !text || group.name.toLowerCase().includes(text) || group.internal?.toLowerCase().includes(text),
  );
});
const count = computed(() => groups.value.reduce((sum, group) => sum + group.rows.length, 0));
const columns = [
  ["attack", "动作值"],
  ["fixedElement", "固定属性值"],
  ["fixed", "固定伤害值"],
  ["stun", "眩晕值"],
  ["breakRate", "部位破坏倍率"],
  ["elementRate", "属性倍率"],
  ["statusRate", "异常倍率"],
] as const;
function format(column: (typeof columns)[number][0], row: Hit) {
  if (column === "fixedElement") {
    const element = row.fixedElement;
    return element ? `${element.name} ${formatNumber(element.value)}` : "—";
  }
  const value = row[column];
  if (value == null) return "—";
  const text = formatNumber(value);
  return column.endsWith("Rate") ? `×${text}` : text;
}
</script>

<template>
  <div class="page weapons-page">
    <div ref="heading" class="page-heading">
      <div>
        <p class="eyebrow">武器动作值</p>
        <h1>{{ pageHeading }}</h1>
      </div>
    </div>
    <LoadState v-if="!ready" :error="error" />
    <section v-else-if="!sheet" class="surface no-weapon">
      <p>没有编号为 {{ props.weaponId }} 的武器数据。</p>
      <RouterLink class="tonal-button" :to="{ name: 'weapon_actions', params: { weaponId: '' } }">返回武器动作值</RouterLink>
    </section>
    <section v-else class="surface weapon-sheet">
      <nav class="weapons" aria-label="武器种类">
        <RouterLink
          v-for="item in tabs"
          :key="item.id"
          :to="{ name: 'weapon_actions', params: { weaponId: item.id } }"
          class="chip"
          :aria-current="item.id === sheet.id ? 'page' : undefined"
        >
          {{ item.name }}
        </RouterLink>
      </nav>
      <header class="table-bar">
        <div class="table-title"><h2>{{ sheet.name }}</h2><output class="count-label">{{ count }} 条命中记录</output></div>
        <label class="search-field small">
          <Icon name="search" /><input v-model="query" type="search" placeholder="搜索动作名称" aria-label="搜索动作名称" />
        </label>
      </header>
      <div v-if="count" class="table-scroll" role="region" tabindex="0" :aria-label="sheet.name + '动作值表'">
        <table class="data-table">
          <thead><tr><th scope="col">动作名称</th><th scope="col">判定编号</th><th v-for="[key, label] in columns" :key="key" scope="col">{{ label }}</th><th scope="col" class="condition">判定说明</th></tr></thead>
          <tbody v-for="(group, index) in groups" :key="index">
            <tr v-for="(row, i) in group.rows" :key="i">
              <th v-if="i === 0" scope="rowgroup" :rowspan="group.rows.length" class="action-name" :title="group.internal || undefined">{{ group.name }}</th>
              <td class="record-id">{{ row.request }}</td>
              <td v-for="[key] in columns" :key="key" :class="{ power: key === 'attack' }">{{ format(key, row) }}</td>
              <td class="condition">{{ row.condition || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="no-results">当前武器中没有匹配的动作。<button type="button" class="text-button" @click="query = ''">清除搜索</button></p>
    </section>
  </div>
</template>

<style scoped>
.weapon-sheet { overflow: hidden; }
.no-weapon { padding: 32px 24px; display: flex; flex-direction: column; align-items: flex-start; gap: 16px; }
.weapons { display: flex; flex-wrap: wrap; gap: 8px; padding: 20px 24px; border-bottom: 1px solid var(--divider); }
.table-bar, .table-title { display: flex; align-items: center; gap: 14px; }
.table-bar { justify-content: space-between; padding: 16px 24px; }
.table-title h2 { font-size: 21px; }
.table-bar .search-field { max-width: 240px; }
.table-scroll { overflow: auto; max-height: 70vh; scrollbar-gutter: stable; }
table { min-width: 64rem; white-space: nowrap; font-variant-numeric: tabular-nums; }
th, td { padding: 9px 12px; text-align: right; }
thead th { position: sticky; top: 0; z-index: 2; }
thead th:first-child, .action-name { text-align: left; padding-left: 24px; }
.action-name, td.condition { white-space: normal; overflow-wrap: anywhere; }
.action-name { width: 21%; min-width: 12rem; font-weight: 650; vertical-align: top; }
.condition { width: 18%; min-width: 10rem; text-align: left; }
td.condition { color: var(--on-surface-variant); font-family: var(--font); }
tbody + tbody tr:first-child > * { border-top: 1px solid var(--divider); }
@media (hover: hover) {
  tbody { transition: background-color var(--dur-effects-fast) var(--effects); }
  tbody:hover { background: var(--surface-hover); }
}
td { font-family: var(--mono); font-size: 13px; }
.power { font-weight: 750; color: var(--primary); }
.record-id { color: var(--on-surface-variant); }
.no-results { padding: 28px 24px; }
@media (max-width: 650px) {
  .weapons { padding: 14px; gap: 5px; }
  .table-bar { padding: 14px; align-items: start; flex-wrap: wrap; }
  .table-bar .search-field { max-width: none; flex: 1 1 160px; }
  th, td { padding: 8px 10px; }
  thead th:first-child, .action-name { padding-left: 14px; }
}
</style>
