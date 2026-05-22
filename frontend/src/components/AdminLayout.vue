<!--
AdminLayout.vue — 管理端布局组件
────────────────────────────────
提供管理端的页面框架：左侧导航菜单 + 顶部标题栏 + <router-view> 内容区。
路由 /admin/* 下的所有子路由均渲染在此布局中。
依赖：store/modules/session.js（管理员名、登出）
-->
<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="title">银屑病辅助诊断管理端</div>
      <div class="menu">
        <el-button text @click="go('/admin/dashboard')">训练与监控</el-button>
        <el-button text @click="go('/admin/datasets')">数据集管理</el-button>
        <el-dropdown @command="handleCommand">
          <span class="user-info" style="cursor: pointer">
            {{ sessionStore.user?.username || '管理员' }}
            <el-icon><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="hasUserSession" command="switchUser">
                切换到普通用户
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

const hasUserSession = computed(() => hasRoleSession('0'));

const go = (path) => router.push(path);

const handleCommand = (command) => {
  if (command === 'logout') {
    logout();
  } else if (command === 'switchUser') {
    switchToUser();
  }
};

const switchToUser = () => {
  const success = sessionStore.switchRole('0');
  if (success) {
    router.push('/user/diagnose');
  } else {
    router.push('/login');
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
