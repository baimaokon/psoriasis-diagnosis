<!--
DiagnoseResultCard.vue — 诊断结果卡片组件（Diagnose.vue 的子组件）
──────────────────────────────────────────────────────────────────
展示单张图像的诊断结果：缩略图、疾病名称、置信度、Grad-CAM热力图叠加效果
父组件：views/user/Diagnose.vue
-->
<template>
  <el-card class="result-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="header-left">
          <el-icon :size="20" color="#e6a23c"><TrendCharts /></el-icon>
          <span class="header-title">详细诊断结果</span>
        </div>
        <el-button type="primary" size="small" :loading="exportLoading" @click="exportReport">
          <el-icon><Download /></el-icon>
          导出 PDF 报告
        </el-button>
      </div>
    </template>

    <div class="result-panel">
      <div class="predictions-section">
        <h3 class="section-subtitle">Top 预测结果</h3>
        <el-table :data="result.predictions" border stripe size="small">
          <el-table-column type="index" label="#" width="50" align="center" />
          <el-table-column prop="label_zh" label="中文病名" min-width="140">
            <template #default="{ row, $index }">
              <span :class="{ 'top-result': $index === 0 }">{{ row.label_zh }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="label_en" label="英文类别" min-width="240" show-overflow-tooltip />
          <el-table-column label="概率" width="120" align="right">
            <template #default="{ row, $index }">
              <el-tag :type="$index === 0 ? 'success' : 'info'" effect="plain" size="small">
                {{ (row.confidence * 100).toFixed(2) }}%
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="images-section">
        <h3 class="section-subtitle">可视化分析</h3>
        <div class="image-grid">
          <ImageDisplay title="原始图像" icon="Picture" :src="result.image_url" />
          <ImageDisplay title="Grad-CAM 热力图" icon="HotWater" :src="result.heatmap_url" />
        </div>
      </div>

      <el-divider />

      <!-- 反馈区域 -->
      <div class="feedback-section">
        <h3 class="section-subtitle feedback-title">
          <el-icon :size="18"><ChatLineSquare /></el-icon>
          诊断反馈（人机协同纠错）
        </h3>

        <div v-if="feedbackState === 'idle'" class="feedback-buttons">
          <p class="feedback-hint">此诊断结果是否准确？您的反馈将帮助我们持续提升模型精度。</p>
          <div class="btn-group">
            <el-button type="success" size="large" :loading="feedbackSubmitting" @click="submitCorrect">
              <el-icon><Select /></el-icon>
              预测正确
            </el-button>
            <el-button type="danger" size="large" :loading="feedbackSubmitting" @click="openCorrectionDialog">
              <el-icon><CloseBold /></el-icon>
              预测有误
            </el-button>
          </div>
        </div>

        <div v-else-if="feedbackState === 'correct'" class="feedback-result feedback-correct">
          <el-icon :size="28"><CircleCheckFilled /></el-icon>
          <div class="feedback-text">
            <strong>感谢反馈！</strong>
            <span>您已确认此诊断结果正确，AI 模型将持续优化。</span>
          </div>
        </div>

        <div v-else-if="feedbackState === 'wrong'" class="feedback-result feedback-wrong">
          <el-icon :size="28"><WarningFilled /></el-icon>
          <div class="feedback-text">
            <strong>反馈已记录</strong>
            <span>您标记的纠正类别：<el-tag type="warning" size="small">{{ correctedLabelZh }}</el-tag></span>
            <span v-if="feedbackComment">备注：{{ feedbackComment }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 纠错对话框 -->
    <el-dialog v-model="correctionVisible" title="纠正诊断结果" width="520px" top="10vh" destroy-on-close>
      <el-form label-width="100px" size="default">
        <el-form-item label="原始预测">
          <el-tag type="info" size="large">{{ result.predicted_label_zh }}</el-tag>
        </el-form-item>
        <el-form-item label="正确诊断">
          <el-select v-model="correctionLabel" placeholder="请选择正确的疾病类型" filterable style="width: 100%">
            <el-option
              v-for="item in labelOptions"
              :key="item.label_en"
              :label="item.label_display"
              :value="item.label_en"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="补充说明">
          <el-input
            v-model="correctionComment"
            type="textarea"
            :rows="3"
            placeholder="可选：补充说明此诊断差异（如：病灶位置不符、颜色判断有误等）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="correctionVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!correctionLabel" :loading="feedbackSubmitting" @click="submitWrong">
          提交纠错
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, onMounted, defineAsyncComponent } from "vue";
import { ElMessage } from "element-plus";
import { TrendCharts, ChatLineSquare, Select, CloseBold, CircleCheckFilled, WarningFilled, Download } from '@element-plus/icons-vue';
import { getLabels, getRecordFeedback, submitFeedback } from "@/api/feedback";
import { downloadReport } from "@/api/user";

const ImageDisplay = defineAsyncComponent(() => import('./ImageDisplay.vue'));

const props = defineProps({ result: Object });

const feedbackState = ref("idle"); // idle | correct | wrong
const feedbackSubmitting = ref(false);
const exportLoading = ref(false);
const correctionVisible = ref(false);
const correctionLabel = ref("");
const correctionComment = ref("");
const labelOptions = ref([]);
const correctedLabelZh = ref("");
const feedbackComment = ref("");

const loadExistingFeedback = async () => {
  const recordId = props.result?.id;
  if (!recordId) return;

  try {
    const res = await getRecordFeedback(recordId);
    const data = res.data;
    if (data?.has_feedback && data.feedback) {
      if (data.feedback.is_correct) {
        feedbackState.value = "correct";
      } else {
        feedbackState.value = "wrong";
        correctedLabelZh.value = data.feedback.corrected_label || "";
        feedbackComment.value = data.feedback.comment || "";
      }
    }
  } catch {
    // 静默加载，忽略错误
  }
};

const loadLabels = async () => {
  try {
    const res = await getLabels();
    labelOptions.value = res.data || [];
  } catch {
    // 标签加载失败时使用空列表
  }
};

const submitCorrect = async () => {
  feedbackSubmitting.value = true;
  try {
    await submitFeedback({ record_id: props.result.id, is_correct: true });
    feedbackState.value = "correct";
    ElMessage.success("感谢反馈，已记录诊断结果正确");
  } catch (e) {
    ElMessage.error(e.response?.data?.message || "提交失败");
  } finally {
    feedbackSubmitting.value = false;
  }
};

const openCorrectionDialog = () => {
  correctionLabel.value = "";
  correctionComment.value = "";
  correctionVisible.value = true;
};

const submitWrong = async () => {
  if (!correctionLabel.value) return;
  feedbackSubmitting.value = true;
  try {
    await submitFeedback({
      record_id: props.result.id,
      is_correct: false,
      corrected_label: correctionLabel.value,
      comment: correctionComment.value || undefined,
    });
    feedbackState.value = "wrong";
    correctionVisible.value = false;
    const selected = labelOptions.value.find(o => o.label_en === correctionLabel.value);
    correctedLabelZh.value = selected?.label_display || correctionLabel.value;
    feedbackComment.value = correctionComment.value;
    ElMessage.success("纠错反馈已提交，感谢您的贡献");
  } catch (e) {
    ElMessage.error(e.response?.data?.message || "提交失败");
  } finally {
    feedbackSubmitting.value = false;
  }
};

const exportReport = async () => {
  exportLoading.value = true;
  try {
    await downloadReport(props.result.id);
    ElMessage.success("报告下载成功");
  } catch {
    ElMessage.error("报告下载失败，请重试");
  } finally {
    exportLoading.value = false;
  }
};

onMounted(() => {
  loadExistingFeedback();
  loadLabels();
});
</script>

<style scoped>
.card-header { display: flex; align-items: center; justify-content: space-between; }
.header-left { display: flex; align-items: center; gap: 8px; }
.header-title { font-size: 16px; font-weight: 600; color: #303133; }
.result-card { border-radius: 12px; }
.result-panel { display: flex; flex-direction: column; gap: 24px; }
.section-subtitle { font-size: 15px; font-weight: 600; color: #303133; margin: 0 0 12px 0; padding-left: 12px; border-left: 4px solid #409eff; }
.top-result { font-weight: 600; color: #67c23a; }
.image-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
@media (max-width: 768px) { .image-grid { grid-template-columns: 1fr; } }

/* 反馈区域 */
.feedback-section {
  background: #f9fafc;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 20px 24px;
}
.feedback-title { border-left-color: #e6a23c; margin-bottom: 16px; }
.feedback-hint { font-size: 14px; color: #606266; margin: 0 0 16px 0; text-align: center; }
.btn-group { display: flex; gap: 16px; justify-content: center; }
.btn-group .el-button { min-width: 140px; }

.feedback-result {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 12px 0;
}
.feedback-correct { color: #67c23a; }
.feedback-wrong { color: #e6a23c; }
.feedback-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #303133;
}
.feedback-text strong { font-size: 15px; }
.feedback-text span { font-size: 13px; color: #606266; }
</style>
