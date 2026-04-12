<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()
const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/projects')) return '/projects'
  if (path.startsWith('/personnel')) return '/personnel'
  if (path.startsWith('/settings')) return '/settings'
  return '/dashboard'
})
</script>

<template>
  <div class="sidebar">
    <div class="sidebar-logo">
      <h2>TeamPilot</h2>
    </div>
    <el-menu :default-active="activeMenu" router class="sidebar-menu">
      <el-menu-item index="/dashboard">
        <el-icon><i class="el-icon-data-analysis" /></el-icon>
        <span>仪表盘</span>
      </el-menu-item>
      <el-menu-item index="/projects">
        <el-icon><i class="el-icon-folder" /></el-icon>
        <span>项目管理</span>
      </el-menu-item>
      <el-menu-item index="/personnel">
        <el-icon><i class="el-icon-user" /></el-icon>
        <span>人员管理</span>
      </el-menu-item>
      <el-menu-item index="/settings">
        <el-icon><i class="el-icon-setting" /></el-icon>
        <span>系统设置</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<style scoped>
.sidebar {
  width: 220px;
  height: 100vh;
  background: #304156;
  color: #fff;
  display: flex;
  flex-direction: column;
}
.sidebar-logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #263445;
}
.sidebar-logo h2 {
  font-size: 18px;
  color: #409eff;
}
.sidebar-menu {
  flex: 1;
  border-right: none;
  background: #304156;
}
.sidebar-menu :deep(.el-menu-item) {
  color: #bfcbd9;
}
.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-menu-item.is-active) {
  color: #fff;
  background: #263445;
}
</style>
