import { ref } from "vue";

const KEY = "mhws-theme";

function stored() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

// A first visit opens with the main site's blue scheme. Remember an explicit
// theme choice for return visits.
export const isDark = ref(stored() === "dark");
document.documentElement.classList.toggle("dark", isDark.value);

function apply(dark: boolean) {
  isDark.value = dark;
  document.documentElement.classList.toggle("dark", dark);
}

function switchTheme() {
  apply(!isDark.value);
  try {
    localStorage.setItem(KEY, isDark.value ? "dark" : "light");
  } catch {
    // The choice simply lasts for this page view.
  }
}

// Spread the new theme as a circle from the toggle button. Browsers
// without view transitions switch through the colour transitions.
export function toggleTheme(event: MouseEvent) {
  const root = document.documentElement;
  if (!(event.currentTarget instanceof Element) || !document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    switchTheme();
    return;
  }
  const rect = event.currentTarget.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  root.style.setProperty("--reveal-x", `${x}px`);
  root.style.setProperty("--reveal-y", `${y}px`);
  root.style.setProperty("--reveal-r", `${radius}px`);
  root.classList.add("theme-reveal");
  document.startViewTransition(switchTheme).finished.finally(() => root.classList.remove("theme-reveal"));
}
