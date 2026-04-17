# TeamPilot 数据库说明

## 当前数据库策略

- 生产环境默认使用 PostgreSQL 16
- 本地开发和测试可以使用 SQLite
- 当前仓库不再维护“启动时自动兼容旧字段/旧状态/旧权限”的迁移逻辑
- 当前项目定位为实验性项目；如果字段结构有破坏性变化，推荐做法是：
  1. 先备份
  2. 再重建或执行显式迁移

## users

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `username` | VARCHAR(50) | 登录用户名，唯一 |
| `hashed_password` | VARCHAR(255) | 密码哈希 |
| `full_name` | VARCHAR(100) | 显示姓名 |
| `role` | VARCHAR(50) | 角色名 |
| `department` | VARCHAR(100), nullable | 部门/分组 |
| `bio` | TEXT, nullable | 个人介绍，AI 分析与派单参考 |
| `avatar_url` | VARCHAR(500), nullable | 头像地址 |
| `is_active` | BOOLEAN | 是否启用 |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

说明：

- 不再保存邮箱字段
- 登录与注册只依赖 `username`
- 删除成员采用停用方式，保留历史任务与进展

## tasks

当前任务状态只保留三态：

| 状态值 | 说明 |
|------|------|
| `not_started` | `start_date` 晚于当前时间，且未会签完成 |
| `in_progress` | 已到开始时间或未设置开始时间，且未会签完成 |
| `done` | 进度 100% 且已会签确认 |

任务会签相关字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `signed_off_by_id` | UUID, nullable | 会签确认人 |
| `signed_off_at` | TIMESTAMP, nullable | 会签确认时间 |
| `completed_at` | TIMESTAMP, nullable | 完成时间 |

## task_assignees

任务负责人使用多负责人模型：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | UUID | 任务 ID |
| `user_id` | UUID | 成员 ID |

说明：

- 当前负责人以 `task_assignees` 为准
- 不再保留旧的单负责人兼容字段语义

## task_progress

任务进度历史统一写入 `task_progress`：

- 手动提交进展
- 群消息粘贴后确认同步的进展
- 后续 AI 导入进展

## role_permissions

角色权限通过 `role_permissions` 保存，后端接口使用 `require_permission(...)` 校验。

## AI 相关上下文

以下信息会进入 AI 上下文：

- `users.bio`
- `user_skills`
- `task_progress`
- `task_assignees`
- 项目和任务树信息
