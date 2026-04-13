# TeamPilot — 项目任务进度管理系统

## 项目概述

公司级项目人员管理平台，支持任务看板、进度追踪、AI 能力画像和智能派单。

## 技术栈

- **前端**: Vue 3.5 + TypeScript + Pinia 3 + Element Plus 2.13 + ECharts + vuedraggable
- **后端**: Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + asyncpg
- **数据库**: PostgreSQL 16
- **AI**: OpenAI 兼容 API (可配置 `base_url + api_key`，支持 Claude / GPT / Deepseek / Ollama)

## 目录结构

```text
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # 应用入口
│   │   ├── config.py        # Pydantic Settings 配置
│   │   ├── database.py      # 数据库连接
│   │   ├── dependencies.py  # 依赖注入 (auth, db session)
│   │   ├── models/          # SQLAlchemy ORM 模型
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   ├── api/             # 路由处理器
│   │   ├── services/        # 业务逻辑层
│   │   │   └── ai/          # LLM 客户端和 AI 服务
│   │   ├── websocket/       # WebSocket 连接管理
│   │   └── utils/           # 工具 (JWT, 分页)
│   └── alembic/             # 数据库迁移
├── frontend/         # Vue 3 前端
│   └── src/
│       ├── api/             # Axios API 调用层
│       ├── stores/          # Pinia 状态管理
│       ├── views/           # 页面组件
│       ├── components/      # 公共组件
│       └── types/           # TypeScript 类型定义
└── docker-compose.yml
```

## 启动开发环境

### 前置条件

- Python `3.11`
- Node.js `20.19+`
- PostgreSQL `16`

说明：

- 后端运行镜像为 `python:3.11-slim`
- 前端构建镜像为 `node:20-alpine`
- 前端依赖实际要求的 Node 范围是 `^20.19.0 || >=22.12.0`

### 后端

```bash
cd backend
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx \
  cryptography python-multipart aiosqlite

# 复制 .env.example 为 .env 并修改数据库连接
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：http://localhost:8000/docs

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问：http://localhost:5173

## 关键设计决策

- **AI 集成**: 不依赖任何 SDK，用 `httpx` 直连 OpenAI 兼容 API，在 `backend/app/services/ai/llm_client.py`
- **认证**: JWT Access Token (30min) + Refresh Token (7days)，token 存 `localStorage`
- **实时更新**: WebSocket 推送任务状态变更到前端
- **看板拖拽**: `vuedraggable` 实现跨列拖放

## 数据库模型关系

```text
User 1──N Task (assignee)
User 1──N ProjectMember N──1 Project
User 1──N UserSkill N──1 Skill
User 1──1 CapabilityProfile
Task N──1 Project
Task 1──N TaskProgress
Task N──N Skill (required_skills via TaskRequiredSkill)
```

## API 前缀

所有 API 在 `/api/v1` 下，主要路由组：

- `/auth` - 认证
- `/users` - 用户管理
- `/projects` - 项目管理
- `/tasks` - 任务管理 (任务 CRUD 在 `/projects/{pid}/tasks` 和 `/tasks/{id}`)
- `/skills` - 技能标签
- `/capabilities` - 能力档案
- `/dashboard` - 仪表盘统计
- `/ai` - AI 推荐和分析

## 测试

```bash
cd backend
pip install pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v
```

## 常见修改指南

- **添加新的 API**: 在 `api/` 添加路由，在 `services/` 添加业务逻辑，在 `schemas/` 添加数据模型，并在 `api/router.py` 注册
- **添加新的数据表**: 在 `models/` 添加模型，在 `models/__init__.py` 导入，并运行 alembic 迁移
- **修改 AI Prompt**: 编辑 `services/ai/prompts.py`
- **添加前端页面**: 在 `views/` 添加组件，在 `router/index.ts` 添加路由
