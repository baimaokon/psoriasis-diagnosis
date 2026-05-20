/**
 * api/auth.js — 认证 API 封装
 * ───────────────────────────
 * 对接后端 routes/auth.py（/api/auth/*）
 * export: login(), register(), adminLogin(), getProfile()
 * 被调方：
 *   views/user/Login.vue → 普通用户登录
 *   views/user/Register.vue → 用户注册
 *   views/admin/Login.vue → 管理员登录
 */
import request from "./request";

export const register = (payload) => request.post("/auth/register", payload);
export const login = (payload) => request.post("/auth/login", payload);
export const adminLogin = (payload) => request.post("/auth/admin/login", payload);
export const profile = () => request.get("/auth/profile");

