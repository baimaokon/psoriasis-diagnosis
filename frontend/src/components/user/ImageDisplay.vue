<template>
  <div class="image-item">
    <div class="img-header">
      <el-icon :color="icon === 'HotWater' ? '#f56c6c' : '#409eff'"><component :is="icon" /></el-icon>
      <span>{{ title }}</span>
    </div>
    <div class="img-wrapper">
      <img
        v-if="src && !hasError"
        :src="src"
        :alt="title"
        class="preview-img"
        @error="hasError = true"
        @load="hasError = false"
      />
      <div v-else-if="!src" class="empty-img">暂无图片</div>
      <el-alert v-else type="warning" :closable="false" title="图片加载失败，请检查网络或重试" show-icon />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';
import { Picture, HotWater } from '@element-plus/icons-vue';

const props = defineProps({ src: String, title: String, icon: String });
const hasError = ref(false);

// 🔑 关键修复：监听 src 变化，自动重置错误状态
watch(() => props.src, () => { hasError.value = false; });
</script>

<style scoped>
.image-item { display: flex; flex-direction: column; gap: 8px; }
.img-header { display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 500; color: #606266; }
.img-wrapper { border-radius: 8px; overflow: hidden; border: 2px solid #ebeef5; background: #f5f7fa; min-height: 200px; display: flex; align-items: center; justify-content: center; }
.preview-img { width: 100%; display: block; transition: transform 0.3s ease; }
.preview-img:hover { transform: scale(1.02); }
.empty-img { color: #909399; font-size: 13px; }
</style>
