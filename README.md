# TeamPilot

TeamPilot 是一个面向中小型团队的项目任务进度管理系统，提供项目管理、任务看板、人员管理、仪表盘分析，以及 AI 辅助分配和风险分析能力。

## 功能概览

- 项目管理：项目列表、详情、进度跟踪
- 任务看板：Kanban 拖拽、子任务拆解、进度记录
- 人员管理：成员列表、能力画像、技能维度
- 数据仪表盘：任务总览、项目风险、团队负载
- AI 辅助：任务分解、风险分析、能力分析、任务分配建议
- 权限控制：登录认证、角色与权限管理

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia + ECharts |
| 后端 | FastAPI + SQLAlchemy 2.0 + asyncpg |
| 数据库 | PostgreSQL 16 |
| 部署 | Docker Compose |

## 环境要求

### 一键部署

- Linux 服务器
- Docker
- Docker Compose

`deploy.sh` 会尽量自动安装 Docker / Docker Compose，并自动补齐部署所需的密钥与管理员密码。

### 本地开发

- Python `3.11`
- Node.js `20.19+`
- PostgreSQL `16`

说明：

- 后端当前容器基础镜像：`python:3.11-slim`
- 前端当前构建镜像：`node:20-alpine`
- 前端依赖要求的 Node 范围：`^20.19.0 || >=22.12.0`

## 一键部署

### 1. 获取代码

```bash
git clone https://github.com/Ssshake1996/teampilot.git
cd teampilot
```

### 2. 准备部署配置

如果仓库根目录没有 `deploy.env`，脚本会自动根据 `deploy.env.example` 生成一份。
`deploy.env` 应作为当前服务器的本地部署配置保留，不建议提交回仓库。

建议至少检查这些配置项：

- `POSTGRES_PASSWORD`
- `CORS_ORIGINS`
- `BACKEND_PORT`
- `FRONTEND_PORT`
- `SEED_DEMO_USERS=false`

参考模板见 [deploy.env.example](deploy.env.example)。

### 3. 执行部署

```bash
bash deploy.sh
```

部署脚本会执行这些动作：

- 检查并安装 Docker / Docker Compose
- 自动生成 `JWT_SECRET_KEY`
- 自动生成 `AI_ENCRYPTION_KEY`
- 自动生成管理员初始密码（占位值或留空时）
- 构建并启动前后端与数据库容器
- 等待后端健康检查通过，失败时直接退出

### 4. 部署完成后

- 前端地址：`http://<服务器IP>:<FRONTEND_PORT>`
- API 文档：`http://<服务器IP>:<BACKEND_PORT>/docs`
- 初始管理员账号：来自 `deploy.env` 中的 `ADMIN_USERNAME / ADMIN_PASSWORD`

注意：

- 当前不再使用固定默认口令 `admin / admin123`
- 建议首次登录后立刻修改管理员密码
- 生产环境建议将 `CORS_ORIGINS` 改成正式域名

## 数据迁移

项目已提供数据库迁移辅助脚本：

```bash
scripts/migrate_db.sh export backups/teampilot_$(date +%Y%m%d_%H%M%S).sql.gz
scripts/migrate_db.sh import backups/teampilot_YYYYMMDD_HHMMSS.sql.gz
```

推荐迁移步骤：

1. 在旧服务器暂停写入或安排维护窗口
2. 执行导出命令
3. 把备份文件和新的 `deploy.env` 拷到新服务器
4. 在新服务器运行 `bash deploy.sh`
5. 执行导入命令
6. 验证后端健康检查和登录

更完整的生产部署与迁移说明见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 本地开发

### 后端

```bash
cd backend

pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx \
  cryptography python-multipart aiosqlite

cat > .env << 'EOF'
DATABASE_URL=sqlite+aiosqlite:///./teampilot.db
JWT_SECRET_KEY=dev-secret-key
CORS_ORIGINS=["http://localhost:5173"]
EOF

uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认访问地址：

```text
http://localhost:5173
```

开发模式下前端会把 `/api` 代理到 `http://localhost:8000`。

## 测试与构建

### 前端构建

```bash
cd frontend
npm run build
```

### 后端测试

```bash
cd backend
pip install pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v
```

## 项目结构

```text
teampilot/
├── backend/                # FastAPI 后端
├── frontend/               # Vue 3 前端
├── docs/                   # 部署、维护、开发文档
├── deploy.sh               # 一键部署脚本
├── deploy.env.example      # 部署配置模板
├── docker-compose.yml      # 容器编排
└── README.md               # 项目入口文档
```

## 相关文档

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)：生产部署与服务器迁移
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md)：运维维护
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)：开发说明
- [docs/API.md](docs/API.md)：接口文档
- [CLAUDE.md](CLAUDE.md)：项目上下文说明

## 当前说明

- 根目录 `README.md` 是项目主入口文档
- 不使用 `READER.md`

## License

MIT
