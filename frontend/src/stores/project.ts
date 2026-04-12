import { defineStore } from 'pinia'
import { ref } from 'vue'
import { projectsApi } from '@/api/projects'
import type { Project } from '@/types/models'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const total = ref(0)
  const loading = ref(false)
  const currentProject = ref<Project | null>(null)

  async function fetchProjects(page = 1, pageSize = 20) {
    loading.value = true
    try {
      const res = await projectsApi.list(page, pageSize)
      projects.value = res.data.items
      total.value = res.data.total
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: string) {
    const res = await projectsApi.get(id)
    currentProject.value = res.data
  }

  return { projects, total, loading, currentProject, fetchProjects, fetchProject }
})
