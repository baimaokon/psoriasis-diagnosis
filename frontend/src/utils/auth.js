// 双角色 session 管理：用户端(0)和管理端(1)的 token/用户信息独立存储
// 同一浏览器可同时持有两个角色的登录态，通过 activeRole 切换
const TOKEN_KEYS = {
  '0': 'psoriasis_user_token',
  '1': 'psoriasis_admin_token'
};
const ROLE_KEY = 'psoriasis_role';
const USER_KEYS = {
  '0': 'psoriasis_user_info',
  '1': 'psoriasis_admin_info'
};
const ACTIVE_ROLE_KEY = 'psoriasis_active_role';

export const getToken = (role) => {
  if (role !== undefined) {
    return localStorage.getItem(TOKEN_KEYS[role]) || "";
  }
  const activeRole = getActiveRole();
  return localStorage.getItem(TOKEN_KEYS[activeRole]) || "";
};

export const setToken = (token, role) => {
  if (role === undefined) {
    role = getActiveRole();
  }
  localStorage.setItem(TOKEN_KEYS[role], token);
};

export const removeToken = (role) => {
  if (role !== undefined) {
    localStorage.removeItem(TOKEN_KEYS[role]);
  } else {
    Object.values(TOKEN_KEYS).forEach(key => localStorage.removeItem(key));
  }
};

export const getRole = () => localStorage.getItem(ROLE_KEY) || "";

export const setRole = (role) => localStorage.setItem(ROLE_KEY, String(role));

export const removeRole = () => localStorage.removeItem(ROLE_KEY);

export const getUser = (role) => {
  if (role === undefined) {
    role = getActiveRole();
  }
  const raw = localStorage.getItem(USER_KEYS[role]);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

export const setUser = (user, role) => {
  if (role === undefined) {
    role = getActiveRole();
  }
  localStorage.setItem(USER_KEYS[role], JSON.stringify(user || null));
};

export const removeUser = (role) => {
  if (role !== undefined) {
    localStorage.removeItem(USER_KEYS[role]);
  } else {
    Object.values(USER_KEYS).forEach(key => localStorage.removeItem(key));
  }
};

export const getActiveRole = () => {
  return localStorage.getItem(ACTIVE_ROLE_KEY) || "0";
};

export const setActiveRole = (role) => {
  localStorage.setItem(ACTIVE_ROLE_KEY, String(role));
};

export const clearAuth = () => {
  Object.values(TOKEN_KEYS).forEach(key => localStorage.removeItem(key));
  Object.values(USER_KEYS).forEach(key => localStorage.removeItem(key));
  removeRole();
  localStorage.removeItem(ACTIVE_ROLE_KEY);
};

export const clearRoleAuth = (role) => {
  localStorage.removeItem(TOKEN_KEYS[role]);
  localStorage.removeItem(USER_KEYS[role]);
};

export const hasRoleSession = (role) => {
  return !!localStorage.getItem(TOKEN_KEYS[role]);
};

export const getAllSessions = () => {
  return {
    user: {
      hasSession: hasRoleSession('0'),
      user: getUser('0')
    },
    admin: {
      hasSession: hasRoleSession('1'),
      user: getUser('1')
    }
  };
};

