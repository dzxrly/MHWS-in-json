<script setup lang="ts">
import { computed, onMounted, onServerPrefetch, ref, shallowRef, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { UseLinkReturn } from "vue-router";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import { getCachedJson, getPreloadedSlice, setPreloadedSlice, useSsrDataContext } from "../../composables/data";
import { usePageHeader } from "../../composables/page_header";
import { useSeoMeta } from "../../composables/seo";
import { SITE_TITLE } from "../../seo/config";
import { loadMission, missionFilePath, type Mission } from "./catalog";
import MissionDetails from "./MissionDetails.vue";
import "./missions.css";

const props = defineProps<{ questId: string }>();
const route = useRoute();
const router = useRouter();
const ssr = useSsrDataContext();
const heading = ref<HTMLElement | null>(null);
const catalogError = shallowRef<Error | null>(null);

function initialQuest(): { ready: boolean; quest: Mission | null } {
  const path = missionFilePath(props.questId);
  const preloaded = getPreloadedSlice<Mission>(path, ssr);
  if (preloaded !== undefined) return { ready: true, quest: preloaded };
  const cached = getCachedJson<Mission>(path);
  if (cached) return { ready: true, quest: cached };
  return { ready: false, quest: null };
}

const initial = initialQuest();
const ready = ref(initial.ready);
const quest = shallowRef<Mission | null>(initial.quest);
const title = computed(() => quest.value?.name ?? (ready.value ? "未找到任务" : "任务详情"));
const listRoute = computed(() => ({ name: "missions", query: route.query }));

onServerPrefetch(async () => {
  const loaded = await loadMission(props.questId, ssr);
  quest.value = loaded;
  ready.value = true;
  setPreloadedSlice(missionFilePath(props.questId), loaded, ssr);
});

async function refreshQuest(questId: string) {
  const path = missionFilePath(questId);
  const cached = getCachedJson<Mission>(path);
  if (cached) {
    quest.value = cached;
    ready.value = true;
    return;
  }
  catalogError.value = null;
  try {
    const loaded = await loadMission(questId);
    if (questId !== props.questId) return;
    quest.value = loaded;
    ready.value = true;
  } catch (failure) {
    if (questId !== props.questId) return;
    if (failure instanceof Error && failure.message.includes("HTTP 404")) {
      quest.value = null;
      ready.value = true;
    } else if (!ready.value) {
      catalogError.value = failure instanceof Error ? failure : new Error(String(failure));
    }
  }
}

onMounted(() => {
  if (!ready.value) {
    void refreshQuest(props.questId);
  }
  watch(() => props.questId, (questId) => {
    ready.value = false;
    quest.value = null;
    void refreshQuest(questId);
  });
});

usePageHeader(title, heading);
useSeoMeta(() => {
  if (!ready.value) return {};
  if (!quest.value) {
    return {
      title: `未找到任务 · 任务信息 · ${SITE_TITLE}`,
      description: `任务目录中没有编号为 ${props.questId} 的任务。`,
      indexable: false,
    };
  }
  const q = quest.value;
  const targetNames = q.targets.map((t) => t.name).filter(Boolean).join("、");
  const soloHps = q.targets
    .flatMap((t) => t.combat?.parties.find((p) => p.players === 1)?.health.map((h) => h.hp) ?? []);
  const hpText = soloHps.length
    ? `单人血量 ${Math.min(...soloHps) === Math.max(...soloHps) ? Math.min(...soloHps) : `${Math.min(...soloHps)}–${Math.max(...soloHps)}`}`
    : "";
  const hasMultiHealth = q.targets.some((target) => target.combat?.parties.some(
    (party) => party.players > 1 && party.health.length > 0,
  ));
  const hasActionSpeed = q.targets.some((target) => target.combat?.actions?.some(
    (action) => Object.keys(action.speed).length > 0,
  ));
  const hasRewards = q.rewards.length || q.rankRewards?.length || q.rewardSlots?.length;
  const contents = [
    hasMultiHealth ? "多人血量倍率" : "",
    hasActionSpeed ? "招式速度" : "",
    hasRewards ? "报酬表" : "",
  ].filter(Boolean);
  const contentText = contents.length
    ? `含${contents.length > 1 ? `${contents.slice(0, -1).join("、")}与${contents[contents.length - 1]}` : contents[0]}`
    : "";
  const summary = [
    `${q.stars}星${q.rank}${q.type}任务`,
    targetNames ? `目标：${targetNames}` : "",
    hpText,
    q.stage ? `原野：${q.stage}` : "",
    contentText,
  ]
    .filter(Boolean)
    .join("，");
  const details = [soloHps.length ? "血量" : "", hasRewards ? "报酬" : ""].filter(Boolean).join("与");
  return {
    title: `${q.name}（★${q.stars} ${q.rank}${q.type}）- 任务${details || "详情"} · ${SITE_TITLE}`,
    description: `怪物猎人：荒野《${q.name}》${summary}。`,
    ogType: "article",
    breadcrumbName: q.name,
  };
});

function returnToList(event: MouseEvent, navigate: UseLinkReturn["navigate"]) {
  const back = router.options.history.state.back;
  if (back === router.resolve(listRoute.value).fullPath && event.button === 0 &&
      !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault();
    router.back();
  } else {
    navigate(event);
  }
}
</script>

<template>
  <div class="page missions-page mission-detail-page">
    <RouterLink v-slot="{ href, navigate }" :to="listRoute" custom>
      <a class="text-button mission-back" :href="href" @click="returnToList($event, navigate)">
        <Icon name="back" />返回任务列表
      </a>
    </RouterLink>
    <header ref="heading" class="page-heading mission-heading">
      <p v-if="quest" class="mission-kind">{{ quest.category }} · {{ quest.rank }} · {{ quest.type }}</p>
      <div class="mission-title-row">
        <h1>{{ title }}</h1>
        <span v-if="quest" class="mission-stars">★ {{ quest.stars }}</span>
      </div>
    </header>
    <LoadState v-if="!ready" :error="catalogError" label="正在读取任务数据…" />
    <MissionDetails v-else-if="quest" :key="quest.id" class="surface" :quest="quest" />
    <div v-else class="surface mission-empty">任务目录中没有编号为 {{ questId }} 的任务。</div>
  </div>
</template>
