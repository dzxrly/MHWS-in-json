import { inject, toValue, watchEffect, type InjectionKey, type MaybeRefOrGetter } from "vue";
import { useRoute, useRouter, type RouteLocationNormalized, type Router } from "vue-router";
import { OG_IMAGE_PATH, SITE_DESCRIPTION, SITE_ORIGIN, SITE_TITLE } from "../seo/config";
import type { BreadcrumbItem, SeoMeta } from "../seo/types";

export interface SeoContext {
  readMeta?: () => SeoMeta;
}

export const SEO_CONTEXT_KEY: InjectionKey<SeoContext> = Symbol("seo-context");

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeJsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

export function buildAbsoluteUrl(path: string): string {
  return `${SITE_ORIGIN}${path}`;
}

function buildBreadcrumbJsonLd(items: BreadcrumbItem[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: buildAbsoluteUrl(item.path),
    })),
  };
}

function buildSeoJsonLd(meta: SeoMeta): Record<string, unknown>[] {
  const blocks: Record<string, unknown>[] = [];
  if (meta.breadcrumbs?.length) {
    blocks.push(buildBreadcrumbJsonLd(meta.breadcrumbs));
  }
  if (meta.jsonLd?.length) {
    blocks.push(...meta.jsonLd);
  }
  return blocks;
}

export function buildHeadTags(meta: SeoMeta): string {
  const canonicalUrl = buildAbsoluteUrl(meta.canonicalPath);
  const ogImageUrl = buildAbsoluteUrl(OG_IMAGE_PATH);
  const robots = meta.indexable === false ? "noindex, follow" : "index, follow";
  const ogType = meta.ogType ?? "website";
  const lines = [
    `<title>${escapeHtml(meta.title)}</title>`,
    `<meta name="description" content="${escapeHtml(meta.description)}" />`,
    `<meta name="robots" content="${robots}" />`,
    `<link rel="canonical" href="${escapeHtml(canonicalUrl)}" />`,
    `<meta property="og:type" content="${ogType}" />`,
    `<meta property="og:site_name" content="${escapeHtml(SITE_TITLE)}" />`,
    `<meta property="og:locale" content="zh_CN" />`,
    `<meta property="og:title" content="${escapeHtml(meta.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(meta.description)}" />`,
    `<meta property="og:url" content="${escapeHtml(canonicalUrl)}" />`,
    `<meta property="og:image" content="${escapeHtml(ogImageUrl)}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtml(meta.title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(meta.description)}" />`,
    `<meta name="twitter:image" content="${escapeHtml(ogImageUrl)}" />`,
  ];
  for (const block of buildSeoJsonLd(meta)) {
    lines.push(`<script type="application/ld+json" data-seo-ld="1">${escapeJsonLd(block)}</script>`);
  }
  return lines.join("\n    ");
}

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attr, key);
    document.head.appendChild(element);
  }
  element.content = content;
}

function upsertCanonical(href: string) {
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "canonical";
    document.head.appendChild(link);
  }
  link.href = href;
}

export function applySeoMeta(meta: SeoMeta) {
  if (typeof document === "undefined") return;
  const canonicalUrl = buildAbsoluteUrl(meta.canonicalPath);
  const ogImageUrl = buildAbsoluteUrl(OG_IMAGE_PATH);
  document.title = meta.title;
  upsertMeta("name", "description", meta.description);
  upsertMeta("name", "robots", meta.indexable === false ? "noindex, follow" : "index, follow");
  upsertCanonical(canonicalUrl);
  upsertMeta("property", "og:type", meta.ogType ?? "website");
  upsertMeta("property", "og:site_name", SITE_TITLE);
  upsertMeta("property", "og:locale", "zh_CN");
  upsertMeta("property", "og:title", meta.title);
  upsertMeta("property", "og:description", meta.description);
  upsertMeta("property", "og:url", canonicalUrl);
  upsertMeta("property", "og:image", ogImageUrl);
  upsertMeta("name", "twitter:card", "summary_large_image");
  upsertMeta("name", "twitter:title", meta.title);
  upsertMeta("name", "twitter:description", meta.description);
  upsertMeta("name", "twitter:image", ogImageUrl);

  for (const existing of document.head.querySelectorAll('script[data-seo-ld="1"]')) {
    existing.remove();
  }
  for (const block of buildSeoJsonLd(meta)) {
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.dataset.seoLd = "1";
    script.textContent = JSON.stringify(block);
    document.head.appendChild(script);
  }
}

export function routeSeoMeta(router: Router, route: RouteLocationNormalized): SeoMeta {
  const site = route.meta.site;
  const title = route.meta.title ?? site?.title;
  const breadcrumbs: BreadcrumbItem[] = [{ name: "首页", path: "/" }];
  if (site) breadcrumbs.push({ name: site.title, path: site.path });
  const path = route.name ? router.resolve({ name: route.name, params: route.params }).path : route.path;
  const canonicalPath = site && path.replace(/\/$/, "") === site.path.replace(/\/$/, "") ? site.path : path;
  return {
    title: title ? `${title} · ${SITE_TITLE}` : SITE_TITLE,
    description: site?.description ?? SITE_DESCRIPTION,
    canonicalPath,
    indexable: route.meta.indexable ?? true,
    breadcrumbs,
  };
}

export function useSeoMeta(source: MaybeRefOrGetter<Partial<SeoMeta> & { breadcrumbName?: string }>) {
  const route = useRoute();
  const router = useRouter();
  const context = inject(SEO_CONTEXT_KEY, null);
  const readMeta = () => {
    const { breadcrumbName, ...overrides } = toValue(source);
    const meta = { ...routeSeoMeta(router, route), ...overrides };
    if (breadcrumbName) {
      meta.breadcrumbs?.push({ name: breadcrumbName, path: meta.canonicalPath });
    }
    return meta;
  };
  if (context) {
    context.readMeta = readMeta;
  } else if (typeof document !== "undefined") {
    watchEffect(() => applySeoMeta(readMeta()));
  }
}
