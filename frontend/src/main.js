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
// 按需导入图标（仅注册项目实际使用的 ~50 个，避免全量 200+ 图标增加构建体积）
import
{
  Aim, ArrowDown, ArrowRight, Back, Box, Calendar, ChatLineSquare,
  CircleCheck, CircleCheckFilled, Clock, CloseBold, Cpu, DataAnalysis,
  DataBoard, Delete, Document, Download, EditPen, Folder, Grid, HotWater,
  InfoFilled, List, Loading, Management, Memo, Picture, PictureFilled,
  PieChart, QuestionFilled, Refresh, Search, Select, Setting, Switch,
  Tickets, Tools, TrendCharts, Trophy, Upload, UploadFilled, User,
  UserFilled, VideoCamera, VideoPlay, View, Warning, WarningFilled, ZoomIn,
} from "@element-plus/icons-vue";

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

const icons = {
  Aim, ArrowDown, ArrowRight, Back, Box, Calendar, ChatLineSquare,
  CircleCheck, CircleCheckFilled, Clock, CloseBold, Cpu, DataAnalysis,
  DataBoard, Delete, Document, Download, EditPen, Folder, Grid, HotWater,
  InfoFilled, List, Loading, Management, Memo, Picture, PictureFilled,
  PieChart, QuestionFilled, Refresh, Search, Select, Setting, Switch,
  Tickets, Tools, TrendCharts, Trophy, Upload, UploadFilled, User,
  UserFilled, VideoCamera, VideoPlay, View, Warning, WarningFilled, ZoomIn,
};
Object.entries(icons).forEach(([name, component]) => {
  app.component(name, component);
});

app.mount("#app");
