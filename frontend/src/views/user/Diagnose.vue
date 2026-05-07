<template>
  <div class="diagnose-container">
    <el-row :gutter="20">
      <el-col :xs="24" :lg="12">
        <el-card class="upload-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#409eff"><UploadFilled /></el-icon>
              <span class="header-title">批量图像上传 (最多10张)</span>
            </div>
          </template>

          <el-upload
              ref="uploadRef"
              v-model:file-list="fileList"
              class="upload-dragger"
              drag
              multiple
              :limit="10"
              :auto-upload="false"
              :on-exceed="handleExceed"
              accept=".jpg,.jpeg,.png,.bmp,.webp"
              list-type="picture"
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 JPG/PNG/BMP/WEBP，单张不超过 10MB</div>
            </template>
          </el-upload>

          <div class="action-bar">
            <el-button type="primary" size="large" :disabled="fileList.length === 0 || diagnosing" @click="startBatchDiagnose">
              <el-icon v-if="!diagnosing"><Aim /></el-icon>
              <el-icon v-else class="is-loading"><Loading /></el-icon>
              {{ diagnosing ? `诊断中 (${completedCount}/${fileList.length})` : '开始批量诊断' }}
            </el-button>
            <el-button size="large" @click="clearFiles" :disabled="diagnosing">清空</el-button>
          </div>
        </el-card>

        <!-- 🔑 新增：诊断完成后的结果展示区 -->
        <el-card v-if="results.length > 0" class="results-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#67c23a"><CircleCheck /></el-icon>
              <span class="header-title">诊断结果 ({{ results.length }})</span>
              <el-button type="primary" link size="small" @click="viewAllResults">查看全部</el-button>
            </div>
          </template>
          <div class="result-previews">
            <div v-for="r in results.slice(0, 4)" :key="r.id" class="result-preview-item" @click="openResultDetail(r)">
              <el-image :src="r.image_url" fit="cover" class="preview-thumb" />
              <div class="preview-info">
                <div class="preview-label">{{ r.predicted_label_zh }}</div>
                <el-progress :percentage="parseFloat((r.confidence * 100).toFixed(0))" :stroke-width="6" :show-text="false" :color="getConfidenceColor(r.confidence)" />
                <div class="preview-conf">{{ (r.confidence * 100).toFixed(1) }}%</div>
              </div>
            </div>
            <div v-if="results.length > 4" class="more-hint" @click="viewAllResults">
              还有 {{ results.length - 4 }} 条结果...
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card class="queue-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#67c23a"><List /></el-icon>
              <span class="header-title">诊断队列与进度</span>
            </div>
          </template>

          <el-empty v-if="queue.length === 0" description="暂无诊断任务" :image-size="100" />

          <div v-else class="queue-list">
            <div v-for="item in queue" :key="item.uid" class="queue-item" :class="item.status" @click="item.status === 'success' && openResultDetail(item)">
              <el-image :src="item.thumb" fit="cover" class="item-thumb" />
              <div class="item-info">
                <div class="item-name">{{ item.name }}</div>
                <el-steps :active="item.step" finish-status="success" simple class="item-steps">
                  <el-step title="预处理" />
                  <el-step title="特征提取" />
                  <el-step title="模型推理" />
                  <el-step title="热力图" />
                </el-steps>
                <div class="item-status">
                  <el-tag v-if="item.status === 'waiting'" type="info" size="small">等待中</el-tag>
                  <el-tag v-else-if="item.status === 'processing'" type="warning" size="small">诊断中 {{ Math.round(item.step / 4 * 100) }}%</el-tag>
                  <el-tag v-else-if="item.status === 'success'" type="success" size="small">完成 ({{ item.confidence }}%)</el-tag>
                  <el-tag v-else type="danger" size="small">失败</el-tag>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 🔑 新增：结果详情对话框 -->
    <el-dialog v-model="detailVisible" title="诊断详情" width="70%" top="5vh" destroy-on-close>
      <DiagnoseResultCard v-if="currentResult" :result="currentResult" />
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, defineAsyncComponent } from "vue";
import { ElMessage } from "element-plus";
import { UploadFilled, Aim, Loading, List, CircleCheck } from '@element-plus/icons-vue';
import { diagnoseBatch } from "@/api/user";

const DiagnoseResultCard = defineAsyncComponent(() => import('@/components/user/DiagnoseResultCard.vue'));

const uploadRef = ref(null);
const fileList = ref([]);
const diagnosing = ref(false);
const queue = ref([]);
const results = ref([]);
const detailVisible = ref(false);
const currentResult = ref(null);

const completedCount = computed(() => queue.value.filter(i => i.status === 'success' || i.status === 'failed').length);

const getConfidenceColor = (c) => c >= 0.9 ? '#67c23a' : c >= 0.7 ? '#e6a23c' : '#f56c6c';

const handleExceed = () => ElMessage.warning("一次最多上传 10 张图像");

const clearFiles = () => {
  fileList.value = [];
  queue.value = [];
  results.value = [];
};

const openResultDetail = (item) => {
  if (item.status !== 'success') return;
  currentResult.value = item;
  detailVisible.value = true;
};

const viewAllResults = () => {
  const successItems = queue.value.filter(i => i.status === 'success');
  if (successItems.length > 0) {
    currentResult.value = successItems[0];
    detailVisible.value = true;
  }
};

const startBatchDiagnose = async () => {
  if (fileList.value.length === 0) return;

  diagnosing.value = true;
  queue.value = fileList.value.map(f => ({
    uid: f.uid,
    name: f.name,
    thumb: f.url,
    status: 'waiting',
    step: 0,
    confidence: 0
  }));

  const formData = new FormData();
  fileList.value.forEach(f => formData.append("images", f.raw));

  // 模拟进度推进
  const progressTimer = setInterval(() => {
    queue.value.forEach(item => {
      if (item.status === 'processing' && item.step < 3) {
        item.step += 1;
      }
    });
  }, 800);

  try {
    const res = await diagnoseBatch(formData);
    clearInterval(progressTimer);

    const batchResults = res.data || [];
    results.value = [];

    batchResults.forEach(r => {
      const qItem = queue.value.find(q => q.uid === fileList.value[r.index]?.uid);
      if (qItem) {
        if (r.status === 'success') {
          qItem.status = 'success';
          qItem.step = 4;
          qItem.confidence = (r.data.confidence * 100).toFixed(1);
          // 🔑 将完整结果数据同步到队列项
          Object.assign(qItem, r.data);
          results.value.push(qItem);
        } else {
          qItem.status = 'failed';
          qItem.step = 0;
        }
      }
    });

    if (results.value.length > 0) {
      ElMessage.success(`批量诊断完成！成功 ${results.value.length} 张`);
    } else {
      ElMessage.warning("所有图像诊断失败");
    }
  } catch (error) {
    clearInterval(progressTimer);
    ElMessage.error("诊断请求失败");
    queue.value.forEach(q => { if(q.status === 'processing') q.status = 'failed'; });
  } finally {
    diagnosing.value = false;
  }
};
</script>

<style scoped>
.diagnose-container { padding: 10px; }
.card-header { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 600; }
.upload-card, .queue-card, .results-card { border-radius: 12px; margin-bottom: 20px; }
.upload-dragger :deep(.el-upload-dragger) { padding: 30px; }
.action-bar { display: flex; gap: 12px; margin-top: 16px; justify-content: center; }
.queue-list { max-height: 500px; overflow-y: auto; }
.queue-item { display: flex; gap: 12px; padding: 12px; border-bottom: 1px solid #eee; transition: background 0.3s; cursor: default; }
.queue-item:hover { background: #f9fafc; }
.queue-item.success { background: #f0f9eb; cursor: pointer; }
.item-thumb { width: 60px; height: 60px; border-radius: 6px; flex-shrink: 0; }
.item-info { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 4px; }
.item-name { font-weight: 500; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-steps { margin: 4px 0; }
.item-steps :deep(.el-step__title) { font-size: 12px; }
.item-status { display: flex; justify-content: flex-end; }

/* 结果预览区样式 */
.result-previews { display: flex; flex-wrap: wrap; gap: 12px; }
.result-preview-item { width: calc(50% - 6px); border: 2px solid #ebeef5; border-radius: 8px; overflow: hidden; cursor: pointer; transition: all 0.3s; }
.result-preview-item:hover { border-color: #409eff; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.preview-thumb { width: 100%; height: 100px; display: block; }
.preview-info { padding: 8px; }
.preview-label { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.preview-conf { font-size: 12px; color: #67c23a; font-weight: bold; margin-top: 4px; text-align: right; }
.more-hint { width: 100%; text-align: center; padding: 12px; color: #409eff; cursor: pointer; font-size: 13px; }
.more-hint:hover { text-decoration: underline; }
</style>
