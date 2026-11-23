<script setup lang="ts">
import { computed, ref, shallowRef } from "vue";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import { loadJson } from "../../composables/data";
import { formatNumber } from "../../composables/numbers";
import { usePageHeader } from "../../composables/page_header";

interface Hit {
  request: number;
  condition: string | null;
  attack: number;
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

const sheets = shallowRef<WeaponSheet[]>([]);
const error = shallowRef<Error | null>(null);
const selected = ref("Wp00");
const query = ref("");
const heading = ref<HTMLElement | null>(null);
usePageHeader("武器动作值", heading);
loadJson<WeaponSheet[]>("weapon_actions/actions.json").then(
  (data) => { sheets.value = data; },
  (failure: unknown) => { error.value = failure instanceof Error ? failure : new Error(String(failure)); },
);

const sheet = computed(() => sheets.value.find(item => item.id === selected.value));
const groups = computed(() => {
  const text = query.value.trim().toLowerCase();
  return (sheet.value?.groups ?? []).filter(group =>
    !text || group.name.toLowerCase().includes(text) || group.internal?.toLowerCase().includes(text)
  );
});
const count = computed(() => groups.value.reduce((sum, group) => sum + group.rows.length, 0));
const columns = [
  ["attack", "动作值"], ["fixed", "固定伤害值"], ["stun", "眩晕值"],
  ["breakRate", "部位破坏倍率"], ["elementRate", "属性倍率"], ["statusRate", "异常倍率"],
] as const;
function format(column: typeof columns[number][0], value: number | null) {
  if (value == null) return "—";
  const text = formatNumber(value);
  return column.endsWith("Rate") ? `×${text}` : text;
}
</script>

<template>
  <div class="page weapons-page">
    <div ref="heading" class="page-heading"><h1>武器动作值</h1></div>
    <LoadState v-if="!sheet" :error="error" />
    <section v-else class="surface weapon-sheet">
      <div class="weapons" role="group" aria-label="武器种类">
        <button v-for="item in sheets" :key="item.id" type="button" class="chip" :aria-pressed="item.id === selected" @click="selected = item.id">
          {{ item.name }}
        </button>
      </div>
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
              <td v-for="[key] in columns" :key="key" :class="{ power: key === 'attack' }">{{ format(key, row[key]) }}</td>
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
.weapons { display: flex; flex-wrap: wrap; gap: 8px; padding: 20px 24px; border-bottom: 1px solid var(--divider); }
.table-bar, .table-title { display: flex; align-items: center; gap: 14px; }
.table-bar { justify-content: space-between; padding: 16px 24px; }
.table-title h2 { font-size: 21px; }
.table-bar .search-field { max-width: 240px; }
.table-scroll { overflow: auto; max-height: 70vh; scrollbar-gutter: stable; }
table { min-width: 58rem; white-space: nowrap; font-variant-numeric: tabular-nums; }
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
