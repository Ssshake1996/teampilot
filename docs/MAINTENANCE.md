# TeamPilot 运维说明

## 版本化迁移与本地备份

自 `20261005_01` 开始使用 Alembic 管理数据库版本。新库和未记录版本的现有整合版数据库都执行 `upgrade head`，不要对现有库直接 `stamp head`，否则会跳过字段和索引更新。此基线不负责迁移早期尚未整合 Assignment/TaskEvent 的其他历史结构。

在 `backend` 工作目录执行：

```powershell
python scripts/backup_database.py --output-dir backups
python -m alembic upgrade head
python -m alembic current
python -m pytest tests/ -q
```

SQLite 使用数据库 backup API 获取一致性快照，并执行 integrity_check；PostgreSQL 使用本机 `pg_dump` 的 custom archive，密码通过子进程环境传递，不放在命令行。备份包含敏感业务数据，必须限制访问，备份目录默认被 Git 忽略。PostgreSQL 备份还应定期在隔离数据库上用 `pg_restore` 做恢复演练。

本地默认 `AUTO_MIGRATE=true`，启动自动升级。生产环境推荐先停止写入、完成备份、单独运行迁移，再设置 `AUTO_MIGRATE=false` 启动，避免并发迁移。当前 WebSocket 连接管理器在进程内，部署须保持单个后端 worker；多 worker 实时同步需要另接 Redis 等跨进程事件总线。首次迁移保留现有记录，新增 reopen 审计类型和最新进展查询索引；仅对原本没有权重列的库初始化均分权重，不覆盖已有自定义权重，不删除会签历史。基线降级被拒绝，恢复旧版本必须使用验证过的备份，不能仅删除 alembic_version。

生产环境必须关闭 `SEED_DEMO_USERS`、替换默认 JWT/管理员密码，使用 HTTPS 并限制数据库访问。浏览器已从明文记住密码改为仅记住账号，但 JWT 目前仍在 localStorage，尚未切换为 HttpOnly Cookie。

GitHub Actions 已加入后端测试、PostgreSQL 16 新库迁移/重复升级、前端单元测试及构建。工作流文件存在不等于远程已经执行，需推送后检查 Actions 结果。

现有密码栈使用 Passlib 1.7，暂时锁定本次已验证的 bcrypt 4.0.1，避免新装环境自动升级到不兼容的 bcrypt 版本。升级密码库应另做旧账号哈希兼容性验证，不直接删除该约束。

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

结构变更使用显式 Alembic 迁移。先在 `backend` 执行 `python scripts/backup_database.py`，再运行 `python -m alembic upgrade head`。启动时 `AUTO_MIGRATE=true` 会执行同一升级；生产可关闭自动迁移，改由部署步骤执行。不自动重建或清空业务数据。

DSH 草稿迁移为 `20261005_02`。旧 AI 模块、路由和 Vue 控件已移除；历史 AI 数据不读不写，密钥不迁入 DSH。插件运行和打包见 [插件说明](../plugins/packages/dsh-teampilot/README.md)。插件卸载或重启会撤销内存中的业务登录与批准凭据，业务库不会被删除。

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
docker compose exec backend python -c "from app.config import settings; from sqlalchemy.engine import make_url; print(make_url(settings.database_url).render_as_string(hide_password=True))"
```

## HTTPS

建议在前端容器前放 Nginx 或其他反向代理，并使用 HTTPS 暴露服务。

## 监控建议

可以用 systemd、crontab 或外部监控系统定时检查：

- `http://localhost:${BACKEND_PORT}/health`
- 前端首页 HTTP 返回码
- `docker compose ps` 容器状态
