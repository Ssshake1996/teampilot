# TeamPilot API 文档

启动后端后访问 **http://localhost:8000/docs** 查看交互式 Swagger UI。

## 认证

所有 API (除登录/注册外) 需要在 Header 中传递 JWT:

```
Authorization: Bearer <access_token>
```

### 获取 Token

```bash
# 登录
# 部署环境请使用 deploy.env 中的 ADMIN_USERNAME / ADMIN_PASSWORD
# 本地开发默认可使用 admin / admin123
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 返回: {"access_token":"eyJ...", "refresh_token":"eyJ...", "token_type":"bearer"}
```

前端会在 access token 过期后自动使用 `refresh_token` 续期；默认 refresh token 有效期为 90 天，可通过 `REFRESH_TOKEN_EXPIRE_DAYS` 调整。

### 注册

注册只需要用户名、姓名和密码，不需要邮箱：

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","full_name":"New User","password":"securepass"}'
```

用户响应字段包含：

```text
id, username, full_name, role, department, bio, avatar_url, is_active, created_at
```

其中 `bio` 是人员详情页展示的个人介绍。

## API 总览

| 模块 | 前缀 | 说明 |
|------|------|------|
| 认证 | `/api/v1/auth` | 注册、登录、刷新Token |
| 用户 | `/api/v1/users` | 用户管理、技能、工作量 |
| 项目 | `/api/v1/projects` | 项目CRUD、成员、任务树 |
| 任务 | `/api/v1/tasks` | 任务CRUD、三态状态、进度、会签、子任务 |
| 技能 | `/api/v1/skills` | 技能标签管理 |
| 能力 | `/api/v1/capabilities` | 能力档案 |
| 仪表盘 | `/api/v1/dashboard` | 统计、四象限、项目进度 |
| 报告 | `/api/v1/reports` | 巡检报告缓存、刷新、周报生成、邮件发送 |
| 数据 Skill | `/api/v1/data-connectors`, `/api/v1/tasks/{task_id}/data-skills` | 内部平台 API 连接器、任务数据采集 Skill、执行快照和采纳进展 |
| 权限 | `/api/v1/permissions` | 角色权限管理 |
| WebSocket | `/ws` | 建连后用首条认证消息发送 Token，不放 URL |

权限接口补充：

- `GET /api/v1/permissions/me`：返回当前用户的角色和有效权限，用于前端按钮显示。
- `GET /api/v1/permissions/catalog`、`GET/PUT/POST/DELETE /api/v1/permissions/roles`：需要 `system.role_manage` 权限。

项目状态由任务自动推导：无任务或任务未到开始时间为 `planning`，存在已开始未完成任务为 `active`，全部会签完成为 `completed`；`archived` 只由归档操作产生。

## 任务状态与会签

任务业务状态只对外显示三种：`not_started`（待开始）、`in_progress`（进行中）、`done`（已完成）。

- 待开始：未完成任务且 `start_date` 晚于当前时间，由后端自动判断。
- 进行中：未完成任务且已到开始时间，或未设置开始时间。
- 已完成：进度达到 100% 后，通过会签接口确认，后端自动写入完成状态。

直接修改任务状态的旧接口 `/api/v1/tasks/{task_id}/status` 仅保留兼容入口，当前会返回 400。完成任务请使用：

```bash
curl -X POST http://localhost:8000/api/v1/tasks/$TASK_ID/signoff \
  -H "Authorization: Bearer $TOKEN"
```

会签需要 `task.signoff` 权限，且任务当前进度必须为 100%。手动进度通过 `POST /api/v1/tasks/{task_id}/progress` 写入，也可采纳任务数据 Skill 的执行结果。

## 任务数据 Skill

任务数据 Skill 用于从公司内部平台 API 采集任务完成证据。用户在任务详情里描述数据来源，系统按确定性规则生成 Skill 草稿，测试执行后确认，后续可重复执行。执行结果只有在“采纳进展”后才会写入 `task_events`。

### 数据连接器

连接器由系统设置中的“数据连接器”维护，需要 `system.connector_manage` 权限。

```bash
curl -X POST http://localhost:8000/api/v1/data-connectors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"测试平台",
    "key":"test_platform",
    "base_url":"https://test-platform.internal",
    "auth_type":"bearer",
    "auth_config_json":{"token":"xxx"},
    "headers_json":{},
    "verify_tls":false,
    "is_enabled":true
  }'
```

动态认证平台使用 `dynamic_token`。系统会先调用 `token_url` 获取 token，再把 token 写入业务接口的 Header 或 Query，并按过期时间缓存复用：

```json
{
  "auth_type": "dynamic_token",
  "auth_config_json": {
    "token_url": "/api/auth/login",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "body": {"app_id": "xxx", "app_secret": "xxx"},
    "token_path": "$.data.access_token",
    "expires_in_path": "$.data.expires_in",
    "token_prefix": "Bearer",
    "target": "header",
    "target_name": "Authorization",
    "cache_seconds": 3600
  }
}
```

说明：
- `token_url` 可以是相对路径，也可以是完整 URL；相对路径会拼接连接器的 `base_url`。
- `token_path` 和 `expires_in_path` 使用简单 JSON 路径，例如 `$.data.access_token`。
- `target` 支持 `header` 或 `query`。
- token 缓存在后端进程内，服务重启后会重新获取。

### 任务 Skill 主流程

```bash
# 1. 根据白话说明生成 Skill 草稿
curl -X POST http://localhost:8000/api/v1/tasks/$TASK_ID/data-skills/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"natural_language":"这个任务的数据从测试平台获取。接口是 GET /api/test/feature/{feature_id}/summary。"}'

# 2. 确认 Skill
curl -X POST http://localhost:8000/api/v1/tasks/$TASK_ID/data-skills/$SKILL_ID/confirm \
  -H "Authorization: Bearer $TOKEN"

# 3. 执行采集。参数可为空，系统会先从任务标题和描述提取 feature_id。
curl -X POST http://localhost:8000/api/v1/tasks/$TASK_ID/data-skills/$SKILL_ID/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"params":{}}'

# 4. 采纳执行结果为任务进展
curl -X POST http://localhost:8000/api/v1/tasks/$TASK_ID/data-skills/runs/$RUN_ID/adopt \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 报告与邮件发送

项目管理页的“巡检报告”支持日报和周报。打开弹窗和切换类型只读取缓存；只有点击“刷新”才重新生成。

- 日报：每天 07:00 自动生成一次；手动刷新使用确定性规则。
- 周报：每周五 12:30 自动生成一次；手动刷新使用确定性规则，项目进展情况表覆盖所有未归档项目。
- 读取缓存：调用 `GET /api/v1/reports/snapshot?report_type=daily|weekly`。
- 手动刷新：调用 `POST /api/v1/reports/refresh`，不调用模型。
- 邮件发送：调用 `POST /api/v1/reports/send`。

日报和周报返回格式固定，确定性规则输出包含：

```text
summary, risky_projects, overdue_blocked_tasks,
progress_fast_top3, progress_slow_top3,
priority_tasks, signoff_pending,
source, source_label
```

其中 `summary` 是字符串，列表字段都是字符串数组。

周报额外包含：

```text
project_progress_table, completed_tasks, progress_updates, period_start, period_end
```

`project_progress_table` 每行包含 `project_name`, `progress_pct`, `weekly_progress`, `task_completion`, `overdue_tasks`, `risk_level`, `next_action`。

读取缓存示例：

```bash
curl http://localhost:8000/api/v1/reports/snapshot?report_type=weekly \
  -H "Authorization: Bearer $TOKEN"
```

手动刷新示例：

```bash
curl -X POST http://localhost:8000/api/v1/reports/refresh \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"report_type":"daily"}'
```

发送接口示例：

```bash
curl -X POST http://localhost:8000/api/v1/reports/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type":"daily",
    "recipients":["pm@example.com"],
    "report":{"summary":"今日巡检正常","risky_projects":["暂无风险"]}
  }'
```

后端需要配置 SMTP：

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=robot@example.com
SMTP_PASSWORD=your-password
SMTP_FROM_EMAIL=teampilot@example.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
REPORT_DEFAULT_RECIPIENTS=pm@example.com,lead@example.com
REPORT_TIMEZONE=Asia/Shanghai
```

如果请求里没有 `recipients`，后端会使用 `REPORT_DEFAULT_RECIPIENTS`。如果 SMTP 未配置，接口会返回 400 并说明缺失项。
