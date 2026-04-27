import type { ProjectStatus, TaskStatus, TaskPriority } from './enums'

export interface User {
  id: string
  username: string
  full_name: string
  role: string
  department: string | null
  bio: string | null
  avatar_url: string | null
  is_active: boolean
  created_at: string
}

export interface Project {
  id: string
  name: string
  goal: string | null
  description: string | null
  status: ProjectStatus
  owner_id: string
  start_date: string | null
  end_date: string | null
  created_at: string
  task_count: number
  completed_count: number
  member_count: number
}

export interface Task {
  id: string
  project_id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assignee_name: string | null
  assignee_ids: string[]
  assignee_names: string[]
  creator_id: string
  parent_task_id: string | null
  estimated_hours: number | null
  actual_hours: number | null
  start_date: string | null
  deadline: string | null
  completed_at: string | null
  signed_off_by_id: string | null
  signed_off_by_name: string | null
  signed_off_at: string | null
  sort_order: number
  created_at: string
  updated_at: string
  progress_pct: number
  is_deleted: boolean
  deleted_at: string | null
}

export interface TaskProgress {
  id: string
  task_id: string
  user_id: string
  user_name: string | null
  progress_pct: number
  note: string | null
  hours_spent: number | null
  created_at: string
}

export interface Skill {
  id: string
  name: string
  category: string | null
  description: string | null
}

export interface DataConnector {
  id: string
  name: string
  key: string
  description: string | null
  base_url: string
  auth_type: 'none' | 'bearer' | 'api_key' | 'basic' | 'dynamic_token'
  auth_config_json: Record<string, any>
  headers_json: Record<string, any>
  timeout_seconds: number
  verify_tls: boolean
  is_enabled: boolean
  created_at: string
  updated_at: string
}

export interface TaskDataSkill {
  id: string
  task_id: string
  connector_id: string | null
  connector_name: string | null
  created_by_id: string
  confirmed_by_id: string | null
  confirmed_at: string | null
  natural_language: string
  skill_json: Record<string, any>
  status: 'draft' | 'confirmed'
  created_at: string
  updated_at: string
}

export interface SkillRun {
  id: string
  task_data_skill_id: string
  task_id: string
  actor_id: string
  status: 'success' | 'failed'
  request_json: Record<string, any>
  response_json: Record<string, any>
  metrics_json: Record<string, any>
  ai_analysis_json: Record<string, any>
  suggested_progress_pct: number | null
  suggested_note: string | null
  error_message: string | null
  created_at: string
}

export interface UserSkill {
  skill_id: string
  skill_name: string
  category: string | null
  proficiency: number
}

export interface CapabilityProfile {
  user_id: string
  summary: string | null
  ai_analysis: {
    strengths: string[]
    growth_areas: string[]
    recommended_task_types: string[]
    summary: string
    overall_rating: number
  } | null
  performance_score: number | null
  on_time_rate: number | null
  last_analyzed_at: string | null
}

export interface OverviewStats {
  total_tasks: number
  in_progress_tasks: number
  overdue_tasks: number
  completion_rate: number
}

export interface TeamWorkload {
  user_id: string
  full_name: string
  avatar_url: string | null
  assigned_tasks: number
  in_progress_tasks: number
  completed_tasks: number
  overdue_tasks: number
}

export interface RecentActivity {
  id: string
  user_name: string
  task_title: string
  project_name: string
  progress_pct: number
  note: string | null
  created_at: string
}

export interface ProjectMember {
  user_id: string
  full_name: string
  role_in_project: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
