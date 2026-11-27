<script setup lang="ts">
import { computed } from "vue";
import Icon from "../../components/Icon.vue";
import type { MissionListTarget } from "./catalog";

const props = defineProps<{ target: MissionListTarget }>();
const texture = `url(${import.meta.env.BASE_URL}quest-icons.webp)`;
const cell = computed(() => props.target.icon ?? (props.target.id ? 160 : null));
</script>

<template>
  <span class="monster-icon" :class="target.state" aria-hidden="true">
    <span v-if="cell !== null" class="sprite" :style="{
      backgroundImage: texture,
      backgroundPosition: `${-(cell % 20)}em ${-Math.floor(cell / 20)}em`,
    }" />
    <Icon v-else name="target" />
  </span>
</template>

<style scoped>
.monster-icon {
  display: inline-grid;
  place-items: center;
  flex: none;
  width: 1em;
  height: 1em;
  font-size: var(--monster-size, 52px);
  vertical-align: middle;
}
.sprite {
  width: 1em;
  height: 1em;
  background-size: 20.48em 20.48em;
  background-repeat: no-repeat;
}
.NORMAL { --rim: #9854c5; }
.KING { --rim: #e67f2b; }
.NORMAL .sprite, .KING .sprite {
  filter: drop-shadow(1.2px 0 0 var(--rim)) drop-shadow(-1.2px 0 0 var(--rim))
          drop-shadow(0 1.2px 0 var(--rim)) drop-shadow(0 -1.2px 0 var(--rim));
}
.icon { color: var(--outline); width: 52%; height: 52%; }
</style>
