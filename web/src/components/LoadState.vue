<script setup>
defineProps({ error: { type: [Error, null], default: null }, label: { type: String, default: "正在加载数据…" } });
</script>

<template>
  <div class="state-panel" role="status">
    <template v-if="error">
      <p>数据加载失败：{{ error.message }}</p>
      <button class="tonal-button" type="button" @click="$router.go(0)">重新加载</button>
    </template>
    <template v-else>
      <div class="progress" aria-hidden="true" />
      <p>{{ label }}</p>
    </template>
  </div>
</template>
