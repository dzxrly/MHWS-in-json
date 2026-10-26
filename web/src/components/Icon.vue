<script setup>
// Outlined 24 px icons drawn with one stroke, as on eggtargaryen.com's blog.
defineProps({ name: { type: String, required: true } });
const paths = {
  sun: "M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  moon: "M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14Z",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "m6 6 12 12M6 18 18 6",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  back: "M19 12H5m6-6-6 6 6 6",
  external: "M14 3h7v7m0-7L10 14M10 3H3v18h18v-7",
  search: "m20 20-4.2-4.2M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14Z",
  tree: "M4 4h6v4H4zM14 10h6v4h-6zM14 17h6v4h-6zM7 8v11h7M7 12h7",
  skill: "M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9ZM19 16v4m-2-2h4",
  github:
    "M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4M9 18c-4.51 2-5-2-7-2",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  fit: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  unfold: "M12 3v6m-3-3 3 3 3-3M12 21v-6m-3 3 3-3 3 3M4 12h16",
  fold: "M12 9V3m-3 3 3-3 3 3M12 15v6m-3-3 3 3 3-3M4 12h16",
  download: "M12 4v11m0 0-4-4m4 4 4-4M5 20h14",
  panel: "M4 5h16v14H4zM15 5v14",
  flow: "M4 4h6v5H4zM14 15h6v5h-6zM7 9v4a2 2 0 0 0 2 2h5",
  tune: "M4 7h10M18 7h2M4 17h4M12 17h8M16 4v6M10 14v6",
  info: "M12 16v-5M12 8h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  target: "M12 3v4M12 17v4M3 12h4M17 12h4M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
  archive: "M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
};
</script>

<template>
  <svg
    class="icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name]" />
  </svg>
</template>
