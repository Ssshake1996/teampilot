# TeamPilot 开发指南

## 开发环境搭建

### 后端

```bash
cd backend
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx \
  cryptography python-multipart aiosqlite

# 使用 SQLite 开发 (免安装 PostgreSQL)
echo 'DATABASE_URL=sqlite+aiosqlite:///./teampilot.db' > .env
echo 'JWT_SECRET_KEY=dev-secret' >> .env
echo 'CORS_ORIGINS=["http://localhost:5173"]' >> .env

uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 测试

```bash
cd backend
pip install pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v
```

## 代码结构

### 添加新 API

1. `backend/app/models/` - 添加 SQLAlchemy 模型
2. `backend/app/schemas/` - 添加 Pydantic schema
3. `backend/app/services/` - 添加业务逻辑
4. `backend/app/api/` - 添加路由处理器
5. `backend/app/api/router.py` - 注册路由
6. `backend/tests/` - 添加测试

### 添加前端页面

1. `frontend/src/views/` - 添加页面组件
2. `frontend/src/router/index.ts` - 添加路由
3. `frontend/src/api/` - 添加 API 调用
4. `frontend/src/types/` - 添加类型定义

### 修改 AI Prompt

两种方式:
- **运行时**: 系统设置 > AI Prompt Tab (管理员 Web UI 修改)
- **代码**: `backend/app/services/ai/prompts.py` (修改默认值)

## 数据库模型

```
User ──< Task (assignee)
User ──< ProjectMember >── Project
User ──< UserSkill >── Skill
User ──1 CapabilityProfile
Task >── Project
Task ──< TaskProgress
Task ──< TaskRequiredSkill >── Skill
RolePermission (role -> permissions JSON)
AIConfig (singleton, AI settings + custom prompts)
```
