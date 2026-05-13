<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <div class="logo">
          <el-icon :size="48" color="#fff"><Management /></el-icon>
        </div>
        <h1 class="title">管理后台</h1>
        <p class="subtitle">模型训练 · 数据监控 · 系统管理</p>
      </div>

      <el-card class="login-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon :size="20" color="#409eff"><Setting /></el-icon>
            <span class="card-title">管理员登录</span>
          </div>
        </template>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="0"
          @keyup.enter="submit"
        >
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入管理员账号"
              size="large"
              prefix-icon="User"
              clearable
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              prefix-icon="Lock"
              show-password
              clearable
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              class="login-btn"
              @click="submit"
            >
              {{ loading ? '登录中...' : '登 录' }}
            </el-button>
          </el-form-item>

          <div class="links">
            <el-button text type="primary" @click="$router.push('/login')">
              <el-icon><UserFilled /></el-icon>
              用户入口
            </el-button>
          </div>
        </el-form>
      </el-card>

    </div>

    <div class="background-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { UserFilled, Management, Setting } from '@element-plus/icons-vue';
import { useRouter } from "vue-router";
import { adminLogin } from "@/api/auth";
import { useSessionStore } from "@/store/modules/session";

const router = useRouter();
const sessionStore = useSessionStore();
const formRef = ref(null);
const loading = ref(false);

const form = reactive({
  username: "",
  password: "",
});

const rules = {
  username: [
    { required: true, message: '请输入管理员账号', trigger: 'blur' },
    { min: 3, message: '账号至少3位', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ]
};

const submit = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (!valid) return;

    loading.value = true;
    try {
      const res = await adminLogin(form);
      const responseData = res.data || {};
      sessionStore.setSession(responseData.token, responseData.user);
      ElMessage.success("登录成功");
      router.push("/admin/dashboard");
    } catch (error) {
      console.error('Admin login error:', error);
    } finally {
      loading.value = false;
    }
  });
};
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
  position: relative;
  overflow: hidden;
}

.login-box {
  position: relative;
  z-index: 10;
  width: 100%;
  max-width: 480px;
  padding: 20px;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
  color: white;
}

.logo {
  margin-bottom: 16px;
  animation: float 3s ease-in-out infinite;
}

.title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px 0;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.subtitle {
  font-size: 14px;
  opacity: 0.9;
  margin: 0;
}

.login-card {
  border-radius: 16px;
  backdrop-filter: blur(10px);
  background: rgba(255, 255, 255, 0.95);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.card-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.login-btn {
  width: 100%;
  font-size: 16px;
  font-weight: 500;
  height: 44px;
  background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
  border: none;
  transition: all 0.3s ease;
}

.login-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(30, 60, 114, 0.4);
}

.links {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 8px;
}

.links .el-button {
  font-size: 13px;
}

.demo-info {
  margin-top: 20px;
}

.demo-info :deep(.el-alert) {
  background: rgba(255, 255, 255, 0.9);
  border: none;
}

.background-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: none;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  animation: pulse 4s ease-in-out infinite;
}

.circle-1 {
  width: 350px;
  height: 350px;
  top: -120px;
  left: -120px;
  animation-delay: 0s;
}

.circle-2 {
  width: 250px;
  height: 250px;
  bottom: -80px;
  right: -80px;
  animation-delay: 1s;
}

.circle-3 {
  width: 180px;
  height: 180px;
  top: 40%;
  right: 15%;
  animation-delay: 2s;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.08;
  }
  50% {
    transform: scale(1.15);
    opacity: 0.15;
  }
}

@media (max-width: 768px) {
  .title {
    font-size: 24px;
  }

  .login-box {
    padding: 15px;
  }
}
</style>
