import request from "./request";

export const register = (payload) => request.post("/auth/register", payload);
export const login = (payload) => request.post("/auth/login", payload);
export const adminLogin = (payload) => request.post("/auth/admin/login", payload);
export const profile = () => request.get("/auth/profile");

