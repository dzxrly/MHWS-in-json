<script setup lang="ts">
import { computed, ref, useId, watch } from "vue";
import SiteSelect from "../../components/SiteSelect.vue";
import type { CombatState, TargetCombat } from "./catalog";
import { number, rate } from "./format";
import { combatReadout, stateLabels } from "./combat_readout";

const props = defineProps<{ combat: TargetCombat }>();
const id = useId();
const showBreakdown = ref(false);
const players = ref(1);
const state = ref<CombatState>("normal");
const grade = ref(0);
// -2 compares actions, -1 is the ordinary action without a specific modifier.
const actionIndex = ref(-2);
const phase = ref("");
const party = computed(() => props.combat.parties.find((entry) => entry.players === players.value) ?? props.combat.parties[0]);
const totals = computed(() => party.value.states[state.value] ?? party.value.states.normal);
const gradeIndex = computed(() => props.combat.grades.findIndex((entry) => entry.grade === grade.value));
const actions = computed(() => props.combat.actions ?? []);
const actionOptions = computed(() => [
  { value: -2, label: "各招式范围" },
  { value: -1, label: "通用招式" },
  ...actions.value.map(({ name }, i) => ({ value: i, label: name })),
]);
const shownActions = computed(() => actionIndex.value === -2
  ? [undefined, ...actions.value]
  : [actions.value[actionIndex.value]]);
const phaseOptions = computed(() => Object.keys(props.combat.phases ?? {}).map(label => ({ label, value: label })));
const readout = computed(() => combatReadout(props.combat, party.value, state.value, gradeIndex.value, shownActions.value, phase.value));
const partyOptions = computed(() => props.combat.parties.map(({ players }) => ({
  value: players,
  label: `${players} 人`,
})));
const gradeOptions = computed(() => props.combat.grades.map(({ grade, probability }) => ({
  value: grade,
  label: `${gradeName(grade)}（${number(probability)}%）`,
})));

watch(() => props.combat, (combat) => {
  showBreakdown.value = false;
  actionIndex.value = -2;
  phase.value = phaseOptions.value[0]?.value ?? "";
  players.value = party.value.players;
  if (!party.value.states[state.value]) state.value = "normal";
  if (gradeIndex.value < 0) grade.value = (combat.grades.find((entry) => entry.grade === 0) ?? combat.grades[0]).grade;
}, { immediate: true });

function gradeName(value: number) {
  if (props.combat.grades.length === 1) return "固定";
  return value === 0 ? "中间档" : `${value > 0 ? "+" : ""}${value} 档`;
}
</script>

<template>
  <section class="mission-combat" aria-label="招式总倍率">
    <div class="combat-heading">
      <h4>招式总倍率</h4>
      <button v-if="combat.factors" class="rate-help" type="button" title="倍率计算明细"
        aria-label="倍率计算明细" :aria-controls="`${id}-breakdown`" :aria-expanded="showBreakdown"
        @click="showBreakdown = !showBreakdown"><span aria-hidden="true">?</span></button>
    </div>
    <div class="rate-controls">
      <div class="button-group" role="group" aria-label="怪物状态">
        <button v-for="(_, key) in party.states" :key="key" class="chip" type="button"
          :aria-pressed="state === key" @click="state = key">{{ stateLabels[key] }}</button>
      </div>
      <div class="rate-field">
        <label :for="`${id}-players`">人数</label>
        <SiteSelect :id="`${id}-players`" v-model="players" label="人数" :options="partyOptions" :disabled="partyOptions.length === 1" />
      </div>
      <div class="rate-field">
        <label :for="`${id}-grade`">攻击档位</label>
        <SiteSelect :id="`${id}-grade`" v-model="grade" label="攻击档位" :options="gradeOptions" :disabled="gradeOptions.length === 1" />
      </div>
      <div v-if="actions.length" class="rate-field action-field">
        <label :for="`${id}-action`">招式</label>
        <SiteSelect :id="`${id}-action`" v-model="actionIndex" label="招式" :options="actionOptions" />
      </div>
      <div v-if="phaseOptions.length" class="rate-field">
        <label :for="`${id}-phase`">战斗阶段</label>
        <SiteSelect :id="`${id}-phase`" v-model="phase" label="战斗阶段" :options="phaseOptions" />
      </div>
    </div>
    <div class="rate-readout" aria-live="polite" aria-atomic="true">
      <dl class="rate-primary">
        <div v-for="metric in readout.primary" :key="metric.label"><dt>{{ metric.label }}</dt><dd>{{ metric.display }}</dd></div>
      </dl>
      <dl class="rate-secondary">
        <div v-for="metric in readout.secondary" :key="metric.label"><dt>{{ metric.label }}</dt><dd>{{ metric.display }}</dd></div>
      </dl>
    </div>
    <section v-if="combat.factors" v-show="showBreakdown" :id="`${id}-breakdown`"
      class="rate-breakdown" aria-label="倍率计算明细">
      <h4>倍率计算明细</h4>
      <p>目标奖励等级 {{ combat.factors.rewardRank }}。行动速度取普通战斗中的全身招式基准，个别动画片段和图层还会单独变速。</p>
      <dl>
        <div v-for="metric in [...readout.primary, ...readout.secondary]" :key="metric.label">
          <dt>{{ metric.label }}</dt>
          <dd v-for="(line, i) in metric.endpoints" :key="i">
            <small v-if="line.caption || metric.endpoints.length > 1">{{ metric.endpoints.length > 1 ? (i ? '最高 ' : '最低 ') : '' }}{{ line.caption }}</small>
            {{ line.expression }}<span v-if="line.limit">（{{ line.limit }}）</span>
            <strong> = {{ number(line.value) }}</strong>
          </dd>
        </div>
      </dl>
    </section>
    <details v-if="combat.damageConditions?.length" class="reward-slots">
      <summary>特定条件下的伤害</summary>
      <table class="data-table mission-table">
        <thead><tr><th scope="col">条件</th><th scope="col">通用物理伤害</th><th scope="col">通用属性伤害</th></tr></thead>
        <tbody>
          <tr v-for="entry in combat.damageConditions" :key="entry.name">
            <th scope="row">{{ entry.name }}</th>
            <td>{{ rate(totals.physical[gradeIndex] * entry.physical) }}</td>
            <td>{{ rate(totals.element[gradeIndex] * entry.element) }}</td>
          </tr>
        </tbody>
      </table>
    </details>
    <details v-if="combat.incomingConditions?.length" class="reward-slots">
      <summary>特定部位受到的伤害</summary>
      <table class="data-table mission-table">
        <thead><tr><th scope="col">命中条件</th><th scope="col">斩击／打击</th><th scope="col">弹类攻击</th></tr></thead>
        <tbody>
          <tr v-for="entry in combat.incomingConditions" :key="entry.name">
            <th scope="row">{{ entry.name }}</th>
            <td>{{ rate(totals.slash * entry.slash) }}</td>
            <td>{{ rate(totals.shot * entry.shot) }}</td>
          </tr>
        </tbody>
      </table>
    </details>
    <details v-if="combat.shells?.length" class="reward-slots">
      <summary>特殊弹体伤害</summary>
      <div class="mission-table-scroll"><table class="data-table mission-table">
        <thead><tr><th scope="col">弹体</th><th scope="col">发射条件</th><th scope="col">物理伤害</th><th scope="col">属性伤害</th></tr></thead>
        <tbody>
          <template v-for="shell in combat.shells" :key="shell.id">
            <tr v-for="source in shell.sources" :key="source.name">
              <th scope="row">{{ shell.name }}</th><td>{{ source.name }}</td>
              <td>{{ rate(totals.physical[gradeIndex] * shell.attack * source.attack) }}</td>
              <td>{{ rate(totals.element[gradeIndex] * shell.attack * source.attack) }}</td>
            </tr>
            <tr>
              <th scope="row">{{ shell.name }}</th>
              <td>{{ shell.ignoreAction ? "独立于发射招式" : shell.sources?.length ? "其他发射招式" : "按实际发射招式" }}</td>
              <td>{{ rate(totals.physical[gradeIndex] * shell.attack) }}<small v-if="!shell.ignoreAction"> × 招式倍率</small></td>
              <td>{{ rate(totals.element[gradeIndex] * shell.attack) }}<small v-if="!shell.ignoreAction"> × 招式倍率</small></td>
            </tr>
          </template>
        </tbody>
      </table></div>
    </details>
    <section class="detail-subsection">
      <h4>{{ party.players === 1 ? "单人" : `${party.players} 人` }}初始血量</h4>
      <ul class="hp-grades" aria-label="血量档位及概率">
        <li v-for="entry in party.health" :key="entry.hp">
          <b>{{ number(entry.hp) }}</b><span>{{ number(entry.probability) }}%</span>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.mission-combat { margin-top: 20px; }
.mission-combat h4 { font-size: 15px; }
.combat-heading, .rate-help { display: flex; align-items: center; }
.combat-heading { gap: 4px; }
.rate-help {
  justify-content: center; width: 36px; height: 36px; padding: 0; border: 0;
  border-radius: 50%; background: transparent; color: var(--primary); cursor: pointer;
}
.rate-help span {
  display: grid; place-items: center; width: 18px; height: 18px; border: 1.5px solid currentColor;
  border-radius: 50%; font: 700 12px/1 var(--font);
}
.rate-help:hover, .rate-help[aria-expanded="true"] { background: var(--primary-container); }
.rate-help:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.rate-breakdown { margin-top: 12px; padding: 16px 20px; border-radius: var(--radius-small); background: var(--surface-hover); }
.rate-breakdown p { margin: 6px 0 12px; font-size: 13px; color: var(--on-surface-variant); }
.rate-breakdown dl > div { padding: 8px 0; border-top: 1px solid var(--outline-variant); }
.rate-breakdown dt { color: var(--on-surface); font-weight: 600; }
.rate-breakdown dd { line-height: 1.7; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.rate-breakdown small { display: block; color: var(--on-surface-variant); }
.rate-breakdown strong { color: var(--primary); white-space: nowrap; }
.rate-controls, .rate-field { display: flex; align-items: center; }
.rate-controls { flex-wrap: wrap; gap: 10px 18px; margin: 12px 0 16px; }
.rate-field { gap: 8px; max-width: 100%; min-width: 0; color: var(--on-surface-variant); font-size: 13px; }
.rate-field > label { flex: none; }
.action-field .site-select { min-width: 0; max-width: 100%; }
.rate-readout { background: var(--surface-hover); border-radius: var(--radius-small); overflow: hidden; }
.rate-primary, .rate-secondary { display: grid; gap: 16px; padding: 16px 20px; }
.rate-primary { grid-template-columns: repeat(3,minmax(0,1fr)); background: var(--primary-container); color: var(--on-primary-container); }
.rate-primary dt { color: inherit; }
.rate-secondary { grid-template-columns: repeat(4,minmax(0,1fr)); }
.rate-readout dl dd { font: 14px/1.4 var(--mono); }
.rate-readout .rate-primary dd { font-size: clamp(16px, 2.1vw, 24px); }
@media (max-width: 620px) {
  .rate-controls .button-group { flex-basis: 100%; }
  .rate-controls { gap: 8px; }
  .rate-field { flex-wrap: wrap; gap: 4px; }
  .rate-primary, .rate-secondary { gap: 10px; padding: 12px; }
  .rate-secondary { grid-template-columns: repeat(2,minmax(0,1fr)); }
}
@media (max-width: 620px) {
  .rate-primary { grid-template-columns: 1fr; }
  .rate-primary > div { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 4px 8px; }
}
</style>
