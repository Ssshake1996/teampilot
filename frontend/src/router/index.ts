import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/login/LoginView.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/',
      component: () => import('@/components/layout/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/dashboard/DashboardView.vue'),
        },
        {
          path: 'projects',
          name: 'ProjectList',
          component: () => import('@/views/projects/ProjectListView.vue'),
        },
        {
          path: 'projects/:id',
          name: 'ProjectDetail',
          component: () => import('@/views/projects/ProjectDetailView.vue'),
        },
        {
          path: 'projects/:id/board',
          name: 'TaskBoard',
          component: () => import('@/views/tasks/TaskBoardView.vue'),
        },
        {
          path: 'projects/:id/tasks',
          name: 'TaskList',
          component: () => import('@/views/tasks/TaskListView.vue'),
        },
        {
          path: 'personnel',
          name: 'PersonnelList',
          component: () => import('@/views/personnel/PersonnelListView.vue'),
        },
        {
          path: 'personnel/:id',
          name: 'PersonnelDetail',
          component: () => import('@/views/personnel/PersonnelDetailView.vue'),
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/settings/SettingsView.vue'),
        },
      ],
    },
  ],
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()

  if (to.meta.requiresAuth !== false && !auth.isAuthenticated) {
    next('/login')
    return
  }

  if (auth.isAuthenticated && !auth.user) {
    await auth.fetchUser()
  } else if (auth.isAuthenticated) {
    await auth.fetchPermissions()
  }

  if (to.path === '/login' && auth.isAuthenticated) {
    next('/dashboard')
    return
  }

  next()
})

export default router
