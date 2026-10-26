<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import SiteHeader from "./components/SiteHeader.vue";
import SiteFooter from "./components/SiteFooter.vue";

const route = useRoute();
// Graph pages use the full window width under the header.
const workspace = computed(() => !!route.meta.workspace);
</script>

<template>
  <div class="site-background" aria-hidden="true" />
  <a class="skip-link" href="#main-content">跳到正文</a>
  <SiteHeader :wide="workspace" />
  <main id="main-content" :class="{ workspace }" tabindex="-1">
    <RouterView />
  </main>
  <SiteFooter />
</template>
