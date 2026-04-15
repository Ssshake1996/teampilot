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

# 返回: {"access_token":"eyJ...", "token_type":"bearer"}
```

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

其中 `bio` 是人员详情页的个人介绍，会被 AI 派单、任务预估和能力分析作为参考。

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
| AI | `/api/v1/ai` | 推荐、分析、风险、配置 |
| 权限 | `/api/v1/permissions` | 角色权限管理 |
| WebSocket | `/ws/{token}` | 实时事件推送 |

权限接口补充：

- `GET /api/v1/permissions/me`：返回当前用户的角色和有效权限，用于前端按钮显示。
- `GET /api/v1/permissions/catalog`、`GET/PUT/POST/DELETE /api/v1/permissions/roles`：需要 `system.role_manage` 权限。

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

会签需要 `task.signoff` 权限，且任务当前进度必须为 100%。进度由 `POST /api/v1/tasks/{task_id}/progress` 或群消息导入写入。

## AI 接口 (SSE 流式)

AI 接口使用 Server-Sent Events 流式返回:

```bash
curl -N http://localhost:8000/api/v1/ai/estimate-task \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id":"xxx","title":"任务标题","description":"描述"}'

# 返回:
# event: status
# data: {"message": "正在分析团队成员技能..."}
#
# event: result  
# data: {"estimated_hours": 8, "recommended_assignees": [...]}
```

### 群消息进展导入

项目管理页汇总栏右侧的“进展更新”按钮调用以下两步接口。默认识别范围是所有未归档项目中的未完成任务，适合一段群消息同时包含多个项目进展。

1. AI 识别预览：

```bash
curl -N http://localhost:8000/api/v1/ai/progress-import/preview \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"张三\n2026-04-16 18:00\n项目A任务完成到80%，项目B任务已完成"}'
```

返回 SSE `result`，包含 `updates` 和 `unmatched`。`updates` 中会给出匹配项目、匹配任务、进度百分比、进展说明和置信度。

2. 确认同步：

```bash
curl -X POST http://localhost:8000/api/v1/ai/progress-import/commit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"updates":[{"task_id":"xxx","progress_pct":80,"note":"任务A完成到80%","person_name":"张三","reported_at":"2026-04-16 18:00"}]}'
```

确认后会写入 `task_progress` 历史记录，并触发前端刷新。进度达到 100% 的任务仍需会签后才会标记为已完成。

### AI 项目搭建与管理助手

项目管理页还提供以下 AI 入口，用于减少计划搭建和日常巡检成本：

- `POST /api/v1/ai/project-plan/preview`：根据自然语言目标生成项目计划、任务树、负责人建议、工时和日期。
- `POST /api/v1/ai/project-plan/commit`：确认后创建项目和任务树。
- `POST /api/v1/ai/daily-brief`：跨未归档项目生成日报巡检，包含完成项、进行中、风险、建议动作和待会签候选。
- `POST /api/v1/ai/signoff-assist`：根据任务进展历史和子任务给出会签建议。
- `POST /api/v1/ai/project-retrospective`：根据项目任务树和进展历史生成项目复盘。

示例：

```bash
curl -N http://localhost:8000/api/v1/ai/project-plan/preview \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"两周内搭建内部项目进度管理系统，包含人员、权限、任务、AI进展识别"}'

curl -N http://localhost:8000/api/v1/ai/daily-brief \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```
