import { onBeforeUnmount, onMounted } from "vue";

// A single listener also covers the menus teleported to document.body.
export function useControlRipple() {
  const controls = ".card-link, .nav-option, .chip, .icon-button, .filled-button, .tonal-button, .text-button, .outlined-button, .site-select";
  let reduced: MediaQueryList | null = null;
  function ripple(event: MouseEvent) {
    if (reduced?.matches || !(event.target instanceof Element)) return;
    const control = event.target.closest<HTMLElement>(controls);
    if (!control || control.matches(":disabled")) return;
    const box = control.getBoundingClientRect();
    const x = event.detail ? event.clientX - box.left : box.width / 2;
    const y = event.detail ? event.clientY - box.top : box.height / 2;
    const radius = Math.hypot(Math.max(x, box.width - x), Math.max(y, box.height - y));
    const layer = document.createElement("span");
    layer.className = "control-ripple";
    layer.ariaHidden = "true";
    layer.style.setProperty("--x", `${x}px`);
    layer.style.setProperty("--y", `${y}px`);
    layer.style.setProperty("--diameter", `${2 * radius}px`);
    layer.addEventListener("animationend", () => layer.remove(), { once: true });
    control.append(layer);
  }
  onMounted(() => {
    reduced = matchMedia("(prefers-reduced-motion: reduce)");
    document.addEventListener("click", ripple, true);
  });
  onBeforeUnmount(() => document.removeEventListener("click", ripple, true));
}
