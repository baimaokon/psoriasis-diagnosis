<!--
Records.vue — 用户端诊断历史记录页
───────────────────────────────────
路由：/user/records
功能：
  - 按时间倒序展示所有历史诊断记录列表
  - 支持按疾病类型、日期范围、最低置信度筛选
  - 点击记录可查看详情（原图+热力图+完整预测结果）
  - 可下载 PDF 诊断报告
API对接：api/user.js → getRecords()、downloadReport()
后端对接：routes/user.py → GET /api/user/records、/api/user/records/<id>/report
-->
<template>
  <div class="records-container">
    <el-card class="records-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon :size="20" color="#409eff"><Clock /></el-icon>
            <span class="header-title">历史诊断记录</span>
          </div>
        </div>
      </template>

      <!-- 新增筛选栏 -->
      <el-form :model="filters" inline class="filter-bar">
        <el-form-item label="日期范围">
          <el-date-picker v-model="filters.dateRange" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="病种">
          <el-input v-model="filters.disease" placeholder="输入病名关键词" clearable />
        </el-form-item>
        <el-form-item label="最低置信度">
          <el-slider v-model="filters.minConf" :min="0" :max="100" show-input size="small" style="width: 160px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData"><el-icon><Search /></el-icon> 查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="list" border stripe :header-cell-style="{ background: '#f5f7fa', fontWeight: '600' }">
        <el-table-column type="index" label="#" width="60" align="center" />
        <el-table-column prop="created_at" label="诊断时间" width="180">
          <template #default="{ row }">
            <div class="time-cell"><el-icon><Calendar /></el-icon><span>{{ row.created_at }}</span></div>
          </template>
        </el-table-column>
        <el-table-column prop="predicted_label_zh" label="中文病名" min-width="150">
          <template #default="{ row }"><span class="diagnosis-text">{{ row.predicted_label_zh }}</span></template>
        </el-table-column>
        <el-table-column prop="predicted_label_en" label="英文类别" min-width="240" show-overflow-tooltip />
        <el-table-column label="反馈" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="feedbackMap[row.id]?.has_feedback" :type="feedbackMap[row.id].is_correct ? 'success' : 'warning'" effect="plain" size="small">
              <el-icon :size="12"><component :is="feedbackMap[row.id].is_correct ? 'Select' : 'Warning'" /></el-icon>
              {{ feedbackMap[row.id].is_correct ? '正确' : '已纠错' }}
            </el-tag>
            <span v-else class="no-feedback">未反馈</span>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="160" align="center">
          <template #default="{ row }">
            <el-progress :percentage="parseFloat((row.confidence * 100).toFixed(2))" :color="getConfidenceColor(row.confidence)" :stroke-width="12" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" align="center">
          <template #default="{ row }">
            <el-link :href="row.image_url" target="_blank" type="primary" :underline="false">
              <el-icon><View /></el-icon> 原图
            </el-link>
            <el-divider direction="vertical" />
            <el-link :href="row.heatmap_url" target="_blank" type="success" :underline="false">
              <el-icon><View /></el-icon> 热力图
            </el-link>
            <el-divider direction="vertical" />
            <el-link type="warning" :underline="false" @click="exportRecord(row)">
              <el-icon><Download /></el-icon> 报告
            </el-link>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.limit" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" background @size-change="loadData" @current-change="handlePageChange" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Clock, Calendar, View, Search, Select, Warning, Download } from '@element-plus/icons-vue';
import { downloadReport, myRecords } from "@/api/user";
import { batchGetFeedback } from "@/api/feedback";

const list = ref([]);
const total = ref(0);
const loading = ref(false);
const query = reactive({ page: 1, limit: 20 });
const filters = reactive({ dateRange: null, disease: '', minConf: 0 });
const feedbackMap = ref({});

const getConfidenceColor = (c) => c >= 0.9 ? '#67c23a' : c >= 0.7 ? '#e6a23c' : '#f56c6c';

const loadData = async () => {
  loading.value = true;
  try {
    const params = { ...query };
    if (filters.dateRange) {
      params.start_date = filters.dateRange[0];
      params.end_date = filters.dateRange[1];
    }
    if (filters.disease) params.disease = filters.disease;
    if (filters.minConf > 0) params.min_confidence = filters.minConf / 100;

    const res = await myRecords(params);
    list.value = res.data.list || [];
    total.value = res.data.total || 0;

    if (list.value.length > 0) {
      const ids = list.value.map(r => r.id).join(",");
      try {
        const fbRes = await batchGetFeedback(ids);
        feedbackMap.value = fbRes.data || {};
      } catch {
        feedbackMap.value = {};
      }
    }
  } finally {
    loading.value = false;
  }
};

const resetFilters = () => {
  filters.dateRange = null;
  filters.disease = '';
  filters.minConf = 0;
  query.page = 1;
  loadData();
};

const exportRecord = async (row) => {
  try {
    await downloadReport(row.id);
    ElMessage.success("报告下载成功");
  } catch {
    ElMessage.error("下载失败");
  }
};

const handlePageChange = (page) => { query.page = page; loadData(); };
onMounted(loadData);
</script>

<style scoped>
.records-container { padding: 10px; }
.records-card { border-radius: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.header-left { display: flex; align-items: center; gap: 8px; }
.header-title { font-size: 16px; font-weight: 600; color: #303133; }
.filter-bar { margin-bottom: 16px; padding: 16px; background: #fafafa; border-radius: 8px; }
.time-cell { display: flex; align-items: center; gap: 6px; color: #606266; font-size: 13px; }
.diagnosis-text { font-weight: 500; color: #303133; }
.pagination-wrapper { margin-top: 20px; display: flex; justify-content: flex-end; }
</style>
