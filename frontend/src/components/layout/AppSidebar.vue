<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { DataAnalysis, FolderOpened, User, Setting, ArrowDown, Connection } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

defineProps<{ collapsed?: boolean }>()
const emit = defineEmits<{ navigate: [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const links = [
  { path: '/dashboard', label: '仪表盘', icon: DataAnalysis },
  { path: '/projects', label: '项目管理', icon: FolderOpened },
  { path: '/management', label: '团队协作', icon: Connection },
  { path: '/personnel', label: '人员管理', icon: User },
  { path: '/settings', label: '系统设置', icon: Setting },
]
const roleLabel = computed(() => ({ admin: '系统管理员', manager: '项目经理', member: '成员' })[auth.user?.role || 'member'])
function logout() { auth.logout(); router.push('/login') }
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <RouterLink to="/dashboard" class="sidebar-brand" @click="emit('navigate')"><span class="brand-mark">T</span><strong v-if="!collapsed">TeamPilot</strong></RouterLink>
    <nav class="sidebar-menu" aria-label="主导航">
      <el-tooltip v-for="link in links" :key="link.path" :content="link.label" :disabled="!collapsed" placement="right">
        <RouterLink :to="link.path" :aria-label="link.label" class="nav-link" :class="{ active: route.path.startsWith(link.path) }" @click="emit('navigate')">
          <el-icon :size="19"><component :is="link.icon" /></el-icon><span v-if="!collapsed">{{ link.label }}</span>
        </RouterLink>
      </el-tooltip>
    </nav>
    <el-dropdown trigger="click" class="sidebar-user">
      <button class="sidebar-user-btn" type="button" aria-label="账号菜单">
        <el-avatar :size="30">{{ auth.user?.full_name?.[0] || 'U' }}</el-avatar>
        <span v-if="!collapsed" class="sidebar-user-text"><strong>{{ auth.user?.full_name || '用户' }}</strong><small>{{ roleLabel }}</small></span>
        <el-icon v-if="!collapsed"><ArrowDown /></el-icon>
      </button>
      <template #dropdown><el-dropdown-menu><el-dropdown-item @click="logout">退出登录</el-dropdown-item></el-dropdown-menu></template>
    </el-dropdown>
  </aside>
</template>

<style scoped>
.sidebar { width: 216px; flex: 0 0 216px; height: 100%; background: #fff; border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.sidebar.collapsed { width: 68px; flex-basis: 68px; }
.sidebar-brand { height: 72px; display: flex; align-items: center; gap: 10px; padding: 0 20px; font-size: 19px; color: #203a3e; white-space: nowrap; }
.brand-mark { background: var(--brand); color: white; width: 28px; height: 28px; flex: 0 0 28px; border-radius: 6px; display: grid; place-items: center; font-size: 17px; font-weight: 700; }
.sidebar-menu { padding: 8px 10px; flex: 1; }
.nav-link { height: 44px; display: flex; align-items: center; gap: 12px; padding: 0 14px; margin-bottom: 6px; border-radius: 6px; font-size: 14px; color: #59666b; }
.nav-link:hover { background: #f3f6f7; }
.nav-link.active { background: #e7f3f1; color: #167267; font-weight: 600; }
.sidebar-user { border-top: 1px solid var(--border); padding: 14px 12px; }
.sidebar-user-btn { display: flex; align-items: center; gap: 10px; border: 0; background: transparent; cursor: pointer; width: 100%; text-align: left; color: var(--ink); }
.sidebar-user-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.sidebar-user-text strong { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sidebar-user-text small { font-size: 11px; color: var(--muted); }
.collapsed .sidebar-brand { padding: 0 20px; }
.collapsed .nav-link { padding: 0; justify-content: center; }
.collapsed .sidebar-user-btn { justify-content: center; }
</style>
