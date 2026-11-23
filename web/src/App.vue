<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import SiteHeader from "./components/SiteHeader.vue";
import SiteFooter from "./components/SiteFooter.vue";
import { useControlRipple } from "./composables/ripple";

const route = useRoute();
useControlRipple();
// Graph pages use the full window width under the header.
const workspace = computed(() => !!route.meta.workspace);
</script>

<template>
  <div class="site-background" aria-hidden="true" />
  <a class="skip-link" href="#main-content">跳到正文</a>
  <SiteHeader :wide="workspace" />
  <main id="main-content" :class="{ workspace }" tabindex="-1">
    <RouterView v-slot="{ Component, route: current }">
      <div class="route-stage" :class="{ backwards: current.meta.backwards }">
        <Transition name="route" @before-leave="element => element.setAttribute('inert', '')">
          <div v-if="Component" :key="current.matched[0]?.path" class="route-panel">
            <component :is="Component" />
          </div>
        </Transition>
      </div>
    </RouterView>
  </main>
  <SiteFooter />
</template>
