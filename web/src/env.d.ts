declare const __BUILD__: { date: string; commit: string };
declare const __SITE_ORIGIN__: string;

interface Window {
  __PRELOADED_DATA__?: Record<string, unknown>;
}
