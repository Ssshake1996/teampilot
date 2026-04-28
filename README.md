# TeamPilot

TeamPilot 是一个面向中小团队的项目与任务进度管理系统，包含项目管理、任务看板、人员管理、进展汇总、日报巡检和多种 AI 辅助能力。

## 功能概览

- 项目管理：项目列表、项目详情、成员管理、任务树
- 任务管理：任务列表、任务看板、子任务拆解、进度记录、会签完成
- 进展更新：支持粘贴群消息，由 AI 识别项目和任务并生成待确认更新
- 任务数据 Skill：支持用白话描述内部平台 API，生成可执行 Skill，采集外部证据后采纳为任务进展
- 人员管理：成员列表、个人介绍、技能维度、能力分析
- 权限控制：登录认证、角色权限、菜单和接口校验
- AI 辅助：任务分配建议、任务估时、任务拆解、项目计划生成、日报巡检、风险分析、会签建议、项目复盘
- 报告发送：巡检报告支持日报、周报刷新，并可通过 SMTP 邮件发送

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Vue Query |
| 后端 | FastAPI + SQLAlchemy 2.0 + asyncpg |
| 数据库 | PostgreSQL 16 / SQLite |
| 部署 | Docker Compose |

## 支持环境

### 部署环境

- Ubuntu `20.04.5+`
- Docker Engine
- Docker Compose Plugin

说明：
- 仓库根目录的 `deploy.sh` 是 Linux Bash 脚本，面向 Ubuntu 服务器部署。
- 当前没有为原生 Windows Server 提供一键部署脚本。

### 本地开发环境

- Ubuntu `20.04.5+` 或 Windows `11+`
- Python `3.11`
- Node.js `20.19+` 或 `22.12+`
- PostgreSQL `16` 可选；本地开发默认可直接使用 SQLite

说明：
- 前端依赖在 [frontend/package.json](frontend/package.json) 中声明的 Node 范围是 `^20.19.0 || >=22.12.0`
- Ubuntu 20.04 自带的软件源通常拿不到满足要求的 Node 版本，建议使用 `nvm` 或 NodeSource 安装
- Windows 11 建议使用官方 Python 安装包 + Node.js 官方安装包，或使用 `winget`

## 快速开始

### 1. 获取代码

```bash
git clone https://github.com/Ssshake1996/teampilot.git
cd teampilot
```

### 2. Ubuntu 服务器一键部署

```bash
bash deploy.sh
```

部署脚本会：

- 检查并尽量安装 Docker / Docker Compose
- 自动生成 `deploy.env`
- 自动补齐 `JWT_SECRET_KEY`、`AI_ENCRYPTION_KEY`、`ADMIN_PASSWORD`
- 构建并启动前端、后端和 PostgreSQL
- 等待后端健康检查通过

部署完成后：

- 前端：`http://<服务器IP>:<FRONTEND_PORT>`
- API 文档：`http://<服务器IP>:<BACKEND_PORT>/docs`

### 3. 本地开发

完整说明见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

后端：

```bash
cd backend
python -m venv .venv
```

前端：

```bash
cd frontend
npm install
npm run dev
```

开发模式下前端默认访问地址：

```text
http://localhost:5173
```

## 本地开发建议

- Ubuntu 20.04.5+：
  - Python：系统包或 `deadsnakes`
  - Node：`nvm install 20.19.0`
- Windows 11+：
  - Python：官方安装包，勾选加入 PATH
  - Node：官方安装包或 `winget install OpenJS.NodeJS.LTS`
  - PostgreSQL：官方安装包或 Docker Desktop

## 数据库说明

- 生产部署默认使用 PostgreSQL 16
- 本地开发和测试可以直接使用 SQLite
- 当前仓库不再维护“启动时自动兼容旧字段/旧状态”的迁移逻辑
- 当前项目定位为实验性项目；如果模型字段有破坏性变化，推荐先备份，再重建或重灌数据，不再为旧数据做兼容补丁

数据库字段说明见 [docs/DATABASE.md](docs/DATABASE.md)。

## 测试与构建

前端构建：

```bash
cd frontend
npm run build
```

后端测试：

```bash
cd backend
pytest tests/ -v
```

## 数据重建

如果需要重建演示数据：

```bash
cd backend
python seed_demo.py
python seed_new_projects.py
```

说明：
- `seed_demo.py` 会清空并重建当前数据库
- `seed_new_projects.py` 会在现有库上追加演示项目

## 相关文档

- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)：开发环境与本地运行
- [docs/USER_MANUAL.md](docs/USER_MANUAL.md)：TeamPilot 使用说明书
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)：Ubuntu 服务器部署与迁移
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md)：运维与排障
- [docs/DATABASE.md](docs/DATABASE.md)：数据库字段与约束
- [docs/API.md](docs/API.md)：接口说明

## License

MIT
