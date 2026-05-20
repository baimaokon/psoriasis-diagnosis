/**
 * api/feedback.js — 反馈 API 封装
 * ───────────────────────────────
 * 对接后端 routes/feedback.py（/api/feedback/*）
 * export: submitFeedback(), getFeedbackStats(), getLabels() 等
 * 被调方：
 *   views/user/Diagnose.vue → 诊断结果纠错
 */
import request from "./request";

export const getLabels = () => request.get("/feedback/labels");

export const submitFeedback = (data) => request.post("/feedback/submit", data);

export const getRecordFeedback = (recordId) =>
  request.get(`/feedback/record/${recordId}`);

export const getMyFeedbackList = (params) =>
  request.get("/feedback/my", { params });

export const batchGetFeedback = (recordIds) =>
  request.get("/feedback/batch", { params: { record_ids: recordIds } });

export const getFeedbackStats = () => request.get("/feedback/stats");
