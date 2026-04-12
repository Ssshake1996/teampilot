export enum UserRole {
  ADMIN = 'admin',
  MANAGER = 'manager',
  MEMBER = 'member',
}

export enum ProjectStatus {
  PLANNING = 'planning',
  ACTIVE = 'active',
  PAUSED = 'paused',
  COMPLETED = 'completed',
  ARCHIVED = 'archived',
}

export enum TaskStatus {
  BACKLOG = 'backlog',
  TODO = 'todo',
  IN_PROGRESS = 'in_progress',
  IN_REVIEW = 'in_review',
  DONE = 'done',
}

export enum TaskPriority {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  URGENT = 'urgent',
}

export const TaskStatusLabel: Record<TaskStatus, string> = {
  [TaskStatus.BACKLOG]: '待办池',
  [TaskStatus.TODO]: '待处理',
  [TaskStatus.IN_PROGRESS]: '进行中',
  [TaskStatus.IN_REVIEW]: '审核中',
  [TaskStatus.DONE]: '已完成',
}

export const TaskPriorityLabel: Record<TaskPriority, string> = {
  [TaskPriority.LOW]: '低',
  [TaskPriority.MEDIUM]: '中',
  [TaskPriority.HIGH]: '高',
  [TaskPriority.URGENT]: '紧急',
}

export const PriorityColor: Record<TaskPriority, string> = {
  [TaskPriority.LOW]: '#67C23A',
  [TaskPriority.MEDIUM]: '#E6A23C',
  [TaskPriority.HIGH]: '#F56C6C',
  [TaskPriority.URGENT]: '#F56C6C',
}
