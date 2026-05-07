<template>
  <el-card class="upload-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <el-icon :size="20" color="#409eff"><Picture /></el-icon>
        <span class="header-title">图像上传与诊断</span>
      </div>
    </template>

    <div class="upload-section">
      <el-upload
        class="upload-area"
        drag
        :auto-upload="false"
        :show-file-list="false"
        accept=".jpg,.jpeg,.png,.bmp,.webp"
        :on-change="handleSelectFile"
      >
        <div class="upload-content">
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-text">
            <p class="main-text">拖拽文件到此处，或点击选择图像</p>
            <p class="sub-text">支持 JPG、PNG、BMP、WEBP 格式</p>
          </div>
        </div>
      </el-upload>

      <div v-if="fileName" class="file-info">
        <el-tag type="success" effect="plain" size="large">
          <el-icon><Document /></el-icon>
          {{ fileName }}
        </el-tag>
      </div>

      <div class="action-section">
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          :disabled="!file"
          class="diagnose-btn"
          @click="$emit('diagnose', file)"
        >
          <el-icon v-if="!loading"><Aim /></el-icon>
          {{ loading ? '诊断中...' : '开始智能诊断' }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref } from "vue";
import { Picture, UploadFilled, Document, Aim } from '@element-plus/icons-vue';

const emit = defineEmits(['diagnose']);

const file = ref(null);
const fileName = ref("");
const loading = defineModel('loading');

const handleSelectFile = (uploadFile) => {
  file.value = uploadFile.raw;
  fileName.value = uploadFile.name;
};

defineExpose({ reset: () => { file.value = null; fileName.value = ""; } });
</script>

<style scoped>
.card-header { display: flex; align-items: center; gap: 8px; }
.header-title { font-size: 16px; font-weight: 600; color: #303133; }
.upload-card { border-radius: 12px; margin-bottom: 20px; }
.upload-section { display: flex; flex-direction: column; gap: 16px; }
.upload-area { width: 100%; }
.upload-area :deep(.el-upload-dragger) { padding: 40px 20px; border-radius: 12px; transition: all 0.3s ease; }
.upload-area :deep(.el-upload-dragger:hover) { border-color: #409eff; background: #f0f7ff; }
.upload-content { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.upload-icon { font-size: 48px; color: #409eff; }
.upload-text { text-align: center; }
.main-text { font-size: 15px; color: #303133; margin: 0 0 4px 0; font-weight: 500; }
.sub-text { font-size: 12px; color: #909399; margin: 0; }
.file-info { display: flex; justify-content: center; }
.file-info .el-tag { font-size: 14px; padding: 8px 16px; }
.action-section { display: flex; justify-content: center; }
.diagnose-btn { width: 100%; height: 48px; font-size: 16px; font-weight: 500; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; transition: all 0.3s ease; }
.diagnose-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 8px 16px rgba(102, 126, 234, 0.4); }
</style>
