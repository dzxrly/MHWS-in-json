import { nextTick, onBeforeUnmount, onMounted, reactive, watch } from "vue";

// The page title shown in the header once the page's own heading has
// scrolled under it; `tools` pages also move their search into the header.
export const pageHeader = reactive({ title: "", condensed: false, tools: false });

/**
 * Condense the header while `heading` (a template ref) is out of view.
 * `focusTarget` (optional ref) keeps the moved search field focused.
 */
export function usePageHeader(title, heading, { tools = false, focusTarget } = {}) {
  let observer = null;
  function observe(element) {
    observer?.disconnect();
    if (!element) return;
    const height = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--header-height")) || 88;
    observer = new IntersectionObserver(([entry]) => {
      pageHeader.condensed = !entry.isIntersecting && entry.boundingClientRect.top < height;
    }, { rootMargin: `-${height}px 0px 0px 0px` });
    observer.observe(element);
  }
  onMounted(() => {
    pageHeader.title = title;
    pageHeader.tools = tools;
    pageHeader.condensed = false;
  });
  watch(heading, observe, { flush: "post" });
  if (focusTarget) {
    // Moving a focused input to another parent drops its focus.
    watch(
      () => pageHeader.condensed,
      async () => {
        const input = focusTarget.value;
        if (input !== document.activeElement) return;
        await nextTick();
        input.focus();
      },
      { flush: "pre" },
    );
  }
  onBeforeUnmount(() => {
    observer?.disconnect();
    Object.assign(pageHeader, { title: "", condensed: false, tools: false });
  });
}
