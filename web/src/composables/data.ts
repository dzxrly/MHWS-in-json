import { ref } from "vue";

// The JSON interface written by `python -m src.site_data`, served at /data.
export async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/${path}`);
  if (!response.ok) throw new Error(`读取 ${path} 失败（HTTP ${response.status}）`);
  return response.json();
}

// The data package's preview flag, shown on the home page.
interface SiteInfo { schemaVersion: number; preview: boolean }
export const siteInfo = ref<SiteInfo | null>(null);
loadJson<SiteInfo>("site.json").then(
  (info) => (siteInfo.value = info),
  (error) => console.error(error),
);
