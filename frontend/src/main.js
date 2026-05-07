import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import * as ElementPlusIconsVue from "@element-plus/icons-vue";

import App from "./App.vue";
import router from "@/router";
import pinia from "@/store";
import { useSessionStore } from "@/store/modules/session";
import "@/styles/global.css";

const app = createApp(App);

app.use(pinia);

const sessionStore = useSessionStore();
sessionStore.initSession();

app.use(router);
app.use(ElementPlus);

Object.entries(ElementPlusIconsVue).forEach(([name, component]) => {
  app.component(name, component);
});

app.mount("#app");
