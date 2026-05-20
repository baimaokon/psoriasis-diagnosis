/**
 * api/user.js — 用户端 API 封装
 * ─────────────────────────────
 * 对接后端 routes/user.py（/api/user/*）
 * export: uploadDiagnose(), batchDiagnose(), getRecords(), downloadReport()
 * 被调方：
 *   views/user/Diagnose.vue → 上传诊断
 *   views/user/Records.vue → 历史记录查询
 */
import request from "./request";

export const diagnose = (formData) =>
  request.post("/user/diagnose", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60000,
  });

export const diagnoseBatch = (formData) =>
  request.post("/user/diagnose/batch", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300000, // 批量诊断耗时较长
  });

export const downloadReport = async (recordId) => {
  const { getToken } = await import("@/utils/auth");
  const token = getToken();
  const response = await fetch(`/api/user/records/${recordId}/report`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error("下载失败");
  }
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const disposition = response.headers.get("content-disposition");
  let filename = `诊断报告_${recordId}.pdf`;
  if (disposition) {
    const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    if (match && match[1]) {
      filename = decodeURIComponent(match[1].replace(/['"]/g, ""));
    }
  }
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

export const myRecords = (params) => request.get("/user/records", { params });

