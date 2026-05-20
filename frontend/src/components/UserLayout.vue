<!--
UserLayout.vue — 用户端布局组件
────────────────────────────────
提供用户端的页面框架：顶部导航栏 + <router-view> 内容区。
导航栏包含：系统logo、诊断页入口、历史记录入口、用户信息、登出按钮。
路由 /user/* 下的所有子路由均渲染在此布局中。
依赖：store/modules/session.js（用户名、登出）
-->
<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="title">银屑病图像辅助诊断</div>
      <div class="menu">
        <el-button text @click="go('/user/diagnose')">图像诊断</el-button>
        <el-button text @click="go('/user/records')">历史记录</el-button>
        <el-button text @click="go('/user/profile')">个人信息</el-button>
        <el-dropdown @command="handleCommand">
          <span class="user-info" style="cursor: pointer">
            {{ sessionStore.user?.username || '用户' }}
            <el-icon><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人中心</el-dropdown-item>
              <el-dropdown-item v-if="hasAdminSession" command="switchAdmin" divided>
                切换到管理员
              </el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue';
import { ArrowDown } from '@element-plus/icons-vue';
import { useRouter } from "vue-router";
import { useSessionStore } from "@/store/modules/session";
import { hasRoleSession } from "@/utils/auth";

const router = useRouter();
const sessionStore = useSessionStore();

const hasAdminSession = computed(() => hasRoleSession('1'));

const go = (path) => router.push(path);

const handleCommand = (command) => {
  if (command === 'logout') {
    logout();
  } else if (command === 'profile') {
    go('/user/profile');
  } else if (command === 'switchAdmin') {
    switchToAdmin();
  }
};

const switchToAdmin = () => {
  const success = sessionStore.switchRole('1');
  if (success) {
    router.push('/admin/dashboard');
  } else {
    router.push('/admin/login');
  }
};

const logout = () => {
  const hasOtherSession = sessionStore.logoutCurrentRole();
  if (hasOtherSession) {
    if (sessionStore.role === '1') {
      router.push('/admin/dashboard');
    } else {
      router.push('/user/diagnose');
    }
  } else {
    router.push("/login");
  }
};
</script>

<style scoped>
.layout {
  min-height: 100vh;
  background: #f4f7fb;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e6ecf3;
  background: #fff;
}

.title {
  font-size: 18px;
  font-weight: 700;
  color: #1f2d3d;
}

.menu {
  display: flex;
  gap: 8px;
  align-items: center;
}

.user-info {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #409eff;
  font-size: 14px;
}

.main {
  padding: 20px;
}
</style>
