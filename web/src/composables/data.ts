import { inject, ref, type InjectionKey } from "vue";

export type JsonLoader = <T>(path: string) => T | Promise<T>;

export interface SsrDataContext {
  readJson: JsonLoader;
  preloaded: Record<string, unknown>;
}

export const SSR_DATA_KEY: InjectionKey<SsrDataContext> = Symbol("ssr-data");

const jsonCache = new Map<string, unknown>();
const inflight = new Map<string, Promise<unknown>>();
let clientPreload: Record<string, unknown> = {};

if (typeof window !== "undefined") {
  const embedded = (window as Window & { __PRELOADED_DATA__?: Record<string, unknown> }).__PRELOADED_DATA__;
  if (embedded && typeof embedded === "object") {
    clientPreload = embedded;
  }
}

export function getPreloadedSlice<T>(key: string, context?: SsrDataContext | null): T | undefined {
  if (context && key in context.preloaded) {
    return context.preloaded[key] as T;
  }
  if (key in clientPreload) {
    return clientPreload[key] as T;
  }
  return undefined;
}

export function setPreloadedSlice(key: string, value: unknown, context?: SsrDataContext | null) {
  if (context) {
    context.preloaded[key] = value;
  } else {
    clientPreload[key] = value;
  }
}

export function useSsrDataContext(): SsrDataContext | null {
  return inject(SSR_DATA_KEY, null);
}

export function getCachedJson<T>(path: string): T | undefined {
  return jsonCache.get(path) as T | undefined;
}

export async function loadJson<T>(path: string, context?: SsrDataContext | null): Promise<T> {
  if (context) {
    return await context.readJson<T>(path);
  }
  if (jsonCache.has(path)) {
    return jsonCache.get(path) as T;
  }
  const existing = inflight.get(path);
  if (existing) {
    return existing as Promise<T>;
  }
  const promise = fetch(`${import.meta.env.BASE_URL}data/${path}`)
    .then(async (response) => {
      if (!response.ok) throw new Error(`读取 ${path} 失败（HTTP ${response.status}）`);
      const data = (await response.json()) as T;
      jsonCache.set(path, data);
      return data;
    })
    .finally(() => {
      inflight.delete(path);
    });
  inflight.set(path, promise);
  return promise;
}

// The data package's preview flag, shown on the home page.
export interface SiteInfo {
  schemaVersion: number;
  preview: boolean;
}
export const siteInfo = ref<SiteInfo | null>(null);

export async function loadSiteInfo(context?: SsrDataContext | null) {
  if (siteInfo.value) return siteInfo.value;
  const cached = getPreloadedSlice<SiteInfo>("site.json", context);
  if (cached) {
    siteInfo.value = cached;
    return cached;
  }
  const info = await loadJson<SiteInfo>("site.json", context);
  siteInfo.value = info;
  if (context) {
    setPreloadedSlice("site.json", info, context);
  }
  return info;
}

if (typeof window !== "undefined") {
  const preloadedSite = getPreloadedSlice<SiteInfo>("site.json");
  if (preloadedSite) {
    siteInfo.value = preloadedSite;
  } else {
    loadSiteInfo().catch((error) => console.error(error));
  }
}
