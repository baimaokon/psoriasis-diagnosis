/**
 * router/index.js — Vue Router 路由定义 + 全局导航守卫
 * ─────────────────────────────────────────────────────
 * 职责：
 *   1. 定义全站路由表：用户端 /user/* 和管理端 /admin/* 两套布局
 *   2. 全局 beforeEach 守卫实现双角色认证隔离：
 *      - role=0（普通用户）→ 仅可访问 /user/* 路由
 *      - role=1（管理员）  → 仅可访问 /admin/* 路由
 *      - 两个角色拥有独立的 session 空间
 *   3. 路由懒加载（动态 import），按需分chunk加载页面组件
 * 依赖：
 *   utils/auth.js → getActiveRole(), hasRoleSession(), getToken()
 *   components/UserLayout.vue → 用户端布局（导航栏+内容区）
 *   components/AdminLayout.vue → 管理端布局（侧边栏+内容区）
 *   views/user/*.vue → 用户端页面组件
 *   views/admin/*.vue → 管理端页面组件
 *   store/modules/session.js → 登录态持久化
 */
import { createRouter, createWebHistory } from "vue-router";
import { getActiveRole, getToken, hasRoleSession } from "@/utils/auth";

const UserLayout = () => import("@/components/UserLayout.vue");
const AdminLayout = () => import("@/components/AdminLayout.vue");

const routes = [
  { path: "/login", component: () => import("@/views/user/Login.vue") },
  { path: "/register", component: () => import("@/views/user/Register.vue") },
  { path: "/admin/login", component: () => import("@/views/admin/Login.vue") },
  {
    path: "/user",
    component: UserLayout,
    meta: { requiresAuth: true, role: "0" },
    children: [
      { path: "diagnose", component: () => import("@/views/user/Diagnose.vue") },
      { path: "records", component: () => import("@/views/user/Records.vue") },
      { path: "profile", component: () => import("@/views/user/Profile.vue") },
      { path: "", redirect: "/user/diagnose" },
    ],
  },
  {
    path: "/admin",
    component: AdminLayout,
    meta: { requiresAuth: true, role: "1" },
    children: [
      { path: "dashboard", component: () => import("@/views/admin/Dashboard.vue") },
      { path: "", redirect: "/admin/dashboard" },
    ],
  },
  { path: "/", redirect: "/login" },
  { path: "/:pathMatch(.*)*", redirect: "/login" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 全局路由守卫：实现用户端/管理端的双角色认证隔离
// 角色 0 = 普通用户，角色 1 = 管理员，各自拥有独立的 session 与 token
router.beforeEach((to, _from, next) => {
  const requiredRole = to.meta?.role;

  if (to.meta?.requiresAuth && requiredRole) {
    const hasSession = hasRoleSession(requiredRole);
    
    if (!hasSession) {
      if (requiredRole === "1") return next("/admin/login");
      return next("/login");
    }
    
    const activeRole = getActiveRole();
    if (activeRole !== requiredRole) {
      // 🔑 关键修复：已有会话则直接放行，避免重复 next() 导致死循环
      // 角色状态同步交给业务组件或 Store 在路由进入后处理
      if (hasRoleSession(requiredRole)) {
        return next();
      }
      // 如果没有该角色的session，重定向到对应的登录页
      if (requiredRole === "1") return next("/admin/login");
      return next("/login");
    }
  }

  if (to.path === "/login" && hasRoleSession("0")) {
    return next("/user/diagnose");
  }
  
  if (to.path === "/admin/login" && hasRoleSession("1")) {
    return next("/admin/dashboard");
  }

  return next();
});

export default router;
