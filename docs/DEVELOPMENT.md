# TeamPilot 开发说明

## 适用环境

- Ubuntu `20.04.5+`
- Windows `11+`

## 运行时要求

- Python `3.11`
- Node.js `20.19+` 或 `22.12+`
- PostgreSQL `16` 可选

说明：

- 本地默认推荐直接使用 SQLite，不强制依赖 PostgreSQL
- 前端当前 Node 版本要求来自 [frontend/package.json](../frontend/package.json)
- Ubuntu 20.04 的默认软件源通常不满足 Node 版本要求，建议用 `nvm`

## Ubuntu 20.04.5+ 本地开发

### 1. 安装 Python 3.11

```bash
python3 --version
```

如果不是 3.11，请先安装 Python 3.11。

### 2. 安装 Node.js

推荐：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install 20.19.0
nvm use 20.19.0
```

### 3. 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx \
  cryptography python-multipart aiosqlite pytest pytest-asyncio
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000
```

如果只做本地开发，确认 `backend/.env` 使用 SQLite：

```env
DATABASE_URL=sqlite+aiosqlite:///./teampilot.db
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

## Windows 11+ 本地开发

### 1. 安装 Python 3.11

建议使用官方安装包，安装时勾选“Add Python to PATH”。

验证：

```powershell
python --version
```

### 2. 安装 Node.js

建议使用官方安装包或：

```powershell
winget install OpenJS.NodeJS.LTS
```

验证：

```powershell
node -v
npm -v
```

### 3. 启动后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic `
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx `
  cryptography python-multipart aiosqlite pytest pytest-asyncio
Copy-Item ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

如果你本地不装 PostgreSQL，确认 `backend/.env` 使用 SQLite。

### 4. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

## 测试

```bash
cd backend
pytest tests/ -v
```

## 构建

```bash
cd frontend
npm run build
```

## 当前开发约束

- 登录与注册只使用 `username`
- 不再维护邮箱字段
- 任务负责人使用统一分配表：`assignments(kind='task_assignee')`
- 任务状态只保留三态：`NOT_STARTED / IN_PROGRESS / DONE`
- 当前仓库不再维护“启动时兼容旧数据结构”的自动迁移逻辑
- 如果字段结构发生破坏性变化，默认做法是备份后重建，不做旧数据兼容
