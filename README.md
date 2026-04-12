# TeamPilot - 项目任务进度管理系统

面向中型团队(20-100人)的项目人员管理平台，支持任务看板、进度追踪、AI能力画像和智能任务分配。

## 功能概览

- **项目管理** - 树形任务列表，逐级展开，内联编辑，进度追踪
- **任务看板** - 五列 Kanban 拖拽，子任务分解，AI 智能分配
- **人员管理** - 分组管理，技能雷达图，AI 能力分析
- **仪表盘** - 四象限任务视图，项目风险预警，团队负荷
- **AI 集成** - 智能派单、工时预估、风险分析、能力评估
- **权限管理** - 自定义角色，细粒度权限控制(24项权限)

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Element Plus + ECharts + Pinia |
| 后端 | Python + FastAPI + SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL 16 |
| AI | OpenAI 兼容 API (支持 Claude/GPT/Deepseek/Ollama 等) |
| 部署 | Docker Compose |

---

## 一键部署 (推荐)

### 前置要求

- Linux 服务器 (Ubuntu 20.04+, CentOS 7+, 等)
- 2GB+ 内存
- Docker 和 Docker Compose (脚本会自动安装)

### 部署步骤

```bash
# 1. 克隆代码
git clone https://github.com/Ssshake1996/teampilot.git
cd teampilot

# 2. 编辑配置文件 (可选，默认配置即可运行)
cp deploy.env deploy.env.bak  # 备份
vim deploy.env                # 修改数据库密码、JWT密钥等

# 3. 一键部署
bash deploy.sh
```

部署完成后:
- 前端: `http://你的服务器IP`
- API 文档: `http://你的服务器IP:8000/docs`
- 默认账号: `admin / admin123`

### 配置说明 (deploy.env)

```env
# 数据库
POSTGRES_USER=teampilot          # 数据库用户名
POSTGRES_PASSWORD=teampilot2026  # 数据库密码 (生产环境请修改)
POSTGRES_DB=teampilot            # 数据库名

# JWT 认证
JWT_SECRET_KEY=xxx               # 部署脚本会自动生成随机密钥

# AI 配置 (可在 Web UI 中配置，也可在此预设)
AI_API_BASE_URL=                 # 如 https://api.openai.com/v1
AI_API_KEY=                      # API Key
AI_MODEL_NAME=                   # 如 gpt-4o, claude-sonnet-4-20250514, qwen3.5-plus

# 端口
BACKEND_PORT=8000                # 后端 API 端口
FRONTEND_PORT=80                 # 前端页面端口
```

### 管理命令

```bash
docker compose logs -f           # 查看实时日志
docker compose restart           # 重启所有服务
docker compose down              # 停止所有服务
docker compose up -d --build     # 重新构建并启动
```

---

## 手动部署 (开发环境)

### 前置要求

- Python >= 3.10
- Node.js >= 18
- PostgreSQL 16 (或使用 SQLite 开发)

### 后端

```bash
cd backend

# 安装依赖
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx \
  cryptography python-multipart

# 配置 (使用 SQLite 快速开发)
cat > .env << 'EOF'
DATABASE_URL=sqlite+aiosqlite:///./teampilot.db
JWT_SECRET_KEY=dev-secret-key
CORS_ORIGINS=["http://localhost:5173"]
EOF

# 启动 (自动建表 + 创建默认用户)
uvicorn app.main:app --reload --port 8000

# (可选) 导入测试数据
pip install aiosqlite
python seed_demo.py
python seed_new_projects.py
```

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器 (自动代理 API 到 localhost:8000)
npm run dev
```

访问 http://localhost:5173

### 测试

```bash
cd backend
pip install pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v
```

---

## 项目结构

```
teampilot/
├── deploy.sh              # 一键部署脚本
├── deploy.env             # 部署配置文件
├── docker-compose.yml     # Docker Compose 编排
├── CLAUDE.md              # AI Agent 项目上下文文件
│
├── backend/
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py        # FastAPI 入口
│   │   ├── config.py      # 配置管理
│   │   ├── models/        # 数据库模型 (7个表)
│   │   ├── schemas/       # 请求/响应模型
│   │   ├── api/           # API 路由 (9个模块)
│   │   ├── services/      # 业务逻辑
│   │   │   └── ai/        # AI 服务 (5个功能)
│   │   └── websocket/     # 实时推送
│   ├── tests/             # 31个测试用例
│   ├── seed_demo.py       # 测试数据生成
│   └── seed_new_projects.py
│
└── frontend/
    ├── Dockerfile
    ├── nginx.conf          # Nginx 反向代理配置
    └── src/
        ├── api/            # API 调用层
        ├── stores/         # Pinia 状态管理
        ├── views/          # 页面组件
        └── types/          # TypeScript 类型
```

## 文档

| 文档 | 说明 |
|------|------|
| [README.md](README.md) | 项目介绍、快速部署 |
| [CLAUDE.md](CLAUDE.md) | AI Agent 项目上下文 (技术架构、目录结构、API 设计) |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | 运维维护手册 (备份恢复、故障排查、安全配置、监控) |
| [docs/API.md](docs/API.md) | API 接口文档 (认证、接口总览、SSE 流式) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 开发指南 (环境搭建、代码结构、添加新功能) |

## 许可证

MIT
