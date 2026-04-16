<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/projects')) return '/projects'
  if (path.startsWith('/personnel')) return '/personnel'
  if (path.startsWith('/settings')) return '/settings'
  return '/dashboard'
})

const roleNames: Record<string, string> = {
  admin: '系统管理员',
  manager: '项目经理',
  member: '成员',
}
const roleLabel = computed(() => roleNames[auth.user?.role || 'member'] || '成员')

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="sidebar">
    <div class="sidebar-logo">
      <div class="brand-block">
        <h2>TeamPilot</h2>
        <span class="brand-role">{{ roleLabel }}</span>
      </div>
      <el-dropdown trigger="click" class="sidebar-user">
        <button class="sidebar-user-btn" type="button">
          <el-avatar :size="28">{{ auth.user?.full_name?.[0] || 'U' }}</el-avatar>
          <span class="sidebar-user-text">
            <span class="sidebar-user-name">{{ auth.user?.full_name || '用户' }}</span>
            <span class="sidebar-user-action">账号操作</span>
          </span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
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
  min-height: 118px;
  padding: 14px 14px 12px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 12px;
  background: #263445;
}
.brand-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 2px 0 0;
}
.sidebar-logo h2 {
  font-size: 18px;
  color: #409eff;
  margin: 0;
  line-height: 1.2;
}
.brand-role {
  font-size: 12px;
  line-height: 1.2;
  color: #bfcbd9;
}
.sidebar-user {
  width: 100%;
}
.sidebar-user-btn {
  width: 100%;
  height: 46px;
  border: none;
  border-radius: 6px;
  background: #304156;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  cursor: pointer;
}
.sidebar-user-btn:hover {
  background: #263445;
}
.sidebar-user-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.25;
}
.sidebar-user-name {
  max-width: 128px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: #fff;
}
.sidebar-user-action {
  font-size: 11px;
  color: #bfcbd9;
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
