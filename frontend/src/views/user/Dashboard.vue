<template>
  <div class="dashboard-container" v-loading="loading">
    <!-- 4 个统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon total-icon">
              <el-icon :size="28"><DataAnalysis /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-title">总诊断次数</div>
              <div class="stat-value">{{ data.total || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon month-icon">
              <el-icon :size="28"><Calendar /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-title">本月诊断</div>
              <div class="stat-value">{{ data.this_month || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon conf-icon">
              <el-icon :size="28"><TrendCharts /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-title">平均置信度</div>
              <div class="stat-value">{{ (data.avg_confidence * 100).toFixed(1) }}%</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon top-icon">
              <el-icon :size="28"><Trophy /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-title">最常见病种</div>
              <div class="stat-value small">{{ topCondition }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表 + 最近记录 -->
    <el-row :gutter="16" class="content-row" v-if="data.total > 0">
      <!-- 疾病分布饼图 -->
      <el-col :xs="24" :lg="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="18"><PieChart /></el-icon>
              <span>疾病分布</span>
            </div>
          </template>
          <v-chart v-if="pieOption" class="chart" :option="pieOption" autoresize />
          <el-empty v-else description="暂无数据" :image-size="80" />
        </el-card>
      </el-col>

      <!-- 最近诊断 -->
      <el-col :xs="24" :lg="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="18"><Clock /></el-icon>
              <span>最近诊断</span>
            </div>
          </template>
          <el-table :data="data.recent" border stripe size="small" max-height="360">
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column prop="predicted_label_zh" label="诊断结果" min-width="120" />
            <el-table-column label="置信度" width="140">
              <template #default="{ row }">
                <el-progress
                  :percentage="(row.confidence * 100)"
                  :stroke-width="6"
                  :color="row.confidence >= 0.9 ? '#67c23a' : row.confidence >= 0.7 ? '#e6a23c' : '#f56c6c'"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && data.total === 0" description="暂无诊断数据，开始你的第一次诊断吧">
      <el-button type="primary" @click="$router.push('/user/diagnose')">
        <el-icon><Upload /></el-icon>
        开始诊断
      </el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { Calendar, Clock, DataAnalysis, PieChart, TrendCharts, Trophy, Upload } from '@element-plus/icons-vue';
import { use } from 'echarts/core';
import { PieChart as EPie } from 'echarts/charts';
import { CanvasRenderer } from 'echarts/renderers';
import { LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components';
import VChart from 'vue-echarts';
import { getDashboard } from "@/api/user";

use([CanvasRenderer, EPie, LegendComponent, TitleComponent, TooltipComponent]);

const loading = ref(true);
const data = reactive({ total: 0, this_month: 0, avg_confidence: 0, disease_distribution: {}, recent: [] });

const topCondition = computed(() => {
  const keys = Object.keys(data.disease_distribution);
  return keys.length > 0 ? keys[0] : "暂无";
});

const pieOption = computed(() => {
  const dist = data.disease_distribution;
  const names = Object.keys(dist);
  if (names.length === 0) return null;
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['35%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      data: names.map(name => ({ name, value: dist[name] })),
      emphasis: { label: { fontSize: 16, fontWeight: 'bold' } },
    }],
  };
});

onMounted(async () => {
  try {
    const res = await getDashboard();
    Object.assign(data, res.data || {});
  } catch {
    // 拦截器已处理
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.dashboard-container { padding: 20px; min-height: 400px; }

.stat-row { margin-bottom: 20px; }
.stat-card { border-radius: 12px; }
.stat-content { display: flex; align-items: center; gap: 16px; }
.stat-icon { width: 56px; height: 56px; border-radius: 12px; display: flex; align-items: center; justify-content: center; }
.total-icon { background: linear-gradient(135deg, #409eff, #337ecc); color: #fff; }
.month-icon { background: linear-gradient(135deg, #67c23a, #529b2e); color: #fff; }
.conf-icon { background: linear-gradient(135deg, #e6a23c, #cf9236); color: #fff; }
.top-icon { background: linear-gradient(135deg, #f56c6c, #e04e4e); color: #fff; }
.stat-info { flex: 1; }
.stat-title { font-size: 13px; color: #909399; margin-bottom: 4px; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; }
.stat-value.small { font-size: 16px; }

.content-row { margin-bottom: 20px; }
.card-header { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.chart { height: 320px; }
</style>
