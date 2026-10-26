import { ref } from "vue";

// The JSON interface written by `python -m src.site_data`, served at /data.
export async function loadJson(path) {
  const response = await fetch(`${import.meta.env.BASE_URL}data/${path}`);
  if (!response.ok) throw new Error(`读取 ${path} 失败（HTTP ${response.status}）`);
  return response.json();
}

// The data package's preview flag, shown on the home page.
export const siteInfo = ref(null);
loadJson("site.json").then(
  (info) => (siteInfo.value = info),
  (error) => console.error(error),
);
