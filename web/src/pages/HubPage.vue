<script setup lang="ts">
import Icon from "../components/Icon.vue";
import SiteCard from "../components/SiteCard.vue";
import { siteInfo } from "../composables/data";
import { sites } from "../sites";

const RELEASES = "https://github.com/dzxrly/MHWS-in-json/releases/latest";
</script>

<template>
  <div class="page hub">
    <h1 class="hero">怪物猎人：荒野 数据站</h1>
    <ul class="site-grid">
      <li v-for="site in sites" :key="site.id">
        <SiteCard class="site-card" :to="site.path">
          <span class="site-icon"><Icon :name="site.icon" /></span>
          <span class="site-text">
            <h2 class="card-title">{{ site.title }}</h2>
            <p>{{ site.description }}</p>
          </span>
          <span class="card-arrow" aria-hidden="true"><Icon name="arrow" /></span>
        </SiteCard>
      </li>
      <li>
        <SiteCard class="site-card" :href="RELEASES" target="_blank" rel="noopener noreferrer">
          <span class="site-icon"><Icon name="archive" /></span>
          <span class="site-text">
            <h2 class="card-title">完整数据下载</h2>
            <p>各语言数据库表格、整理数据与源 JSON。</p>
          </span>
          <span class="card-arrow" aria-hidden="true"><Icon name="external" /></span>
        </SiteCard>
      </li>
    </ul>
    <p v-if="siteInfo?.preview" class="preview-note">这是研究预览：怪物行动逻辑只包含部分怪物，不是正式发布的数据。</p>
  </div>
</template>

<style scoped>
.hub {
  padding-top: 24px;
}
.hero {
  margin: 0 8px 32px;
  font-size: clamp(30px, 4.5vw, 44px);
  font-weight: 750;
  letter-spacing: -1.2px;
  line-height: 1.25;
}
.site-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
.site-card {
  height: 100%;
  flex-direction: row;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
}
.site-icon {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--shape-l);
  background: var(--primary-container);
  color: var(--on-primary-container);
  transition:
    border-radius var(--dur-spring) var(--spring),
    transform var(--dur-spring) var(--spring);
}
/* The icon's container morphs from a rounded square into a circle. */
@media (hover: hover) {
  .site-card:hover .site-icon {
    border-radius: 50%;
    transform: rotate(-8deg);
  }
}
.site-text {
  flex: 1;
  min-width: 0;
}
.site-card p {
  margin-top: 2px;
  color: var(--on-surface-variant);
  font-size: 0.875rem;
  line-height: 1.75;
}
.preview-note {
  margin-top: 24px;
  padding: 14px 22px;
  background: var(--error-container);
  color: var(--on-error-container);
  border-radius: 20px;
}
@media (max-width: 479px) {
  .hub {
    padding-top: 8px;
  }
  .hero {
    margin: 0 4px 24px;
  }
  .site-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
}
</style>
