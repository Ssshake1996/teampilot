import { defineStore } from 'pinia'
import { ref } from 'vue'
import { tasksApi } from '@/api/tasks'
import type { Task } from '@/types/models'
import { TaskStatus } from '@/types/enums'

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>([])
  const total = ref(0)
  const loading = ref(false)

  const tasksByStatus = (status: TaskStatus) =>
    tasks.value
      .filter((t) => t.status === status && !t.is_deleted)
      .sort((a, b) => a.sort_order - b.sort_order)

  async function fetchTasks(projectId: string, params?: Record<string, any>) {
    loading.value = true
    try {
      const res = await tasksApi.list(projectId, params)
      tasks.value = res.data.items
      total.value = res.data.total
    } finally {
      loading.value = false
    }
  }

  function updateTaskLocally(taskId: string, updates: Partial<Task>) {
    const idx = tasks.value.findIndex((t) => t.id === taskId)
    if (idx !== -1) {
      const currentTask = tasks.value[idx]
      if (!currentTask) return
      tasks.value[idx] = { ...currentTask, ...updates } as Task
    }
  }

  return { tasks, total, loading, tasksByStatus, fetchTasks, updateTaskLocally }
})
