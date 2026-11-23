import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";
import "./styles/tokens.css";
import "./styles/background.css";
import "./styles/layout.css";

const app = createApp(App).use(router);
void router.isReady().then(() => app.mount("#app"));
