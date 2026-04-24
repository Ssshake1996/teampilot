# TeamPilot 数据库说明

## 当前策略

- 生产环境默认使用 PostgreSQL 16，本地测试可使用 SQLite。
- 当前是实验阶段，破坏性表结构变更不做历史数据兼容；部署到旧库时建议先备份，再重建数据库或执行清库脚本。
- 启动时只负责创建当前模型缺失的表，不再维护旧字段、旧状态、旧关联表的兼容补丁。

## 核心表

### users

保存账号、角色、部门、个人介绍和 AI 能力档案字段。

关键字段：
- `username`, `hashed_password`, `full_name`, `role`, `department`, `bio`, `avatar_url`, `is_active`
- `capability_summary`, `capability_ai_analysis`, `performance_score`, `on_time_rate`, `last_analyzed_at`

说明：
- 注册和登录只依赖 `username`，不保存邮箱字段。
- 成员删除采用停用方式，保留历史任务、进展和会签记录。

### projects

保存项目基础信息：`name`, `goal`, `description`, `status`, `owner_id`, `start_date`, `end_date`。

### tasks

保存任务本体、任务树和会签状态。

关键字段：
- `project_id`, `parent_task_id`, `title`, `description`, `priority`
- `start_date`, `deadline`, `estimated_hours`, `actual_hours`
- `signed_off_by_id`, `signed_off_at`, `completed_at`
- `is_deleted`, `deleted_at`, `required_skills_json`, `sort_order`

任务状态只保留三类：
- `not_started`：开始时间晚于当前时间，且未会签完成。
- `in_progress`：已到开始时间或未设置开始时间，且未会签完成。
- `done`：进度达到 100% 后由有权限角色会签确认。

### assignments

统一保存项目成员和任务负责人，降低项目、任务、用户之间的耦合。

关键字段：
- `project_id`
- `task_id`：项目成员为空，任务负责人为对应任务 ID。
- `user_id`
- `kind`：`project_member` 或 `task_assignee`
- `role`：项目成员角色或任务分配角色。

说明：
- 项目人数按项目成员与未删除任务负责人去重统计。
- 任务负责人支持多人。
- 删除项目成员只删除显式项目成员关系，不影响该成员仍作为任务负责人的历史关系。

### task_events

统一保存任务事件历史，替代旧的单一进度表。

事件类型：
- `progress`：手动进度提交或 AI 进展更新确认后的记录。
- `signoff`：任务会签确认。
- `delete`：任务删除。
- `restore`：任务恢复。

关键字段：`task_id`, `actor_id`, `event_type`, `progress_pct`, `note`, `hours_spent`, `created_at`。

说明：
- 前端仍使用“进度历史”的接口名称，但后端数据来源是 `task_events`。
- 已删除任务不能继续提交进度。

### skills / user_skills

保存技能库和成员技能熟练度。

### system_settings

保存系统级 JSON 配置。

当前键：
- `ai_config`：AI 服务地址、模型、API Key、温度、最大 token，以及自定义 prompt。
- `role_permissions`：内置角色覆盖权限和自定义角色权限。

说明：
- `admin` 始终拥有全部权限，不允许被修改。
- `manager`、`member` 默认使用代码内置权限；如果 `role_permissions` 中存在同名角色，则使用配置覆盖。
- 自定义角色只保存在 `role_permissions` JSON 中，不再单独建表。

## AI 上下文

以下信息会进入 AI 分析上下文：
- `users.bio`
- `users` 中的能力档案字段
- `user_skills`
- `assignments`
- `task_events`
- 项目、任务树、任务进度和会签信息
