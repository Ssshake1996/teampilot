<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { projectsApi } from '@/api/projects'
import type { Project } from '@/types/models'
import { ProjectStatus } from '@/types/enums'
import type { FormInstance } from 'element-plus'

const router = useRouter()

const projects = ref<Project[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = ref({
  name: '',
  description: '',
  start_date: '',
  end_date: '',
})

const rules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

const statusTagType: Record<string, string> = {
  [ProjectStatus.PLANNING]: 'info',
  [ProjectStatus.ACTIVE]: 'success',
  [ProjectStatus.PAUSED]: 'warning',
  [ProjectStatus.COMPLETED]: '',
  [ProjectStatus.ARCHIVED]: 'danger',
}

const statusLabel: Record<string, string> = {
  [ProjectStatus.PLANNING]: '规划中',
  [ProjectStatus.ACTIVE]: '进行中',
  [ProjectStatus.PAUSED]: '已暂停',
  [ProjectStatus.COMPLETED]: '已完成',
  [ProjectStatus.ARCHIVED]: '已归档',
}

function progressPercent(project: Project): number {
  if (!project.task_count || project.task_count === 0) return 0
  return Math.round((project.completed_count / project.task_count) * 100)
}

async function fetchProjects() {
  loading.value = true
  try {
    const res = await projectsApi.list(1, 100)
    projects.value = res.data.items
  } catch {
    ElMessage.error('加载项目列表失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  form.value = { name: '', description: '', start_date: '', end_date: '' }
  dialogVisible.value = true
}

async function handleCreate() {
  if (!formRef.value) return
  await formRef.value.validate()
  submitting.value = true
  try {
    const payload: { name: string; description?: string; start_date?: string; end_date?: string } = {
      name: form.value.name,
    }
    if (form.value.description) payload.description = form.value.description
    if (form.value.start_date) payload.start_date = form.value.start_date
    if (form.value.end_date) payload.end_date = form.value.end_date
    await projectsApi.create(payload)
    ElMessage.success('项目创建成功')
    dialogVisible.value = false
    await fetchProjects()
  } catch {
    ElMessage.error('项目创建失败')
  } finally {
    submitting.value = false
  }
}

function goToBoard(id: string) {
  router.push(`/projects/${id}/board`)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return dateStr.slice(0, 10)
}

onMounted(() => {
  fetchProjects()
})
</script>

<template>
  <div class="project-list-view">
    <div class="page-header">
      <h2>项目列表</h2>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建项目</el-button>
    </div>

    <div v-loading="loading" class="project-grid">
      <el-row :gutter="20">
        <el-col
          v-for="project in projects"
          :key="project.id"
          :xs="24"
          :sm="12"
          :md="8"
          :lg="6"
        >
          <el-card
            class="project-card"
            shadow="hover"
            @click="goToBoard(project.id)"
          >
            <div class="card-header">
              <span class="project-name">{{ project.name }}</span>
              <el-tag :type="(statusTagType[project.status] as any)" size="small">
                {{ statusLabel[project.status] || project.status }}
              </el-tag>
            </div>

            <p class="project-desc">{{ project.description || '暂无描述' }}</p>

            <div class="progress-section">
              <div class="progress-label">
                <span>任务进度</span>
                <span>{{ project.completed_count }}/{{ project.task_count }}</span>
              </div>
              <el-progress
                :percentage="progressPercent(project)"
                :stroke-width="8"
                :show-text="false"
              />
            </div>

            <div class="card-footer">
              <span class="member-info">
                <el-icon><svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path d="M512 512a192 192 0 1 0 0-384 192 192 0 0 0 0 384zm0 64C299.936 576 128 680.384 128 808v40a48 48 0 0 0 48 48h672a48 48 0 0 0 48-48v-40c0-127.616-171.936-232-384-232z" fill="currentColor"/></svg></el-icon>
                {{ project.member_count }} 成员
              </span>
              <span class="date-info">
                {{ formatDate(project.start_date) }} ~ {{ formatDate(project.end_date) }}
              </span>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-empty v-if="!loading && projects.length === 0" description="暂无项目" />
    </div>

    <!-- Create Project Dialog -->
    <el-dialog
      v-model="dialogVisible"
      title="新建项目"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="80px"
      >
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入项目名称" />
        </el-form-item>
        <el-form-item label="项目描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="请输入项目描述"
          />
        </el-form-item>
        <el-form-item label="开始日期" prop="start_date">
          <el-date-picker
            v-model="form.start_date"
            type="date"
            placeholder="选择开始日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束日期" prop="end_date">
          <el-date-picker
            v-model="form.end_date"
            type="date"
            placeholder="选择结束日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">确认创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.project-list-view {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.project-grid {
  min-height: 200px;
}

.project-card {
  margin-bottom: 20px;
  cursor: pointer;
  transition: transform 0.2s;
  border-radius: 8px;
}

.project-card:hover {
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.project-name {
  font-size: 16px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
}

.project-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 16px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-section {
  margin-bottom: 16px;
}

.progress-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #909399;
}

.member-info {
  display: flex;
  align-items: center;
  gap: 4px;
}

.date-info {
  font-size: 11px;
}
</style>
