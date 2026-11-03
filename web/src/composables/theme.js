import { ref } from "vue";

const KEY = "mhws-theme";
const media = matchMedia("(prefers-color-scheme: dark)");

function stored() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

// index.html applies the class before the first paint; this keeps it in sync.
export const isDark = ref(document.documentElement.classList.contains("dark"));

function apply(dark) {
  isDark.value = dark;
  document.documentElement.classList.toggle("dark", dark);
}

media.addEventListener("change", (event) => {
  if (!stored()) apply(event.matches);
});

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
export function toggleTheme(event) {
  const root = document.documentElement;
  if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) {
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
