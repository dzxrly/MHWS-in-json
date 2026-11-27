<script setup lang="ts">
import { computed, ref } from "vue";
import MonsterIcon from "./MonsterIcon.vue";
import MissionCombat from "./MissionCombat.vue";
import type { Mission, MissionReward } from "./catalog";
import { number, targetName } from "./format";

const props = defineProps<{ quest: Mission }>();
const targetIndex = ref(0);
const target = computed(() => props.quest.targets[targetIndex.value]);
const targetSummaries = computed(() =>
  props.quest.targets.map((item) => {
    const solo = item.combat?.parties.find((p) => p.players === 1)?.health.map((h) => h.hp) ?? [];
    const hpText = solo.length
      ? Math.min(...solo) === Math.max(...solo)
        ? `单人血量 ${number(Math.min(...solo))}`
        : `单人血量 ${number(Math.min(...solo))}–${number(Math.max(...solo))}`
      : "";
    return {
      label: targetName(item),
      detail: [item.objective, hpText].filter(Boolean).join(" · "),
    };
  }),
);
const rewardGroups = computed(() => {
  const groups = new Map<string, MissionReward[]>();
  for (const reward of props.quest.rewards) {
    const items = groups.get(reward.group);
    if (items) items.push(reward);
    else groups.set(reward.group, [reward]);
  }
  return groups;
});
</script>

<template>
  <div class="mission-details">
    <dl class="quest-facts">
      <div><dt>原野</dt><dd>{{ quest.stage || "—" }}</dd></div>
      <div><dt>受理条件</dt><dd>{{ quest.hr == null ? "—" : `HR ${quest.hr} 起` }}</dd></div>
      <div><dt>人数上限</dt><dd>{{ quest.maxPlayers }} 人</dd></div>
      <div><dt>时间限制</dt><dd>{{ number(quest.timeLimit) }} 分钟</dd></div>
      <div><dt>力尽次数</dt><dd>{{ quest.faints }} 次</dd></div>
      <div><dt>报酬金</dt><dd>{{ number(quest.money) }} z</dd></div>
    </dl>
    <section class="detail-content" aria-labelledby="mission-targets-heading">
      <h2 id="mission-targets-heading">目标数据</h2>
      <div v-if="quest.targets.length > 1" class="detail-targets" role="group" aria-label="选择任务目标">
        <button v-for="(item, index) in quest.targets" :key="index" class="chip" type="button"
          :aria-pressed="targetIndex === index" @click="targetIndex = index">
          <MonsterIcon :target="item" />
          <span><small>目标 {{ index + 1 }}</small><b>{{ targetName(item) }}</b></span>
        </button>
      </div>
      <ul v-if="quest.targets.length > 1" class="target-overview" aria-label="全部目标概览">
        <li v-for="(item, index) in targetSummaries" :key="index">
          <strong>{{ item.label }}</strong>
          <span v-if="item.detail">（{{ item.detail }}）</span>
        </li>
      </ul>
      <template v-if="target">
        <div class="target-title">
          <MonsterIcon v-if="quest.targets.length === 1" :target="target" />
          <div>
            <h3>{{ targetName(target) }}</h3>
            <p v-if="target.objective || target.spawn">{{ [target.objective, target.spawn].filter(Boolean).join(" · ") }}</p>
          </div>
        </div>
        <MissionCombat v-if="target.combat" :combat="target.combat" />
      </template>
      <p v-else class="detail-note">{{ quest.type }}</p>
    </section>
    <section class="detail-content" aria-labelledby="mission-rewards-heading">
      <h2 id="mission-rewards-heading">报酬</h2>
      <dl v-if="quest.hrPoints > 0 || quest.points > 0" class="quest-points">
        <div v-if="quest.hrPoints > 0"><dt>猎人等级点数</dt><dd>{{ number(quest.hrPoints) }}</dd></div>
        <div v-if="quest.points > 0"><dt>调查点数</dt><dd>{{ number(quest.points) }}</dd></div>
      </dl>
      <section v-for="[group, rewards] in rewardGroups" :key="group" class="reward-group">
        <h3>{{ group }}</h3>
        <div class="mission-table-scroll">
          <table class="data-table mission-table">
            <thead><tr><th scope="col">物品</th><th scope="col">数量</th><th scope="col">表列概率</th></tr></thead>
            <tbody><tr v-for="(reward, i) in rewards" :key="i">
              <th scope="row">{{ reward.name }}</th><td>×{{ number(reward.quantity) }}</td><td>{{ reward.probability == null ? "—" : number(reward.probability) + "%" }}</td>
            </tr></tbody>
          </table>
        </div>
      </section>
      <section v-if="quest.rankRewards?.length" class="reward-group">
        <h3>剧情任务档位报酬</h3>
        <div class="mission-table-scroll">
          <table class="data-table mission-table rank-rewards">
            <thead><tr><th scope="col">档位</th><th scope="col">报酬金</th><th scope="col">调查点数</th><th scope="col">猎人等级点数</th><th scope="col">物品</th></tr></thead>
            <tbody><tr v-for="entry in quest.rankRewards" :key="entry.rank">
              <th scope="row">{{ entry.rank }}</th><td>{{ number(entry.money) }} z</td><td>{{ number(entry.points) }}</td><td>{{ number(entry.hrPoints) }}</td>
              <td>{{ entry.items.map(item => item.name + ' ×' + number(item.quantity)).join('、') || '—' }}</td>
            </tr></tbody>
          </table>
        </div>
      </section>
      <p v-if="!quest.rewards.length && !quest.rankRewards?.length" class="detail-note">此任务未列出道具报酬表。</p>
      <details v-if="quest.rewardSlots?.length" class="reward-slots">
        <summary>基础报酬格数（通用配置）</summary>
        <ul class="hp-grades" aria-label="基础报酬总格数及概率">
          <li v-for="slot in quest.rewardSlots" :key="slot.count">
            <b>{{ slot.count }} 格</b><span>{{ number(slot.probability) }}%</span>
          </li>
        </ul>
      </details>
    </section>
    <section class="detail-content quest-description" aria-labelledby="mission-description-heading">
      <h2 id="mission-description-heading">任务说明</h2>
      <dl>
        <div><dt>任务编号</dt><dd class="mono">{{ quest.id }}</dd></div>
        <div><dt>任务类别</dt><dd>{{ quest.category }} · {{ quest.type }}</dd></div>
        <div v-if="quest.prerequisite"><dt>前置任务</dt><dd>{{ quest.prerequisite }}</dd></div>
        <div v-if="quest.client"><dt>委托人</dt><dd>{{ quest.client }}</dd></div>
        <div v-if="quest.description"><dt>委托内容</dt><dd>{{ quest.description }}</dd></div>
      </dl>
    </section>
  </div>
</template>
