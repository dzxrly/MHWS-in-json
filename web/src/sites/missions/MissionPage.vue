<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { UseLinkReturn } from "vue-router";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import { pageHeader, usePageHeader } from "../../composables/page_header";
import { SITE_TITLE } from "../../router";
import { catalog, catalogError } from "./catalog";
import MissionDetails from "./MissionDetails.vue";
import "./missions.css";

const props = defineProps<{ questId: string }>();
const route = useRoute();
const router = useRouter();
const heading = ref<HTMLElement | null>(null);
const quest = computed(() => catalog.value?.quests.find((item) => item.id === props.questId));
const title = computed(() => quest.value?.name ?? (catalog.value ? "未找到任务" : "任务详情"));
const listRoute = computed(() => ({ name: "missions", query: route.query }));

usePageHeader("任务详情", heading);
onMounted(() => {
  watch([title, () => props.questId], ([name]) => {
    pageHeader.title = name;
    document.title = `${name} · 任务信息 · ${SITE_TITLE}`;
  }, { immediate: true });
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
    <LoadState v-if="!catalog" :error="catalogError" label="正在读取任务数据…" />
    <MissionDetails v-else-if="quest" :key="quest.id" class="surface" :quest="quest" />
    <div v-else class="surface mission-empty">任务目录中没有编号为 {{ questId }} 的任务。</div>
  </div>
</template>
