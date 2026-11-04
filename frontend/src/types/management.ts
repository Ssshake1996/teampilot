import type { Task } from './models'

export interface ManagedTask extends Task {
  owner_id: string | null
  owner_name: string | null
  reviewer_id: string | null
  reviewer_name: string | null
  review_status: string
  needs_owner: boolean
  open_issue_count: number
  handover_pending: boolean
}
export interface TaskGovernance {
  owner_id: string; owner_name: string; reviewer_id: string; reviewer_name: string
  acceptance_criteria: string; deliverable_url: string | null; deliverable_note: string | null
  review_status: string; review_note: string | null; handover_accepted_at: string | null
}
export interface TaskIssue {
  id: string; task_id: string; title: string; reason: string; owner_id: string; owner_name: string
  reporter_id: string; next_action: string; due_at: string; state: 'open' | 'resolved'
  resolution: string | null; resolved_at: string | null; is_overdue: boolean; escalation_owner_id: string | null
}
export interface PlanChange {
  id: string; actor_id: string; actor_name: string; before_json: Record<string, unknown>
  after_json: Record<string, unknown>; reason: string; created_at: string
}
export interface TaskManagementDetail {
  task: ManagedTask; governance: TaskGovernance | null; issues: TaskIssue[]; changes: PlanChange[]
  needs_owner: boolean; can_manage: boolean; can_deliver: boolean; can_review: boolean; can_accept_handover: boolean
}
export interface CapacityUser { user_id: string; full_name: string; available_hours: number | null; allocated_hours: number; gap_hours: number | null; note: string }
export interface Allocation { id: string; task_id: string; task_title: string; project_id: string; user_id: string; hours: number; week_start: string; excluded_from_total?: boolean }
export interface CapacityPlan { week_start: string; users: CapacityUser[]; allocations: Allocation[]; totals: { available_hours: number; allocated_hours: number; over_capacity_hours: number } }
export interface Milestone { id: string; project_id: string; name: string; owner_id: string; due_date: string; task_ids: string[]; completed_tasks: number; total_tasks: number; is_overdue: boolean }
export interface Dependency { id: string; predecessor_id: string; successor_id: string; predecessor_title: string; successor_title: string; is_blocked: boolean; is_upstream_late: boolean }
export interface PlanBaseline { id: string; label: string; created_at: string; tasks: { task_id: string; title: string; baseline_deadline: string | null; current_deadline: string | null; baseline_hours: number | null; current_hours: number | null; changed: boolean }[] }
export interface Commitment { id: string; project_id: string; task_id: string; task_title: string; week_start: string; owner_id: string; expected_outcome: string; outcome_note: string; status: 'committed' | 'delivered' | 'missed'; signed_off_at: string | null }
export interface Retrospective { id: string; project_id: string; week_start: string; summary: string; decisions: string; action_tasks: { task_id: string; title: string; owner_id: string; deadline: string | null; status: string }[] }
export interface ReportHistory { id: string; report_type: 'daily' | 'weekly'; generated_at: string; summary: string }
export interface ProjectAccess { visibility: 'company' | 'private'; can_manage: boolean; can_write: boolean; owner_id: string; can_transfer_owner: boolean }
