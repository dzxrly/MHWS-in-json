<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from "vue-router";

defineProps<
  | { to: RouteLocationRaw; href?: never }
  | { href: string; to?: never }
>();
</script>

<template>
  <component
    :is="to === undefined ? 'a' : RouterLink"
    v-bind="to === undefined ? { href } : { to }"
    class="surface card-link"
  ><slot /></component>
</template>
