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
