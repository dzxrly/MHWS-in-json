import { createApp, createSSRApp } from "vue";
import App from "./App.vue";
import { router } from "./router";
import { legacySkillLocation } from "./sites/skill_details";
import "./styles/tokens.css";
import "./styles/background.css";
import "./styles/layout.css";

const legacySkill = legacySkillLocation(router.resolve(router.options.history.location));
if (legacySkill) {
  window.location.replace(router.resolve(legacySkill).href);
} else {
  const root = document.getElementById("app");
  const app = (root?.dataset.ssr === "1" ? createSSRApp(App) : createApp(App)).use(router);
  void router.isReady().then(() => app.mount("#app"));
}
