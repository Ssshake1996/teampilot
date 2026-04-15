# TeamPilot 开发指南

## 开发环境

当前项目的实际开发版本建议如下：

- Python `3.11`
- Node.js `20.19+`
- PostgreSQL `16`

说明：

- 后端容器基础镜像是 `python:3.11-slim`
- 前端构建镜像是 `node:20-alpine`
- 前端依赖实际要求的 Node 范围是 `^20.19.0 || >=22.12.0`

## 后端开发

```bash
cd backend
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx \
  cryptography python-multipart aiosqlite

# 使用 SQLite 进行本地开发（无需额外安装 PostgreSQL）
# 可直接复制仓库根目录的 .env.example 到 backend/.env
copy ..\\.env.example .env
# 或手动创建等价配置
# echo 'DATABASE_URL=sqlite+aiosqlite:///./teampilot.db' > .env
# echo 'JWT_SECRET_KEY=dev-secret-key' >> .env
# echo 'AI_ENCRYPTION_KEY=dev-ai-encryption-key' >> .env
# echo 'CORS_ORIGINS=["http://localhost:5173"]' >> .env

uvicorn app.main:app --reload --port 8000
```

## 前端开发

```bash
cd frontend
npm install
npm run dev
```

## 测试

```bash
cd backend
pip install pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v
```

## 代码结构

## 用户字段约定

- 登录和注册只使用 `username`，不再采集或保存邮箱。
- `users.bio` 保存人员详情页的个人介绍。AI 派单、任务预估和能力分析会读取该字段作为成员背景参考。
- 开发库和生产 PostgreSQL 启动时都会自动补齐当前轻量 schema 变更：删除旧 `users.email`，添加缺失的 `users.bio`。
- 数据库表字段以 [DATABASE.md](DATABASE.md) 为准；修改模型时需要同步 ORM、Pydantic schema、前端类型、启动兼容迁移和字段回归测试。

### 新增后端 API

1. `backend/app/models/`：新增 SQLAlchemy 模型
2. `backend/app/schemas/`：新增 Pydantic schema
3. `backend/app/services/`：新增业务逻辑
4. `backend/app/api/`：新增路由处理
5. `backend/app/api/router.py`：注册路由
6. `backend/tests/`：补测试

### 新增前端页面

1. `frontend/src/views/`：新增页面组件
2. `frontend/src/router/index.ts`：新增路由
3. `frontend/src/api/`：新增 API 调用
4. `frontend/src/types/`：新增类型定义

### 修改 AI Prompt

有两种方式：

- 运行时：系统设置 > AI Prompt 页面中修改
- 代码方式：`backend/app/services/ai/prompts.py`

## 数据模型关系

```text
User --> Task (assignee)
User --> ProjectMember --> Project
User --> UserSkill --> Skill
User --> CapabilityProfile
User.bio --> AI task assignment / estimate / capability context
Task --> Project
Task --> TaskProgress
Task --> TaskRequiredSkill --> Skill
RolePermission (role -> permissions JSON)
AIConfig (singleton, AI settings + custom prompts)
```
