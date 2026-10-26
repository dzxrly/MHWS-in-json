<script setup>
import { computed } from "vue";
import { siteInfo } from "../composables/data.js";

const commitUrl = computed(
  () => siteInfo.value && `https://github.com/${siteInfo.value.repository}/commit/${siteInfo.value.commit}`,
);
</script>

<template>
  <footer class="site-footer">
    <span v-if="siteInfo"
      >部署日期：{{ siteInfo.builtOn }}（<a :href="commitUrl" target="_blank" rel="noopener noreferrer">{{
        siteInfo.commit.slice(0, 7)
      }}</a
      >）</span
    >
  </footer>
</template>
