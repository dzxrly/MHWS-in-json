<script setup lang="ts">
// Date and commit of this build, set by Vite.
const build = __BUILD__;
const repository = "https://github.com/dzxrly/MHWS-in-json";
</script>

<template>
  <footer class="site-footer">
    <span class="footer-links">
      <a :href="`${repository}/blob/main/LICENSE`">LICENSE</a>
      <span aria-hidden="true">·</span>
      <a href="https://eggtargaryen.com/">By Egg Targaryen</a>
    </span>
    <span>部署日期：{{ build.date }}<template v-if="build.commit">（<a
      :href="`${repository}/commit/${build.commit}`" target="_blank" rel="noopener noreferrer"
    >{{ build.commit.slice(0, 7) }}</a>）</template></span>
  </footer>
</template>
