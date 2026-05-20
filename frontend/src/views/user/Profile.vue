<!--
Profile.vue — 用户端个人中心页
───────────────────────────────
路由：/user/profile
功能：展示用户基本信息（用户名、角色、注册时间），修改密码。
后端对接：routes/auth.py → GET /api/auth/profile
-->
<template>
  <div class="profile-container">
    <el-card class="profile-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <el-icon :size="20" color="#409eff"><User /></el-icon>
          <span class="header-title">个人中心</span>
        </div>
      </template>

      <div class="profile-content">
        <div class="avatar-section">
          <el-avatar :size="80" class="user-avatar">
            <el-icon :size="40"><UserFilled /></el-icon>
          </el-avatar>
          <h2 class="username">{{ user.username }}</h2>
          <el-tag
            :type="user.role === 1 ? 'danger' : 'primary'"
            effect="dark"
            size="large"
          >
            {{ user.role === 1 ? '管理员' : '普通用户' }}
          </el-tag>
        </div>

        <el-divider />

        <el-descriptions :column="1" border size="large">
          <el-descriptions-item>
            <template #label>
              <div class="desc-label">
                <el-icon><Key /></el-icon>
                <span>用户 ID</span>
              </div>
            </template>
            <span class="info-value">{{ user.id }}</span>
          </el-descriptions-item>
          <el-descriptions-item>
            <template #label>
              <div class="desc-label">
                <el-icon><User /></el-icon>
                <span>用户名</span>
              </div>
            </template>
            <span class="info-value">{{ user.username }}</span>
          </el-descriptions-item>
          <el-descriptions-item>
            <template #label>
              <div class="desc-label">
                <el-icon><Postcard /></el-icon>
                <span>角色</span>
              </div>
            </template>
            <el-tag :type="user.role === 1 ? 'danger' : 'primary'" effect="plain">
              {{ user.role === 1 ? '管理员' : '普通用户' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item>
            <template #label>
              <div class="desc-label">
                <el-icon><Calendar /></el-icon>
                <span>注册时间</span>
              </div>
            </template>
            <span class="info-value">{{ user.created_at }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="actions">
          <el-button type="primary" size="large" @click="$router.push('/user/diagnose')">
            <el-icon><Aim /></el-icon>
            开始诊断
          </el-button>
          <el-button type="warning" size="large" plain @click="$router.push('/user/records')">
            <el-icon><List /></el-icon>
            查看记录
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive } from "vue";
import { ElMessage } from "element-plus";
import {
  User, UserFilled, Key, Postcard, Calendar, Aim, List
} from '@element-plus/icons-vue';
import { profile } from "@/api/auth";

const user = reactive({
  id: "",
  username: "",
  role: 0,
  created_at: "",
});

onMounted(async () => {
  try {
    const res = await profile();
    const data = res.data || {};
    Object.assign(user, data);
  } catch (error) {
    ElMessage.error("获取个人信息失败");
  }
});
</script>

<style scoped>
.profile-container {
  max-width: 520px;
  margin: 0 auto;
}

.profile-card {
  border-radius: 16px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
}

.user-avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.username {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  margin: 0;
}

.desc-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.info-value {
  font-weight: 500;
  color: #606266;
}

.actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 24px;
  flex-wrap: wrap;
}

.actions .el-button {
  min-width: 140px;
}

@media (max-width: 576px) {
  .actions {
    flex-direction: column;
  }

  .actions .el-button {
    width: 100%;
  }
}
</style>
