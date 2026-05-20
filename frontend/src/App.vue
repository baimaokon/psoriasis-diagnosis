<!--
App.vue — Vue 根组件
────────────────────
仅提供 <router-view /> 占位，由 Vue Router 根据 URL 动态渲染对应页面组件。
不包含任何业务逻辑，所有路由分发由 router/index.js 处理。
-->
<template>
  <router-view />
</template>

