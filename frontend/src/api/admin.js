/**
 * api/admin.js — 管理端 API 封装
 * ──────────────────────────────
 * 对接后端 routes/admin.py（/api/admin/*）
 * export: getDashboard(), getDatasetSummary(), startTraining(), getModels(),
 *         activateModel(), getSSEStream(), terminateJob(), reviveJob() 等
 * 被调方：
 *   views/admin/Dashboard.vue → 管理端所有功能
 */
import request from "./request";

export const getDashboard = () => request.get("/admin/dashboard");

export function getDatasetSummary(params = {}) {
  return request({
    url: "/admin/dataset/summary",
    method: "get",
    params,
  });
}

export function getClassSamples(className, params = {}) {
  const encodedName = encodeURIComponent(className);
  return request({
    url: `/admin/dataset/classes/${encodedName}/samples`,
    method: "get",
    params,
  });
}

export function getRandomSamples(params = {}) {
  return request({
    url: "/admin/dataset/samples/random",
    method: "get",
    params,
  });
}

export function getDatasetQualityReport(params = {}) {
  return request({
    url: "/admin/dataset/quality-report",
    method: "get",
    params,
    timeout: 300000,  // 质量分析需扫描全量图片，耗时较长
  });
}

export function getDatasetSplitVisualization(params = {}) {
  return request({
    url: "/admin/dataset/split-visualization",
    method: "get",
    params,
  });
}

export const getTrainParamSpec = () => request.get("/admin/train/param-spec");
export const startTrain = (payload) => request.post("/admin/train/start", payload, { timeout: 60000 });
export const getTrainJobs = (params) => request.get("/admin/train/jobs", { params });
export const getTrainJobDetail = (jobId) => request.get(`/admin/train/jobs/${jobId}`);
export const terminateTrainJob = (jobId) => request.post(`/admin/train/jobs/${jobId}/terminate`);
export const reviveTrainJob = (jobId) => request.post(`/admin/train/jobs/${jobId}/revive`);
export const deleteTrainJob = (jobId) => request.delete(`/admin/train/jobs/${jobId}`);
export const getModels = () => request.get("/admin/models");
export const activateModel = (modelId) => request.post(`/admin/models/${modelId}/activate`);
export const deleteModel = (modelId) => request.delete(`/admin/models/${modelId}`);
export const getRecords = (params) => request.get("/admin/records", { params });
export const deleteRecord = (recordId) => request.delete(`/admin/records/${recordId}`);

export const createTrainEventSource = (token) => {
  const safeToken = encodeURIComponent(token || "");
  return new EventSource(`/api/admin/train/stream?token=${safeToken}`);
};
