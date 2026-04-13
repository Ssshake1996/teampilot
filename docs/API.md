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

## API 总览

| 模块 | 前缀 | 说明 |
|------|------|------|
| 认证 | `/api/v1/auth` | 注册、登录、刷新Token |
| 用户 | `/api/v1/users` | 用户管理、技能、工作量 |
| 项目 | `/api/v1/projects` | 项目CRUD、成员、任务树 |
| 任务 | `/api/v1/tasks` | 任务CRUD、状态、进度、子任务 |
| 技能 | `/api/v1/skills` | 技能标签管理 |
| 能力 | `/api/v1/capabilities` | 能力档案 |
| 仪表盘 | `/api/v1/dashboard` | 统计、四象限、项目进度 |
| AI | `/api/v1/ai` | 推荐、分析、风险、配置 |
| 权限 | `/api/v1/permissions` | 角色权限管理 |
| WebSocket | `/ws/{token}` | 实时事件推送 |

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
