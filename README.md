# TeamPilot — 项目任务进度管理系统

一个面向中型团队 (20-100人) 的项目人员管理平台，支持个人动态刷新工作进展、工作量评估、AI 能力画像和智能任务分配。

## 核心功能

### 1. 任务看板 + 进度追踪
- 五列 Kanban 看板：待办池 → 待处理 → 进行中 → 审核中 → 已完成
- 拖拽式状态变更，实时 WebSocket 推送
- 个人进度提交（进度百分比 + 工时记录 + 备注）
- 截止时间管理，逾期自动标红

### 2. 人员能力画像
- 技能标签体系（分类管理，1-5级熟练度）
- ECharts 能力雷达图可视化
- AI 自动生成能力分析报告（优势、成长方向、推荐任务类型）
- 历史绩效记录：按时完成率、工时偏差、综合评分

### 3. 智能任务分配
- AI 根据技能匹配度 + 当前负载 + 历史绩效推荐最佳人选
- 支持配置任意 OpenAI 兼容 API（Claude、GPT、Deepseek、本地模型）
- 管理后台可配置 API Base URL、API Key、模型名称等

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Element Plus + ECharts + Pinia |
| 后端 | Python + FastAPI + SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL 16 |
| 实时通信 | WebSocket |
| AI | OpenAI 兼容 API (httpx 直连) |

## 快速开始

### 1. 环境要求
- Python >= 3.10
- Node.js >= 18
- PostgreSQL 16

### 2. 数据库准备
```bash
# 创建数据库
createdb project_mgmt
```

### 3. 启动后端
```bash
cd backend
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic-settings "python-jose[cryptography]" "passlib[bcrypt]" httpx \
  cryptography python-multipart

# 编辑 .env 文件配置数据库连接
cp ../.env.example .env

# 初始化数据库（需要先运行 alembic）
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端
```bash
cd frontend
npm install
npm run dev
```

### 5. 使用 Docker Compose（推荐）
```bash
docker-compose up -d
```

访问 http://localhost:5173

## API 文档

启动后端后访问 http://localhost:8000/docs 查看 Swagger UI。

## 项目结构

详见 [CLAUDE.md](./CLAUDE.md)

## 许可证

MIT
