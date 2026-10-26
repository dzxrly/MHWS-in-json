<script setup>
import { computed, ref } from "vue";

const props = defineProps({ effect: { type: Object, required: true }, levels: { type: Array, required: true } });
const MEANING_FIELDS = ["作用于", "计算", "条件"];
const highlighted = ref(null);

const meaning = computed(() => MEANING_FIELDS.filter((field) => props.effect.meaning[field]));
const plain = computed(() => {
  const rows = props.effect.rows;
  return rows.length === 1 && !rows[0].applies && !rows[0].situation;
});
// Bold a value where it differs from the previous level of the same row.
const rows = computed(() =>
  props.effect.rows.map((row) => {
    let previous = null;
    const cells = props.levels.map((level) => {
      const value = row.values[level];
      if (!value) return { level, text: "—", kind: "missing" };
      const kind = value.unsure ? "unsure" : previous === null ? "first" : value.text !== previous ? "changed" : "";
      previous = value.text;
      return { level, text: value.text, kind, unsure: value.unsure };
    });
    return { ...row, cells };
  }),
);
const basis = computed(() =>
  [
    ["代码名称", props.effect.code],
    ["含义依据", props.effect.meaning["依据"]],
    ["条目键", props.effect.key],
  ].filter(([, value]) => value),
);
function highlight(level) {
  highlighted.value = highlighted.value === level ? null : level;
}
</script>

<template>
  <section class="effect surface">
    <div class="effect-head">
      <h3>{{ effect.name }}</h3>
      <span v-if="effect.meaning['单位']" class="badge unit">{{ effect.meaning["单位"] }}</span>
      <span v-if="effect.written" class="badge" title="技能发动等处理写入运行时字段的数值">写入值</span>
    </div>
    <dl v-if="meaning.length" class="meaning">
      <template v-for="field in meaning" :key="field">
        <dt>{{ field }}</dt>
        <dd>{{ effect.meaning[field] }}</dd>
      </template>
    </dl>
    <div class="table-wrap">
      <table class="values">
        <thead>
          <tr>
            <th class="case" scope="col">{{ plain ? "适用" : "适用 / 情形" }}</th>
            <th
              v-for="level in levels"
              :key="level"
              scope="col"
              :class="{ hl: highlighted === level }"
              title="点击高亮此等级"
              @click="highlight(level)"
            >
              Lv.{{ level }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.applies + '\u0000' + row.situation">
            <td class="case">
              <span class="applies">{{ row.applies || (row.situation ? "" : "全部") }}</span>
              <span v-if="row.situation" class="situation">{{ row.situation }}</span>
            </td>
            <td
              v-for="cell in row.cells"
              :key="cell.level"
              class="v"
              :class="[cell.kind, { hl: highlighted === cell.level }]"
              :title="cell.unsure ? '代码中找不到区分这几种取值的条件' : undefined"
            >
              {{ cell.text }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <details class="basis">
      <summary>依据</summary>
      <dl>
        <template v-for="[name, value] in basis" :key="name">
          <dt>{{ name }}</dt>
          <dd>{{ value }}</dd>
        </template>
      </dl>
    </details>
  </section>
</template>

<style scoped>
.effect {
  padding: 20px 24px 16px;
  border-radius: 24px;
  min-width: 0;
}
.effect-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
}
.effect-head h3 {
  font-size: 18px;
  font-weight: 650;
  line-height: 1.5;
}
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0 12px;
  min-height: 26px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--secondary-container);
  color: var(--on-secondary-container);
}
.badge.unit {
  background: var(--primary-container);
  color: var(--on-primary-container);
}
.meaning {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 14px;
  margin: 10px 0 0;
  font-size: 13.5px;
  line-height: 1.7;
}
.meaning dt {
  color: var(--primary);
  font-weight: 600;
}
.meaning dd {
  margin: 0;
  color: var(--on-surface-variant);
}
.table-wrap {
  margin-top: 14px;
  overflow-x: auto;
  border-radius: 16px;
  background: var(--surface-lowest);
  border: 1px solid color-mix(in srgb, var(--outline-variant) 60%, transparent);
}
.values {
  border-collapse: collapse;
  font-size: 14px;
  min-width: 100%;
}
.values th,
.values td {
  padding: 8px 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--outline-variant) 50%, transparent);
  text-align: left;
}
.values thead th {
  color: var(--on-surface-variant);
  font-weight: 600;
  font-size: 12px;
  white-space: nowrap;
  background: color-mix(in srgb, var(--surface-high) 60%, transparent);
  cursor: pointer;
  user-select: none;
  text-align: right;
}
.values thead th.case {
  cursor: default;
  text-align: left;
}
.values thead th:not(.case):hover {
  color: var(--primary);
}
.values td.case {
  min-width: 120px;
  max-width: 420px;
  color: var(--on-surface-variant);
  font-size: 13px;
}
.values td.case .applies {
  color: var(--on-surface);
}
.values td.case .situation {
  display: block;
}
.values td.v {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  min-width: 64px;
  color: var(--on-surface-variant);
}
.values td.v.changed {
  color: var(--value);
  font-weight: 700;
}
.values td.v.first {
  color: var(--on-surface);
  font-weight: 600;
}
.values td.v.missing {
  color: var(--outline-variant);
}
.values td.v.unsure {
  color: var(--unsure);
  background: var(--unsure-soft);
  font-weight: 600;
}
.values .hl {
  background: var(--highlight);
}
.values tbody tr:last-child td {
  border-bottom: none;
}
.basis {
  margin-top: 10px;
  font-size: 13px;
}
.basis dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 2px 12px;
  margin: 8px 0 2px;
}
.basis dt {
  color: var(--on-surface-variant);
}
.basis dd {
  margin: 0;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--on-surface-variant);
  word-break: break-all;
}
@media (max-width: 479px) {
  .effect {
    padding: 16px 16px 12px;
    border-radius: 20px;
  }
}
</style>
