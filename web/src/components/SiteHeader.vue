<script setup>
import Icon from "./Icon.vue";
import { isDark, toggleTheme } from "../composables/theme.js";
import { pageHeader } from "../composables/page_header.js";

// The information sites are reached from the home page, not from the header.
defineProps({ wide: Boolean });
</script>

<template>
  <header class="site-header" :class="{ wide, condensed: pageHeader.condensed, tools: pageHeader.tools }">
    <div class="header-inner">
      <RouterLink class="site-brand" to="/" aria-label="MHWS 数据站，首页">
        <span class="brand-name">MHWS 数据站</span>
      </RouterLink>
      <div class="header-center">
        <span class="header-title" :aria-hidden="!pageHeader.condensed">{{ pageHeader.title }}</span>
        <!-- Pages teleport their search here while condensed. -->
        <div id="header-tools" class="header-tools" />
      </div>
      <div class="header-actions">
        <a
          class="icon-button standard"
          href="https://github.com/dzxrly/MHWS-in-json"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="GitHub 仓库"
          ><Icon name="github"
        /></a>
        <button
          class="icon-button"
          type="button"
          :aria-label="isDark ? '切换到浅色主题' : '切换到深色主题'"
          @click="toggleTheme"
        >
          <Icon :name="isDark ? 'sun' : 'moon'" />
        </button>
      </div>
    </div>
  </header>
</template>
