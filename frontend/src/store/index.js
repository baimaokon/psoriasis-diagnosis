/**
 * store/index.js — Pinia 全局状态管理
 * ───────────────────────────────────
 * 职责：创建 Pinia 实例，在 main.js 中通过 app.use(pinia) 注册。
 * 模块：
 *   store/modules/session.js → 用户登录态管理（token存储、角色切换、自动恢复）
 */
import { createPinia } from "pinia";

const pinia = createPinia();

export default pinia;

