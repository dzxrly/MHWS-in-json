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

export function toggleTheme() {
  apply(!isDark.value);
  try {
    localStorage.setItem(KEY, isDark.value ? "dark" : "light");
  } catch {
    // The choice simply lasts for this page view.
  }
}
