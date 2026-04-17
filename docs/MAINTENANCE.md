# TeamPilot 运维说明

## 适用范围

本手册面向 Ubuntu `20.04.5+` 上的 Docker Compose 部署。

## 日常操作

先加载部署环境变量：

```bash
set -a
. ./deploy.env
set +a
```

查看服务：

```bash
docker compose ps
docker compose logs -f
docker compose logs backend
docker compose logs db
```

重启服务：

```bash
docker compose restart
docker compose restart backend
docker compose restart frontend
```

停止与启动：

```bash
docker compose down
docker compose up -d
```

## 备份与恢复

导出：

```bash
scripts/migrate_db.sh export backups/teampilot_$(date +%Y%m%d_%H%M%S).sql.gz
```

导入：

```bash
scripts/migrate_db.sh import backups/teampilot_YYYYMMDD_HHMMSS.sql.gz
```

## 升级

```bash
cd /path/to/teampilot
git pull origin main
docker compose up -d --build
docker compose logs -f --tail=50
```

## 关于数据库结构变更

当前项目策略：

- 不再依赖“应用启动时自动兼容旧表结构”
- 不再维护旧字段、旧状态、旧权限的自动修补
- 如果升级涉及破坏性数据库变更，建议：
  1. 先备份 PostgreSQL
  2. 评估是否直接重建
  3. 如果要保留数据，单独编写显式迁移脚本

## 常见排障

后端健康检查：

```bash
curl "http://localhost:${BACKEND_PORT}/health"
```

数据库可用性：

```bash
docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

进入后端容器：

```bash
docker compose exec backend bash
```

查看数据库连接配置：

```bash
docker compose exec backend python -c "from app.config import settings; print(settings.database_url)"
```

## HTTPS

建议在前端容器前放 Nginx 或其他反向代理，并使用 HTTPS 暴露服务。

## 监控建议

可以用 systemd、crontab 或外部监控系统定时检查：

- `http://localhost:${BACKEND_PORT}/health`
- 前端首页 HTTP 返回码
- `docker compose ps` 容器状态
