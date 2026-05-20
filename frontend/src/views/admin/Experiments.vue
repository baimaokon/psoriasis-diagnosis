<!--
Experiments.vue — 管理端实验对比页
───────────────────────────────────
路由：/admin/experiments
功能：多训练任务横向对比（验证准确率、F1等指标），训练曲线可视化。
后端对接：routes/admin.py → GET /api/admin/experiments/compare、/api/admin/training/<id>/visualization
-->
<template>
  <div class="experiments-container">
    <el-tabs type="border-card">
      <!-- 1. 模型对比 -->
      <el-tab-pane label="📊 实验对比">
        <el-table :data="selectedJobs" border style="width: 100%">
          <el-table-column prop="name" label="任务名称" />
          <el-table-column prop="params.backbone" label="主干网络" width="120" />
          <el-table-column prop="metrics.val_accuracy" label="验证集精度" width="120">
            <template #default="{ row }">{{ (row.metrics.val_accuracy * 100).toFixed(2) }}%</template>
          </el-table-column>
          <el-table-column prop="metrics.val_f1" label="F1 Score" width="120">
            <template #default="{ row }">{{ (row.metrics.val_f1 * 100).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="耗时" width="120">
            <template #default="{ row }">{{ row.metrics.duration ? Math.round(row.metrics.duration / 60) + ' min' : '-' }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 2. 训练过程可视化 -->
      <el-tab-pane label="📈 训练细节">
        <div v-if="chartData.epochs.length > 0">
          <v-chart class="chart" :option="lossOption" autoresize />
          <v-chart class="chart" :option="accOption" autoresize />
        </div>
        <el-empty v-else description="请选择一个已完成的任务查看详情" />
      </el-tab-pane>

      <!-- 3. 错误案例分析 -->
      <el-tab-pane label="⚠️ 错误案例">
        <div class="error-grid">
          <div v-for="item in errorCases" :key="item.id" class="error-card">
            <el-image :src="item.image_url" fit="cover" class="err-img" />
            <div class="err-info">
              <div class="err-label">{{ item.predicted_label_zh }}</div>
              <el-progress :percentage="(item.confidence * 100).toFixed(0)" :stroke-width="6" color="#f56c6c" />
              <p class="err-desc">置信度极低，建议人工复核</p>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import VChart from 'vue-echarts';
import request from '@/api/request';

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const selectedJobs = ref([]);
const chartData = ref({ epochs: [], train_losses: [], val_losses: [], val_accuracies: [] });
const errorCases = ref([]);

const lossOption = computed(() => ({
  title: { text: 'Loss 变化趋势' },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: chartData.value.epochs },
  yAxis: { type: 'value' },
  series: [
    { name: 'Train Loss', data: chartData.value.train_losses, type: 'line', smooth: true },
    { name: 'Val Loss', data: chartData.value.val_losses, type: 'line', smooth: true }
  ]
}));

const accOption = computed(() => ({
  title: { text: 'Accuracy 变化趋势' },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: chartData.value.epochs },
  yAxis: { type: 'value', min: 0, max: 1 },
  series: [{ name: 'Val Accuracy', data: chartData.value.val_accuracies, type: 'line', smooth: true, areaStyle: {} }]
}));

const loadErrorCases = async () => {
  try {
    const res = await request.get('/admin/analysis/error-cases');
    errorCases.value = res.data || [];
  } catch {
    // 错误已由拦截器统一处理
  }
};

onMounted(loadErrorCases);
</script>

<style scoped>
.experiments-container { padding: 20px; }
.chart { height: 350px; margin-bottom: 20px; }
.error-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
.error-card { border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
.err-img { width: 100%; height: 150px; }
.err-info { padding: 10px; }
.err-label { font-weight: bold; margin-bottom: 5px; }
.err-desc { font-size: 12px; color: #999; margin-top: 5px; }
</style>