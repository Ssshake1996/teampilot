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
  assignee_id: string | null
  assignee_name: string | null
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
