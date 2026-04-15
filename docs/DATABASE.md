# TeamPilot 数据库结构说明

当前生产部署使用 PostgreSQL 16，本地开发和测试可使用 SQLite。仓库暂未补齐完整 Alembic 版本迁移流程，因此后端启动时会执行轻量 schema 同步：

- 自动创建缺失表。
- 如果旧 `users` 表仍包含 `email` 列，会删除该列。
- 如果 `users` 表缺少 `bio` 列，会添加 `bio TEXT`。
- 会把旧任务状态 `BACKLOG/TODO/IN_REVIEW` 归并为当前三态 `NOT_STARTED/IN_PROGRESS/DONE`。
- 如果 `tasks` 表缺少会签字段，会添加 `signed_off_by_id` 和 `signed_off_at`。

生产升级前仍应先备份 PostgreSQL。

## users

用户表当前字段如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `username` | VARCHAR(50) | 登录用户名，唯一 |
| `hashed_password` | VARCHAR(255) | 密码哈希 |
| `full_name` | VARCHAR(100) | 显示姓名 |
| `role` | VARCHAR(50) | 角色名，支持内置和自定义角色 |
| `department` | VARCHAR(100), nullable | 分组/部门 |
| `bio` | TEXT, nullable | 个人介绍，AI 派单、任务预估和能力分析会作为参考 |
| `avatar_url` | VARCHAR(500), nullable | 头像地址 |
| `is_active` | BOOLEAN | 是否启用 |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

说明：

- 当前不再保存邮箱字段。
- 注册和登录只依赖 `username`。
- 删除人员是软删除，将 `is_active` 置为 false，以保留任务、项目和进度历史。

## tasks

任务表当前保留一个内部 `status` 字段，但业务状态只使用三种：

| 状态值 | 前端显示 | 规则 |
|------|------|------|
| `not_started` / `NOT_STARTED` | 待开始 | 未会签完成，且 `start_date` 晚于当前时间 |
| `in_progress` / `IN_PROGRESS` | 进行中 | 未会签完成，且任务已到开始时间或未设置开始时间 |
| `done` / `DONE` | 已完成 | 任务进度达到 100% 后，由管理员或拥有 `task.signoff` 权限的角色会签确认 |

任务完成不再通过手动修改状态完成。成员提交进度到 100% 后，任务进入“待会签”的操作状态；会签接口写入：

| 字段 | 类型 | 说明 |
|------|------|------|
| `signed_off_by_id` | UUID, nullable | 会签确认人 |
| `signed_off_at` | TIMESTAMP, nullable | 会签确认时间 |
| `completed_at` | TIMESTAMP, nullable | 会签确认后同步写入的完成时间 |

说明：

- PostgreSQL 旧枚举值会在后端启动时同步到新的三态枚举。
- SQLite 旧状态字符串会在后端启动时直接更新为新状态字符串。
- 任务进展仍保存在 `task_progress` 表，群消息导入和手动反馈都会写入同一张历史表。

## 权限相关

`role_permissions` 保存角色到权限码的映射。前端通过 `GET /api/v1/permissions/me` 获取当前用户有效权限，后端通过 `require_permission(...)` 执行接口级校验。

任务完成会签使用 `task.signoff` 权限。后端启动时会把已有角色权限里的旧 `task.status` 自动替换为 `task.signoff`。

## AI 相关

`users.bio` 会进入以下 AI 上下文：

- 任务分配推荐
- 任务工时预估和候选人推荐
- 人员能力分析
