<!--
Dashboard.vue — 管理端仪表盘（核心页面，集成全部管理功能）
─────────────────────────────────────────────────────────────
路由：/admin/dashboard
功能模块：
  1. 顶部统计卡片：普通用户数/模型版本数/诊断记录数
  2. 数据集概览：总图像数+类别分布表+按类别浏览样本
  3. 训练任务管理：配置超参数→启动训练→SSE实时进度折线图→终止/复活
  4. 模型版本管理：版本列表→性能对比→一键上线(热切换)→删除
API对接：api/admin.js → 全部管理端 API
后端对接：routes/admin.py → 全部 /api/admin/* 端点
SSE连接：直接使用 EventSource 连接 /api/admin/train/stream?token=xxx
-->
<template>
  <div class="dashboard">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="24" :sm="8">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon user-icon">
              <el-icon :size="32"><User /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-title">普通用户数</div>
              <div class="stat-value">{{ dashboard.user_count || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon model-icon">
              <el-icon :size="32"><Cpu /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-title">模型版本数</div>
              <div class="stat-value">{{ dashboard.model_count || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon record-icon">
              <el-icon :size="32"><Document /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-title">诊断记录数</div>
              <div class="stat-value">{{ dashboard.record_count || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="main-row">
      <el-col :xs="24" :lg="9">
        <el-card class="card-block" shadow="hover">
          <template #header>
            <div class="header-row">
              <div class="header-left">
                <el-icon :size="18" color="#409eff"><DataAnalysis /></el-icon>
                <span>数据集概览</span>
              </div>
              <el-button size="small" type="primary" plain @click="loadDatasetSummary">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>
          <el-form label-width="110px" size="default">
            <el-form-item label="数据集目录">
              <el-input v-model="datasetDirInput" placeholder="数据集目录" clearable>
                <template #prefix>
                  <el-icon><Folder /></el-icon>
                </template>
              </el-input>
            </el-form-item>
          </el-form>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="总图像数">
              <el-tag type="success" effect="dark" size="large">
                {{ datasetSummary.total_images || 0 }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="类别数">
              <el-tag type="primary" effect="dark" size="large">
                {{ datasetSummary.class_count || 0 }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <el-table
              :data="datasetSummary.classes || []"
              border
              stripe
              max-height="300"
              style="margin-top: 12px"
          >
            <el-table-column prop="zh_name" label="中文病名" min-width="140" />
            <el-table-column prop="name" label="英文类别" min-width="220" show-overflow-tooltip />
            <el-table-column prop="count" label="数量" width="90" align="center" />
            <el-table-column label="浏览" width="80" align="center">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  link
                  @click="openClassBrowser(row)"
                >
                  <el-icon><View /></el-icon>
                  查看
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 新增：数据集浏览器对话框 -->
        <el-dialog
          v-model="browserVisible"
          :title="`数据集浏览器 - ${currentClassInfo?.zh_name || currentClassName}`"
          width="80%"
          top="5vh"
          destroy-on-close
        >
          <div class="dataset-browser">
            <div class="browser-header">
              <el-descriptions :column="3" border size="small">
                <el-descriptions-item label="类别名称">
                  {{ currentClassName }}
                </el-descriptions-item>
                <el-descriptions-item label="样本总数">
                  <el-tag type="success">{{ browserTotal }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="当前页码">
                  {{ browserPage }} / {{ browserTotalPages }}
                </el-descriptions-item>
              </el-descriptions>
            </div>

            <div v-loading="browserLoading" class="sample-grid">
              <el-empty v-if="!browserLoading && browserSamples.length === 0" description="暂无样本" />

              <div
                v-for="sample in browserSamples"
                :key="sample.filename"
                class="sample-item"
                @click="previewSample(sample)"
              >
                <div class="sample-image-wrapper">
                  <el-image
                    :src="sample.url"
                    fit="cover"
                    lazy
                    class="sample-image"
                  >
                    <template #error>
                      <div class="image-error">
                        <el-icon :size="40"><Picture /></el-icon>
                      </div>
                    </template>
                  </el-image>
                  <div class="sample-overlay">
                    <el-icon :size="24" color="#fff"><ZoomIn /></el-icon>
                  </div>
                </div>
                <div class="sample-filename" :title="sample.filename">
                  {{ sample.filename }}
                </div>
              </div>
            </div>

            <div class="browser-pagination">
              <el-pagination
                v-model:current-page="browserPage"
                :page-size="browserPerPage"
                :total="browserTotal"
                layout="total, prev, pager, next, jumper"
                @current-change="loadClassSamples"
              />
            </div>
          </div>

          <template #footer>
            <el-button @click="browserVisible = false">关闭</el-button>
          </template>
        </el-dialog>

        <!-- 图片预览对话框 -->
        <el-dialog
          v-model="previewVisible"
          :title="previewSampleData?.filename"
          width="70%"
          center
        >
          <div class="preview-container">
            <el-image
              :src="previewSampleData?.url"
              fit="contain"
              style="width: 100%; max-height: 70vh;"
            />
          </div>
        </el-dialog>

        <el-card class="card-block" shadow="hover">
          <template #header>
            <div class="header-row">
              <div class="header-left">
                <el-icon :size="18" color="#67c23a"><VideoCamera /></el-icon>
                <span>训练任务</span>
              </div>
              <el-tag
                  v-if="dashboard.is_training"
                  type="warning"
                  effect="dark"
                  size="large"
              >
                <el-icon><Loading /></el-icon>
                训练中
              </el-tag>
              <el-tag v-else type="success" effect="dark" size="large">
                <el-icon><CircleCheck /></el-icon>
                空闲
              </el-tag>
            </div>
          </template>
          <el-form label-width="110px" size="default">
            <el-form-item label="任务名称">
              <el-input v-model="trainPayload.name" placeholder="例如：银屑病云训练V1" clearable>
                <template #prefix>
                  <el-icon><EditPen /></el-icon>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="数据集目录">
              <el-input v-model="trainPayload.dataset_dir" placeholder="默认使用后端配置目录" clearable>
                <template #prefix>
                  <el-icon><Folder /></el-icon>
                </template>
              </el-input>
            </el-form-item>
          </el-form>

          <el-divider content-position="left">
            <el-icon><Setting /></el-icon>
            参数配置
          </el-divider>
          <div class="param-scroll">
            <el-form label-width="120px" size="default">
              <template v-for="item in trainParamSpec" :key="item.key">
                <el-form-item :label="item.name">
                  <template #label>
                    <div class="param-label">
                      <span>{{ item.name }}</span>
                      <el-tooltip :content="item.description" placement="top">
                        <el-icon><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </div>
                  </template>
                  <el-select v-if="item.type === 'select'" v-model="trainPayload.params[item.key]" style="width: 100%">
                    <el-option
                        v-for="option in item.options || []"
                        :key="option"
                        :label="option"
                        :value="option"
                    />
                  </el-select>
                  <el-switch v-else-if="item.type === 'bool'" v-model="trainPayload.params[item.key]" />
                  <el-input-number
                      v-else
                      v-model="trainPayload.params[item.key]"
                      :step="item.type === 'float' ? 0.0001 : 1"
                      :min="item.min"
                      :max="item.max"
                      controls-position="right"
                      style="width: 100%"
                  />
                </el-form-item>
              </template>
            </el-form>
          </div>

          <div class="btn-row">
            <el-button type="primary" :loading="trainLoading" @click="startTraining">
              <el-icon><VideoPlay /></el-icon>
              开始训练
            </el-button>
            <el-button @click="applyPreset('base')">基础值</el-button>
            <el-button @click="applyPreset('balanced')">平衡建议</el-button>
            <el-button @click="applyPreset('max_performance')">高性能</el-button>
          </div>
        </el-card>

      </el-col>

      <el-col :xs="24" :lg="15">
        <el-card class="card-block" shadow="hover">
          <template #header>
            <div class="header-row">
              <div class="header-left">
                <el-icon :size="18" color="#e6a23c"><Memo /></el-icon>
                <span>参数说明（含推荐档位）</span>
              </div>
            </div>
          </template>
          <el-table :data="trainParamSpec" border stripe max-height="400">
            <el-table-column prop="name" label="参数" width="130" fixed />
            <el-table-column prop="description" label="说明" min-width="220" />
            <el-table-column label="基础值" width="130" align="center">
              <template #default="{ row }">{{ row.base }}</template>
            </el-table-column>
            <el-table-column label="平衡建议值" width="140" align="center">
              <template #default="{ row }">{{ row.balanced }}</template>
            </el-table-column>
            <el-table-column label="无视成本推荐值" width="150" align="center">
              <template #default="{ row }">{{ row.max_performance }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="card-block" shadow="hover">
          <template #header>
            <div class="header-row">
              <div class="header-left">
                <el-icon :size="18" color="#909399"><List /></el-icon>
                <span>训练任务进度</span>
              </div>
              <el-button size="small" type="primary" plain @click="loadJobs">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>
          <el-table
              :data="jobs"
              border
              stripe
              @row-click="selectJob"
              highlight-current-row
              max-height="400"
          >
            <el-table-column prop="id" label="ID" width="70" align="center" />
            <el-table-column prop="name" label="任务名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" effect="dark" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="进度" min-width="180">
              <template #default="{ row }">
                <el-progress
                    :percentage="Math.round(row.progress || 0)"
                    :stroke-width="14"
                    :color="getProgressColor(row.progress)"
                />
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="170" />
            <el-table-column label="操作" width="240" fixed="right" align="center">
              <template #default="{ row }">
                <el-space>
                  <el-button
                      v-if="row.status === 'running' || row.status === 'canceling'"
                      size="small"
                      type="warning"
                      plain
                      :disabled="row.status === 'canceling'"
                      @click.stop="terminateJob(row)"
                  >
                    终止
                  </el-button>
                  <el-button
                      v-if="row.status === 'failed' || row.status === 'canceled'"
                      size="small"
                      type="success"
                      plain
                      @click.stop="reviveJob(row)"
                  >
                    复活
                  </el-button>
                  <el-button
                      size="small"
                      type="danger"
                      plain
                      @click.stop="removeJob(row)"
                  >
                    删除
                  </el-button>
                </el-space>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="selectedJob" class="job-detail">
            <el-divider content-position="left">
              <el-icon><InfoFilled /></el-icon>
              任务详情：#{{ selectedJob.id }}
            </el-divider>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="状态">
                <el-tag :type="statusType(selectedJob.status)" effect="dark">
                  {{ selectedJob.status }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="当前轮次">
                {{ selectedJob.current_epoch }}/{{ selectedJob.total_epochs }}
              </el-descriptions-item>
              <el-descriptions-item label="最佳验证Acc">
                <el-tag type="success" effect="plain">
                  {{ (selectedJob.val_accuracy * 100).toFixed(2) }}%
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="消息">{{ selectedJob.message }}</el-descriptions-item>
            </el-descriptions>

            <div class="epoch-log-wrap">
              <el-table
                  :data="selectedJob.logs || []"
                  border
                  stripe
                  height="300"
                  style="margin-top: 12px"
              >
                <el-table-column prop="epoch" label="Epoch" width="80" align="center" />
                <el-table-column prop="train_loss" label="Train Loss" width="110" />
                <el-table-column prop="val_loss" label="Val Loss" width="110" />
                <el-table-column prop="val_accuracy" label="Val Acc" width="110" />
                <el-table-column prop="learning_rate" label="LR" width="130" />
              </el-table>
            </div>
          </div>
        </el-card>

        <el-card class="card-block" shadow="hover">
          <template #header>
            <div class="header-row">
              <div class="header-left">
                <el-icon :size="18" color="#409eff"><Box /></el-icon>
                <span>模型版本与上线</span>
              </div>
              <el-button size="small" type="primary" plain @click="loadModels">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>
          <el-table :data="models" border stripe>
            <el-table-column prop="id" label="ID" width="70" align="center" />
            <el-table-column prop="name" label="模型名" min-width="220" show-overflow-tooltip />
            <el-table-column prop="backbone" label="主干" width="120" align="center" />
            <el-table-column label="测试Acc" width="120" align="center">
              <template #default="{ row }">
                <el-tag type="success" effect="plain">
                  {{ ((row.metrics?.test?.accuracy || 0) * 100).toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="上线状态" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" effect="dark">
                  {{ row.is_active ? "已上线" : "未上线" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180" fixed="right" align="center">
              <template #default="{ row }">
                <el-space>
                  <el-button
                      size="small"
                      type="primary"
                      :disabled="row.is_active"
                      @click="activate(row)"
                  >
                    设为在线
                  </el-button>
                  <el-button size="small" type="danger" plain @click="removeModel(row)">
                    删除
                  </el-button>
                </el-space>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="card-block" shadow="hover">
          <template #header>
            <div class="header-row">
              <div class="header-left">
                <el-icon :size="18" color="#f56c6c"><Tickets /></el-icon>
                <span>诊断记录</span>
              </div>
              <el-button size="small" type="primary" plain @click="loadRecords">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>
          <el-input
              v-model="recordKeyword"
              placeholder="按用户名或预测类别搜索"
              clearable
              style="margin-bottom: 12px"
              @change="loadRecords"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-table :data="records" border stripe max-height="500" v-loading="records.length === 0">
            <el-table-column prop="created_at" label="时间" width="170" />
            <el-table-column prop="username" label="用户" width="120" />
            <el-table-column prop="predicted_label_zh" label="中文病名" min-width="150" />
            <el-table-column prop="predicted_label_en" label="英文类别" min-width="260" show-overflow-tooltip />
            <el-table-column label="置信度" width="120" align="center">
              <template #default="{ row }">
                <el-tag type="success" effect="plain">
                  {{ (row.confidence * 100).toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="原图" width="100" align="center">
              <template #default="{ row }">
                <el-link :href="row.image_url" target="_blank" :underline="false">
                  <el-button size="small" type="primary" link>
                    <el-icon><View /></el-icon>
                    查看
                  </el-button>
                </el-link>
              </template>
            </el-table-column>
            <el-table-column label="热力图" width="100" align="center">
              <template #default="{ row }">
                <el-link :href="row.heatmap_url" target="_blank" :underline="false">
                  <el-button size="small" type="success" link>
                    <el-icon><View /></el-icon>
                    查看
                  </el-button>
                </el-link>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right" align="center">
              <template #default="{ row }">
                <el-button size="small" type="danger" plain @click="removeRecord(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  User, Cpu, Document, DataAnalysis, Folder, Refresh, VideoCamera,
  Loading, CircleCheck, EditPen, Setting, QuestionFilled, VideoPlay,
  Memo, List, InfoFilled, Box, Tickets, Search, View, Picture, ZoomIn,
  Tools, DataBoard
} from '@element-plus/icons-vue';
import {
  activateModel,
  createTrainEventSource,
  deleteModel,
  deleteRecord,
  deleteTrainJob,
  getDashboard,
  getDatasetSummary,
  getClassSamples,
  getModels,
  getRandomSamples,
  getRecords,
  getTrainJobDetail,
  getTrainJobs,
  getTrainParamSpec,
  reviveTrainJob,
  startTrain,
  terminateTrainJob,
} from "@/api/admin";
import { getToken } from "@/utils/auth";

const dashboard = reactive({});
const datasetSummary = reactive({ classes: [] });
const trainParamSpec = ref([]);
const jobs = ref([]);
const models = ref([]);
const records = ref([]);
const selectedJob = ref(null);
const trainLoading = ref(false);
const trainEventSource = ref(null);
const streamReconnectTimer = ref(null);

const datasetDirInput = ref("");
const recordKeyword = ref("");
const trainPayload = reactive({
  name: "银屑病云训练任务",
  dataset_dir: "",
  params: {},
});

// 数据集浏览器相关状态
const browserVisible = ref(false);
const browserLoading = ref(false);
const browserSamples = ref([]);
const browserPage = ref(1);
const browserPerPage = ref(30);
const browserTotal = ref(0);
const browserTotalPages = ref(0);
const currentClassName = ref("");
const currentClassInfo = ref(null);

// 图片预览相关状态
const previewVisible = ref(false);
const previewSampleData = ref(null);

const statusType = (status) => {
  if (status === "success") return "success";
  if (status === "running" || status === "canceling") return "warning";
  if (status === "failed") return "danger";
  return "info";
};

// 新增函数：根据进度动态设置进度条颜色
const getProgressColor = (progress) => {
  if (progress >= 80) return '#67c23a'; // 绿色
  if (progress >= 50) return '#e6a23c'; // 黄色
  return '#409eff'; // 蓝色
};

const applyPreset = (key) => {
  trainParamSpec.value.forEach((item) => {
    trainPayload.params[item.key] = item[key];
  });
};

const isUserCancel = (err) => err === "cancel" || err === "close";

const applyJobRow = (jobRow) => {
  if (!jobRow || !jobRow.id) return;
  const idx = jobs.value.findIndex((item) => item.id === jobRow.id);
  if (idx >= 0) {
    jobs.value[idx] = jobRow;
  } else {
    jobs.value.unshift(jobRow);
  }
  if (selectedJob.value?.id === jobRow.id || !selectedJob.value) {
    selectedJob.value = jobRow;
  }
  dashboard.is_training = jobs.value.some((item) =>
      ["queued", "running", "canceling"].includes(item.status),
  );
};


const loadDashboard = async () => {
  const res = await getDashboard();
  Object.assign(dashboard, res.data || {});
};

const loadDatasetSummary = async () => {
  const params = {};
  if (datasetDirInput.value) params.dataset_dir = datasetDirInput.value;
  const res = await getDatasetSummary(params);
  const data = res.data || {};
  Object.assign(datasetSummary, data);
  if (!trainPayload.dataset_dir) trainPayload.dataset_dir = data.dataset_dir || "";
  if (!datasetDirInput.value) datasetDirInput.value = data.dataset_dir || "";
};

const openClassBrowser = async (classInfo) => {
  currentClassName.value = classInfo.name;
  currentClassInfo.value = classInfo;
  browserPage.value = 1;
  browserVisible.value = true;
  await loadClassSamples();
};

const loadClassSamples = async () => {
  if (!currentClassName.value) return;

  browserLoading.value = true;
  try {
    const res = await getClassSamples(currentClassName.value, {
      page: browserPage.value,
      per_page: browserPerPage.value,
      dataset_dir: datasetDirInput.value || undefined,
    });

    const data = res.data || {};
    browserSamples.value = data.samples || [];
    browserTotal.value = data.total || 0;
    browserTotalPages.value = data.total_pages || 0;
  } catch (error) {
    ElMessage.error("加载样本失败：" + (error.message || "未知错误"));
  } finally {
    browserLoading.value = false;
  }
};

const previewSample = (sample) => {
  previewSampleData.value = sample;
  previewVisible.value = true;
};

const loadParamSpec = async () => {
  const res = await getTrainParamSpec();
  trainParamSpec.value = res.data || [];
  if (!Object.keys(trainPayload.params).length) {
    applyPreset("balanced");
  }
};

const loadJobs = async () => {
  const res = await getTrainJobs({ limit: 30 });
  jobs.value = res.data || [];
  if (selectedJob.value) {
    const exists = jobs.value.some((item) => item.id === selectedJob.value.id);
    if (!exists) {
      selectedJob.value = null;
    }
  }
  if (!selectedJob.value && jobs.value.length) {
    selectedJob.value = jobs.value[0];
  }
  if (selectedJob.value) {
    try {
      const detail = await getTrainJobDetail(selectedJob.value.id);
      selectedJob.value = detail.data;
    } catch {
      selectedJob.value = jobs.value[0] || null;
    }
  }
};

const selectJob = async (row) => {
  const detail = await getTrainJobDetail(row.id);
  selectedJob.value = detail.data;
};

const loadModels = async () => {
  const res = await getModels();
  models.value = res.data || [];
};

const loadRecords = async () => {
  const res = await getRecords({
    keyword: recordKeyword.value || "",
    limit: 20,
  });
  records.value = res.data || [];
};

const activate = async (row) => {
  await activateModel(row.id);
  ElMessage.success("模型已上线");
  await loadModels();
  await loadDashboard();
};

const removeJob = async (row) => {
  const running = row.status === "running" || row.status === "canceling";
  const tip = running
      ? `确认删除训练任务 #${row.id} 吗？当前任务将先终止，随后自动删除。`
      : `确认删除训练任务 #${row.id} 吗？`;
  try {
    await ElMessageBox.confirm(
        tip,
        "删除确认",
        {
          type: "warning",
          confirmButtonText: "删除",
          cancelButtonText: "取消",
        },
    );
    const res = await deleteTrainJob(row.id);
    if (res?.data?.pending) {
      if (selectedJob.value?.id === row.id) {
        selectedJob.value = { ...selectedJob.value, status: "canceling" };
      }
      ElMessage.success("已提交终止并删除请求，请稍候");
    } else {
      if (selectedJob.value?.id === row.id) {
        selectedJob.value = null;
      }
      jobs.value = jobs.value.filter((item) => item.id !== row.id);
      ElMessage.success("训练任务已删除");
    }
    await loadDashboard();
  } catch (err) {
    if (isUserCancel(err)) return;
  }
};

const terminateJob = async (row) => {
  if (row.status === "canceling") {
    ElMessage.info("该任务已在终止中");
    return;
  }
  try {
    await ElMessageBox.confirm(
        `确认终止训练任务 #${row.id} 吗？`,
        "终止确认",
        {
          type: "warning",
          confirmButtonText: "终止",
          cancelButtonText: "取消",
        },
    );
    const res = await terminateTrainJob(row.id);
    applyJobRow(res?.data || {});
    ElMessage.success("终止请求已提交");
    await loadDashboard();
  } catch (err) {
    if (isUserCancel(err)) return;
  }
};

const reviveJob = async (row) => {
  try {
    await ElMessageBox.confirm(
        `确认复活任务 #${row.id} 吗？将按原参数重新启动新任务。`,
        "复活确认",
        {
          type: "warning",
          confirmButtonText: "复活",
          cancelButtonText: "取消",
        },
    );
    const res = await reviveTrainJob(row.id);
    const newJob = res?.data?.job;
    const resumed = Boolean(res?.data?.resume_from_checkpoint);
    if (newJob) {
      applyJobRow(newJob);
      selectedJob.value = newJob;
    }
    ElMessage.success(resumed ? "复活任务已启动，已从检查点续训" : "复活任务已启动，未找到检查点已从头训练");
    await Promise.all([loadJobs(), loadDashboard()]);
  } catch (err) {
    if (isUserCancel(err)) return;
  }
};

const removeModel = async (row) => {
  const extra = row.is_active ? "该模型当前在线，删除后会自动切换到其他模型（若存在）。" : "";
  try {
    await ElMessageBox.confirm(
        `确认删除模型 #${row.id} 吗？${extra}`,
        "删除确认",
        {
          type: "warning",
          confirmButtonText: "删除",
          cancelButtonText: "取消",
        },
    );
    const res = await deleteModel(row.id);
    const activatedModelId = res?.data?.activated_model_id;
    if (activatedModelId) {
      ElMessage.success(`模型已删除，已切换在线模型 #${activatedModelId}`);
    } else {
      ElMessage.success("模型已删除");
    }
    await Promise.all([loadModels(), loadDashboard(), loadJobs()]);
  } catch (err) {
    if (isUserCancel(err)) return;
  }
};

const removeRecord = async (row) => {
  try {
    await ElMessageBox.confirm(
        `确认删除诊断记录 #${row.id} 吗？`,
        "删除确认",
        {
          type: "warning",
          confirmButtonText: "删除",
          cancelButtonText: "取消",
        },
    );
    const res = await deleteRecord(row.id);
    const removedCount = res?.data?.removed_files?.length || 0;
    if (removedCount > 0) {
      ElMessage.success(`记录已删除，并清理文件 ${removedCount} 个`);
    } else {
      ElMessage.success("记录已删除");
    }
    await Promise.all([loadRecords(), loadDashboard()]);
  } catch (err) {
    if (isUserCancel(err)) return;
  }
};

const startTraining = async () => {
  trainLoading.value = true;
  try {
    await startTrain({
      name: trainPayload.name,
      dataset_dir: trainPayload.dataset_dir || undefined,
      params: trainPayload.params,
    });
    ElMessage.success("训练任务已启动");
    await loadJobs();
    await loadDashboard();
  } finally {
    trainLoading.value = false;
  }
};

const stopTrainStream = () => {
  if (streamReconnectTimer.value) {
    clearTimeout(streamReconnectTimer.value);
    streamReconnectTimer.value = null;
  }
  if (trainEventSource.value) {
    trainEventSource.value.close();
    trainEventSource.value = null;
  }
};

const scheduleTrainStreamReconnect = () => {
  if (streamReconnectTimer.value) return;
  streamReconnectTimer.value = window.setTimeout(() => {
    streamReconnectTimer.value = null;
    startTrainStream();
  }, 3000);
};

const startTrainStream = () => {
  const token = getToken();
  if (!token) return;
  stopTrainStream();
  const source = createTrainEventSource(token);
  trainEventSource.value = source;

  source.addEventListener("job_update", async (event) => {
    try {
      const payload = JSON.parse(event.data || "{}");
      const job = payload?.job;
      applyJobRow(job);
      if (payload?.type === "success") {
        await loadModels();
        await loadDashboard();
      } else if (payload?.type === "failed" || payload?.type === "canceled") {
        await loadDashboard();
      }
    } catch {
      // SSE解析异常忽略
    }
  });

  source.addEventListener("job_deleted", async (event) => {
    try {
      const payload = JSON.parse(event.data || "{}");
      const jobId = Number(payload?.job_id || 0);
      if (jobId > 0) {
        jobs.value = jobs.value.filter((item) => item.id !== jobId);
        if (selectedJob.value?.id === jobId) {
          selectedJob.value = jobs.value[0] || null;
        }
      }
    } finally {
      await loadDashboard();
    }
  });

  source.addEventListener("sync", async () => {
    await Promise.all([loadJobs(), loadDashboard(), loadModels()]);
  });

  source.onerror = () => {
    if (trainEventSource.value !== source) return;
    source.close();
    trainEventSource.value = null;
    scheduleTrainStreamReconnect();
  };
};

onMounted(async () => {
  // 1. 优先加载核心、轻量级的数据
  await Promise.all([
    loadDashboard(),
    loadParamSpec(),
    loadJobs(),
    loadModels(),
    loadRecords(),
  ]);

  startTrainStream();

  // 2. 核心渲染完成后，再在后台静默加载数据集概览
  // 使用 requestAnimationFrame 确保不阻塞首屏渲染
  requestAnimationFrame(() => {
    setTimeout(() => {
      loadDatasetSummary();
    }, 500);
  });
});

onUnmounted(() => {
  stopTrainStream();
});
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 10px;
  background-color: #f5f7fa; /* 添加浅灰色背景 */
  min-height: 100vh;
}

.stat-row {
  margin-bottom: 8px;
}

.stat-card {
  border-radius: 12px;
  transition: all 0.3s ease;
  background: linear-gradient(135deg, #ffffff 0%, #f9fafb 100%); /* 卡片渐变背景 */
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0; /* 防止图标被压缩 */
}

.user-icon {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.model-icon {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.record-icon {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.stat-info {
  flex: 1;
}

.stat-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.main-row {
  margin-top: 8px;
}

.card-block {
  margin-bottom: 16px;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
  border: none;
}

.card-block:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

/* 为卡片头部添加渐变背景 */
:deep(.el-card__header) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  border-bottom: none;
  padding: 14px 20px;
}

:deep(.el-card__body) {
  padding: 20px;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #fff; /* 与头部背景色匹配 */
}

.param-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.param-scroll {
  max-height: 380px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  padding: 12px;
  border-radius: 8px;
  background: #fafafa;
}

/* 滚动条美化 */
.param-scroll::-webkit-scrollbar {
  width: 6px;
}
.param-scroll::-webkit-scrollbar-thumb {
  background-color: #c0c4cc;
  border-radius: 3px;
}
.param-scroll::-webkit-scrollbar-thumb:hover {
  background-color: #909399;
}

.btn-row {
  margin-top: 12px;
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 12px 0;
  background: #f8f8f8;
  border-top: 1px solid #ebeef5;
  border-radius: 0 0 12px 12px;
}

.job-detail {
  margin-top: 12px;
}

.epoch-log-wrap {
  margin-top: 4px;
}

/* 进度条样式优化 */
:deep(.el-progress-bar__outer) {
  background-color: #ebeef5;
  border-radius: 10px;
  padding: 2px;
  background: #f5f7fa;
}

:deep(.el-progress-bar__inner) {
  border-radius: 10px;
  transition: all 0.3s ease;
}

/* 数据集浏览器样式 */
.dataset-browser {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.browser-header {
  margin-bottom: 8px;
}

.sample-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  max-height: 60vh;
  overflow-y: auto;
  padding: 8px;
}

.sample-item {
  cursor: pointer;
  transition: all 0.3s ease;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  border: 2px solid transparent;
}

.sample-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border-color: #409eff;
}

.sample-image-wrapper {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  background: #f5f7fa;
}

.sample-image {
  width: 100%;
  height: 100%;
}

.sample-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.sample-item:hover .sample-overlay {
  opacity: 1;
}

.sample-filename {
  padding: 8px;
  font-size: 12px;
  color: #606266;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  background: #fafafa;
}

.browser-pagination {
  display: flex;
  justify-content: center;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}

.preview-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.image-error {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: #f5f7fa;
  color: #c0c4cc;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .sample-grid {
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  }

  .stat-value {
    font-size: 24px;
  }

  .stat-icon {
    width: 50px;
    height: 50px;
  }
}
</style>