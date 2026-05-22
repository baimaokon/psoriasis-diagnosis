<template>
  <div class="ds-container">
    <!-- 顶部统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon total-icon"><el-icon :size="28"><Folder /></el-icon></div>
            <div class="stat-info"><div class="stat-title">数据集</div><div class="stat-value small">{{ currentDirName }}</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon count-icon"><el-icon :size="28"><Picture /></el-icon></div>
            <div class="stat-info"><div class="stat-title">总图片数</div><div class="stat-value">{{ summary.total_images || 0 }}</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon class-icon"><el-icon :size="28"><Grid /></el-icon></div>
            <div class="stat-info"><div class="stat-title">类别数</div><div class="stat-value">{{ summary.class_count || 0 }}</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon switch-icon"><el-icon :size="28"><Switch /></el-icon></div>
            <div class="stat-info">
              <div class="stat-title">切换数据集</div>
              <el-select v-model="currentDir" @change="switchDataset" size="small" style="width:180px">
                <el-option v-for="d in dirList" :key="d.path" :label="d.name" :value="d.path" />
              </el-select>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 主内容区 -->
    <el-row :gutter="16" v-loading="loading">
      <!-- 左侧类别列表 -->
      <el-col :xs="24" :sm="6">
        <el-card class="card-block" shadow="hover">
          <template #header><div class="card-header"><el-icon :size="18"><List /></el-icon><span>类别列表</span></div></template>
          <div class="class-list">
            <div v-for="cls in summary.classes" :key="cls.name"
              class="class-item" :class="{ active: selectedClass === cls.name }"
              @click="selectClass(cls.name)">
              <span class="class-name">{{ cls.zh_name || cls.name }}</span>
              <el-tag size="small" type="info">{{ cls.count }}</el-tag>
            </div>
            <el-empty v-if="!summary.classes?.length" description="无数据" :image-size="60" />
          </div>
        </el-card>
      </el-col>

      <!-- 右侧图片浏览 -->
      <el-col :xs="24" :sm="18">
        <el-card class="card-block" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="18"><PictureFilled /></el-icon>
              <span v-if="selectedClass">浏览：{{ selectedClass }}（共 {{ classTotal }} 张）</span>
              <span v-else>请从左侧选择一个类别</span>
              <div style="margin-left:auto">
                <el-button type="success" size="small" :icon="Upload" @click="uploadVisible = true" :disabled="!selectedClass">添加图片</el-button>
                <el-button size="small" :icon="Refresh" @click="loadClassSamples" :loading="samplesLoading" style="margin-left:8px">刷新</el-button>
              </div>
            </div>
          </template>

          <div v-if="selectedClass" v-loading="samplesLoading">
            <div v-if="classSamples.length > 0" class="image-grid">
              <div v-for="img in classSamples" :key="img.relative_path" class="image-item">
                <el-image :src="img.url" fit="cover" lazy class="thumb"
                  :preview-src-list="[img.url]" preview-teleported />
                <div class="img-name">{{ img.filename }}</div>
              </div>
            </div>
            <el-empty v-else description="该类别暂无图片" :image-size="80" />
            <div v-if="classTotal > pageSize" class="pagination-wrap">
              <el-pagination background layout="total, prev, pager, next"
                :total="classTotal" :page-size="pageSize"
                v-model:current-page="currentPage" @current-change="loadClassSamples" />
            </div>
          </div>
          <el-empty v-else description="选择左侧类别查看图片" :image-size="100" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadVisible" title="添加图片到数据集" width="480px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="目标类别"><el-input :model-value="selectedClass" disabled /></el-form-item>
        <el-form-item label="选择图片">
          <el-upload ref="uploadRef" :auto-upload="false" :limit="20" multiple
            accept=".jpg,.jpeg,.png,.bmp,.webp" :on-change="handleFileChange"
            :file-list="uploadFiles" list-type="picture">
            <el-button type="primary">选择文件（可多选）</el-button>
            <template #tip><div class="el-upload__tip">支持 jpg/png/bmp/webp，单张不超过 10MB</div></template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="doUpload">上传到 {{ selectedClass }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Folder, Picture, Grid, Switch, List, PictureFilled, Upload, Refresh } from '@element-plus/icons-vue';
import { getDatasetSummary, getClassSamples, listDatasetDirs, addDatasetImage } from "@/api/admin";

const loading = ref(true), samplesLoading = ref(false);
const currentDir = ref(""), dirList = ref([]);
const summary = reactive({ total_images: 0, class_count: 0, classes: [] });
const selectedClass = ref(""), classSamples = ref([]), classTotal = ref(0);
const currentPage = ref(1), pageSize = 60;
const uploadVisible = ref(false), uploadFiles = ref([]), uploading = ref(false);

const currentDirName = computed(() => {
  const d = dirList.value.find(x => x.path === currentDir.value);
  return d ? d.name : "未选择";
});

onMounted(loadData);

async function loadData() {
  loading.value = true;
  try {
    const [dirRes, summaryRes] = await Promise.all([
      listDatasetDirs(),
      getDatasetSummary(currentDir.value ? { dataset_dir: currentDir.value } : {}),
    ]);
    dirList.value = dirRes.data || [];
    if (!currentDir.value && dirList.value.length > 0) currentDir.value = dirList.value[0].path;
    if (summaryRes.data?.classes) summaryRes.data.classes.sort((a, b) => b.count - a.count);
    Object.assign(summary, summaryRes.data || {});
  } catch { /* 拦截器已处理 */ } finally { loading.value = false; }
}

async function switchDataset() { selectedClass.value = ""; classSamples.value = []; await loadData(); }

async function selectClass(name) { selectedClass.value = name; currentPage.value = 1; await loadClassSamples(); }

async function loadClassSamples() {
  if (!selectedClass.value) return;
  samplesLoading.value = true;
  try {
    const params = { page: currentPage.value, per_page: pageSize };
    if (currentDir.value) params.dataset_dir = currentDir.value;
    const res = await getClassSamples(selectedClass.value, params);
    classSamples.value = res.data?.samples || [];
    classTotal.value = res.data?.total || 0;
  } catch { /* */ } finally { samplesLoading.value = false; }
}

function handleFileChange(file) { uploadFiles.value.push(file); }

async function doUpload() {
  if (!uploadFiles.value.length) { ElMessage.warning("请先选择图片"); return; }
  uploading.value = true;
  let ok = 0, fail = 0;
  for (const f of uploadFiles.value) {
    try {
      const fd = new FormData();
      if (currentDir.value) fd.append("dataset_dir", currentDir.value);
      fd.append("class_name", selectedClass.value);
      fd.append("image", f.raw);
      await addDatasetImage(fd);
      ok++;
    } catch { fail++; }
  }
  uploading.value = false;
  if (ok > 0) ElMessage.success(`成功添加 ${ok} 张` + (fail > 0 ? `，${fail} 张失败` : ""));
  else ElMessage.error("全部上传失败");
  uploadFiles.value = []; uploadVisible.value = false;
  await loadData(); await loadClassSamples();
}
</script>

<style scoped>
.ds-container { padding: 20px; }

/* 统计卡片 — 复用 Dashboard 风格 */
.stat-row { margin-bottom: 20px; }
.stat-card { border-radius: 12px; }
.stat-content { display: flex; align-items: center; gap: 16px; }
.stat-icon { width: 56px; height: 56px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.total-icon { background: linear-gradient(135deg, #409eff, #337ecc); color: #fff; box-shadow: 0 4px 12px rgba(64,158,255,0.3); }
.count-icon { background: linear-gradient(135deg, #67c23a, #529b2e); color: #fff; box-shadow: 0 4px 12px rgba(103,194,58,0.3); }
.class-icon { background: linear-gradient(135deg, #e6a23c, #cf9236); color: #fff; box-shadow: 0 4px 12px rgba(230,162,60,0.3); }
.switch-icon { background: linear-gradient(135deg, #9060eb, #7b4fd4); color: #fff; box-shadow: 0 4px 12px rgba(144,96,235,0.3); }
.stat-info { flex: 1; min-width: 0; }
.stat-title { font-size: 13px; color: #909399; margin-bottom: 4px; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; }
.stat-value.small { font-size: 15px; }

/* 主卡片 */
.card-block { border-radius: 12px; margin-bottom: 0; height: calc(100vh - 340px); display: flex; flex-direction: column; transition: box-shadow 0.25s ease; }
.card-block :deep(.el-card__body) { flex: 1; overflow-y: auto; padding: 16px; }
.card-header { display: flex; align-items: center; gap: 8px; font-weight: 600; }

/* 类别列表 */
.class-list { max-height: calc(100vh - 460px); overflow-y: auto; }
.class-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; cursor: pointer; border-radius: 6px; transition: all 0.2s ease; margin-bottom: 2px; }
.class-item:hover { background: #ecf5ff; transform: translateX(2px); }
.class-item.active { background: #ecf5ff; font-weight: 600; color: var(--el-color-primary); }
.class-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; margin-right: 8px; }

/* 图片网格 */
.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
.image-item { text-align: center; border-radius: 10px; overflow: hidden; background: #fff; transition: all 0.25s ease; border: 1px solid #ebeef5; }
.image-item:hover { transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0,0,0,0.12); border-color: var(--el-color-primary-light); }
.thumb { width: 100%; height: 140px; cursor: pointer; }
.img-name { font-size: 11px; color: #909399; padding: 6px 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: center; }
</style>
