<script setup>
/* global __BUILD__ */
// Date and commit of this build, set by vite.config.js.
const build = __BUILD__;
const commitUrl = `https://github.com/dzxrly/MHWS-in-json/commit/${build.commit}`;
</script>

<template>
  <footer class="site-footer">
    <span
      >部署日期：{{ build.date
      }}<template v-if="build.commit"
        >（<a :href="commitUrl" target="_blank" rel="noopener noreferrer">{{ build.commit.slice(0, 7) }}</a
        >）</template
      ></span
    >
  </footer>
</template>
