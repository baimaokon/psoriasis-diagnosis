/**
 * store/modules/session.js — 用户会话状态模块
 * ────────────────────────────────────────────
 * 职责：管理双角色（普通用户/管理员）登录态：
 *   - 登录时存储 token + user 到 localStorage
 *   - 支持角色切换（普通用户 ↔ 管理员使用独立 session key）
 *   - 页面刷新时自动从 localStorage 恢复登录态
 * 被调方：
 *   router/index.js → 路由守卫检查 hasRoleSession()
 *   components/UserLayout.vue → 显示用户名、登出操作
 *   components/AdminLayout.vue → 显示管理员名、登出操作
 *   views/user/Login.vue → 登录成功后写入 session
 *   views/admin/Login.vue → 管理员登录成功后写入 session
 */
import { defineStore } from "pinia";
import {
  clearAuth,
  clearRoleAuth,
  getActiveRole,
  getRole,
  getToken,
  getUser,
  hasRoleSession,
  setActiveRole,
  setRole,
  setToken,
  setUser,
} from "@/utils/auth";

export const useSessionStore = defineStore("session", {
  state: () => ({
    token: getToken(),
    role: getActiveRole(),
    user: getUser(),
  }),
  getters: {
    isUserLoggedIn: (state) => state.role === "0" && !!state.token,
    isAdminLoggedIn: (state) => state.role === "1" && !!state.token,
    currentRole: (state) => state.role,
  },
  actions: {
    setSession(token, user) {
      const role = String(user?.role ?? "");
      this.token = token;
      this.role = role;
      this.user = user || null;
      setToken(token, role);
      setRole(role);
      setUser(user, role);
      setActiveRole(role);
    },
    switchRole(role) {
      role = String(role);
      if (!hasRoleSession(role)) {
        return false;
      }
      const token = getToken(role);
      const user = getUser(role);
      this.token = token;
      this.role = role;
      this.user = user || null;
      setActiveRole(role);
      return true;
    },
    logoutCurrentRole() {
      clearRoleAuth(this.role);
      const otherRole = this.role === "0" ? "1" : "0";
      if (hasRoleSession(otherRole)) {
        return this.switchRole(otherRole);
      } else {
        this.clearSession();
        return false;
      }
    },
    logoutAll() {
      this.clearSession();
    },
    clearSession() {
      this.token = "";
      this.role = "";
      this.user = null;
      clearAuth();
    },
    initSession() {
      const activeRole = getActiveRole();
      if (hasRoleSession(activeRole)) {
        this.token = getToken(activeRole);
        this.role = activeRole;
        this.user = getUser(activeRole);
      }
    },
  },
});
