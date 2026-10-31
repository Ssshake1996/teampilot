<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { Fold, Expand, Menu } from '@element-plus/icons-vue'
import AppSidebar from './AppSidebar.vue'
import { useAuthStore } from '@/stores/auth'
import { useWebSocketStore } from '@/stores/websocket'

const route = useRoute()
const auth = useAuthStore()
const socket = useWebSocketStore()
const mobile = useMediaQuery('(max-width: 760px)')
const collapsed = ref(localStorage.getItem('teampilot.sidebarCollapsed') === 'true')
const menuOpen = ref(false)
const section = computed(() => route.path.startsWith('/projects') ? '项目管理' : route.path.startsWith('/personnel') ? '人员管理' : route.path.startsWith('/settings') ? '系统设置' : '仪表盘')
watch(() => auth.token, token => token ? socket.connect() : socket.disconnect(), { immediate: true })
watch(() => route.fullPath, () => { menuOpen.value = false })
watch(collapsed, value => localStorage.setItem('teampilot.sidebarCollapsed', String(value)))
onUnmounted(socket.disconnect)
</script>

<template>
  <div class="app-layout">
    <AppSidebar v-if="!mobile" :collapsed="collapsed" />
    <el-drawer v-else v-model="menuOpen" direction="ltr" size="240px" :with-header="false" class="navigation-drawer">
      <AppSidebar @navigate="menuOpen = false" />
    </el-drawer>
    <div class="app-main">
      <header class="app-toolbar">
        <el-tooltip :content="mobile ? '打开导航' : collapsed ? '展开导航' : '收起导航'">
          <el-button :icon="mobile ? Menu : collapsed ? Expand : Fold" text circle :aria-label="mobile ? '打开导航' : '切换导航'" @click="mobile ? menuOpen = true : collapsed = !collapsed" />
        </el-tooltip>
        <span class="toolbar-section">{{ section }}</span>
        <span class="connection-state" :class="{ online: socket.connected }">{{ socket.connected ? '实时同步' : '连接中' }}</span>
      </header>
      <main class="app-content">
        <RouterView :key="route.path" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout { display: flex; height: 100dvh; overflow: hidden; }
.app-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.app-toolbar { height: 52px; flex: 0 0 52px; display: flex; align-items: center; gap: 10px; padding: 0 20px; background: white; border-bottom: 1px solid var(--border); }
.toolbar-section { font-size: 14px; font-weight: 600; }
.connection-state { margin-left: auto; font-size: 12px; color: var(--muted); }
.connection-state::before { content: ''; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #c98730; margin-right: 6px; }
.connection-state.online::before { background: #27936d; }
.app-content { flex: 1; min-height: 0; overflow: auto; padding: 20px 24px; background: var(--canvas); }
@media (max-width: 760px) { .app-content { padding: 16px 12px; } .app-toolbar { padding: 0 12px; } }
</style>
