/**
 * main.js — Vue3 应用入口
 * ────────────────────────
 * 职责：创建 Vue 应用实例，注册所有插件，挂载到 #app。
 * 初始化顺序：Pinia(状态管理) → Vue Router(路由) → Element Plus(UI) → App 根组件
 * 被 index.html 通过 <script type="module" src="/src/main.js"> 加载。
 * 连接关系：
 *   store/index.js → Pinia 全局状态
 *   router/index.js → Vue Router 路由定义+守卫
 *   App.vue → 根组件（仅含 <router-view>）
 */
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
