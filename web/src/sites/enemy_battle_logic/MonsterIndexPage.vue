<script setup lang="ts">
import { computed, ref } from "vue";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import SiteCard from "../../components/SiteCard.vue";
import { loadJson } from "../../composables/data";
import { pageHeader, usePageHeader } from "../../composables/page_header";
import type { MonsterIndex } from "./types";

const index = ref<MonsterIndex | null>(null);
const error = ref<Error | null>(null);
const query = ref("");
const toolbar = ref<HTMLElement>();
const searchInput = ref<HTMLInputElement>();
usePageHeader("怪物行动逻辑", toolbar, { tools: true, focusTarget: searchInput });
loadJson<MonsterIndex>("enemy_battle_logic/index.json").then(
  (data) => (index.value = data),
  (failure: unknown) => (error.value = failure instanceof Error ? failure : new Error(String(failure))),
);

const shown = computed(() => {
  const text = query.value.trim().toLocaleLowerCase();
  const monsters = index.value?.monsters ?? [];
  return text
    ? monsters.filter((m) => `${m.enemyName} ${m.enemyId}`.toLocaleLowerCase().includes(text))
    : monsters;
});
</script>

<template>
  <div class="page">
    <div class="page-heading">
      <div>
        <h1>怪物行动逻辑</h1>
      </div>
    </div>
    <LoadState v-if="!index" :error="error" />
    <template v-else>
      <div ref="toolbar" class="toolbar">
        <div class="search-slot">
          <Teleport to="#header-tools" :disabled="!pageHeader.condensed" defer>
            <label class="search-field">
              <Icon name="search" />
              <input
                ref="searchInput"
                v-model="query"
                type="search"
                placeholder="搜索名称或编号"
                aria-label="搜索怪物名称或编号"
                autocomplete="off"
              />
            </label>
          </Teleport>
        </div>
        <span class="count-label" aria-live="polite">{{
          query.trim() ? `${shown.length} / ${index.monsters.length}` : `共 ${index.monsters.length} 只`
        }}</span>
      </div>
      <p v-if="!index.releaseReady" class="preview-note">研究预览：只包含部分怪物，不是正式发布的数据。</p>
      <ul class="monster-grid">
        <li v-for="monster in shown" :key="monster.enemyId">
          <SiteCard class="monster-card" :to="`/enemy_battle_logic/${monster.enemyId}`">
            <span class="monster-id mono">{{ monster.enemyId }}</span>
            <span class="card-title">{{ monster.enemyName }}</span>
            <span class="monster-stats">
              <span v-if="monster.behaviorTables"><b>{{ monster.behaviorTables }}</b> 张行为表</span>
              <span v-if="monster.actions"><b>{{ monster.actions }}</b> 个动作</span>
              <span class="card-arrow" aria-hidden="true"><Icon name="arrow" /></span>
            </span>
          </SiteCard>
        </li>
      </ul>
      <p v-if="!shown.length" class="empty-state">没有匹配的怪物。</p>
    </template>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
/* Keeps the row's height while the search sits in the header. */
.search-slot {
  flex: 0 1 420px;
  min-height: 48px;
}
:global(.header-tools .search-field) {
  width: min(420px, 100%);
}
.preview-note {
  margin-bottom: 20px;
  padding: 12px 20px;
  border-radius: var(--shape-l-plus);
  background: var(--error-container);
  color: var(--on-error-container);
}
.monster-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.monster-card {
  height: 100%;
  padding: 20px 20px 16px 22px;
  gap: 2px;
}
.monster-id {
  font-size: 12px;
  color: var(--on-surface-variant);
}
.monster-stats {
  margin-top: auto;
  padding-top: 12px;
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: var(--on-surface-variant);
}
.monster-stats b {
  color: var(--on-surface);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.monster-stats .card-arrow {
  margin-left: auto;
}
@media (max-width: 559px) {
  .monster-grid {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .monster-card {
    padding: 14px 14px 12px;
  }
  .monster-stats {
    flex-direction: column;
    align-items: flex-start;
    gap: 0;
  }
  .monster-stats .card-arrow {
    display: none;
  }
}
</style>
