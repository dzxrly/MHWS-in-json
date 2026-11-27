export interface BreadcrumbItem {
  name: string;
  path: string;
}

export interface SeoMeta {
  title: string;
  description: string;
  canonicalPath: string;
  indexable?: boolean;
  ogType?: "website" | "article";
  breadcrumbs?: BreadcrumbItem[];
  jsonLd?: Record<string, unknown>[];
}

export interface RedirectRule {
  from: string;
  to: string;
}
