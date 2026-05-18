import axios from "axios";
import { ElMessage } from "element-plus";
import { getToken, removeToken, getActiveRole, clearRoleAuth } from "@/utils/auth";

const request = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

// 请求拦截器：自动附加 JWT Token 到每个请求头
request.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：统一处理后端返回的 JSON 格式，解包 data 字段
// 后端统一返回 {code: 0, message: '...', data: ...} 或 {success: true/false, ...}
request.interceptors.response.use(
  (response) => {
    const payload = response.data;

    if (payload && typeof payload === "object") {
      if ("code" in payload) {
        // code !== 0 表示业务错误
        if (payload.code !== 0 && payload.code !== 200) {
          ElMessage.error(payload.message || "请求失败");
          return Promise.reject(payload);
        }
        return { data: payload.data, message: payload.message, code: payload.code };
      }
      if ("success" in payload) {
        if (payload.success === false) {
          ElMessage.error(payload.message || "请求失败");
          return Promise.reject(payload);
        }
        return { data: payload.data, message: payload.message };
      }
    }
    
    // 其他情况直接返回
    return payload;
  },
  (error) => {
    // HTTP 错误统一处理：401 清除登录态并跳转，403/404/500 提示用户
    if (error.response) {
      const status = error.response.status;
      const message = error.response.data?.message || error.message;

      switch (status) {
        case 401:
          ElMessage.error(message || "登录已过期，请重新登录");
          if (error.config && (error.config.url === "/auth/login" || error.config.url === "/auth/admin/login")) {
            break;
          }
          const activeRole = getActiveRole();
          clearRoleAuth(activeRole);
          if (activeRole === "0") {
            window.location.href = "/login";
          } else {
            window.location.href = "/admin/login";
          }
          break;
        case 403:
          ElMessage.error("权限不足");
          break;
        case 404:
          ElMessage.error("请求的资源不存在");
          break;
        case 500:
          ElMessage.error("服务器内部错误");
          break;
        default:
          ElMessage.error(message || "网络错误，请稍后重试");
      }
    } else if (error.message === "Network Error") {
      ElMessage.error("网络连接失败，请检查服务器是否运行");
    } else {
      ElMessage.error(error.message || "网络错误，请稍后重试");
    }
    
    return Promise.reject(error);
  },
);

export default request;
