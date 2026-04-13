# TeamPilot 运维维护手册

## 目录

1. [日常运维](#日常运维)
2. [数据备份与恢复](#数据备份与恢复)
3. [版本更新](#版本更新)
4. [故障排查](#故障排查)
5. [性能调优](#性能调优)
6. [安全配置](#安全配置)

---

## 日常运维

建议先加载当前部署配置，避免命令里写死数据库名、用户名或端口：

```bash
set -a
. ./deploy.env
set +a
```

### 查看服务状态

```bash
docker compose ps              # 查看容器状态
docker compose logs -f         # 实时日志
docker compose logs backend    # 只看后端日志
docker compose logs db         # 只看数据库日志
```

### 重启服务

```bash
docker compose restart            # 重启所有
docker compose restart backend    # 只重启后端
docker compose restart frontend   # 只重启前端
```

### 停止/启动

```bash
docker compose down      # 停止所有服务(数据保留)
docker compose up -d     # 启动所有服务
```

---

## 数据备份与恢复

### 手动备份

```bash
# 推荐：使用仓库自带脚本导出数据库
scripts/migrate_db.sh export backups/teampilot_$(date +%Y%m%d_%H%M%S).sql.gz

# 或者手动备份数据库
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup_$(date +%Y%m%d_%H%M%S).sql

# 备份整个数据卷
docker compose down
docker run --rm -v teampilot_pgdata:/data -v $(pwd):/backup alpine \
  tar czf /backup/pgdata_$(date +%Y%m%d).tar.gz /data
docker compose up -d
```

### 定时备份 (crontab)

```bash
# 每天凌晨3点自动备份
echo "0 3 * * * cd /path/to/teampilot && set -a && . ./deploy.env && set +a && docker compose exec -T db pg_dump -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\" > /backups/teampilot_\$(date +\%Y\%m\%d).sql" | crontab -
```

### 恢复数据

```bash
# 推荐：使用仓库自带脚本恢复数据库
scripts/migrate_db.sh import backups/teampilot_YYYYMMDD_HHMMSS.sql.gz

# 从SQL文件恢复
cat backup.sql | docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
```

---

## 版本更新

### 常规更新

```bash
cd /path/to/teampilot

# 拉取最新代码
git pull origin main

# 重建并重启
docker compose up -d --build

# 查看是否启动正常
docker compose logs -f --tail=50
```

### 数据库迁移

如果更新涉及数据库结构变更，请先确认仓库里是否已经补齐 Alembic 配置。

当前仓库状态：

- 已安装 `alembic` Python 包
- 已存在 `backend/alembic/` 目录
- 但未包含可直接执行的 `alembic.ini` 和版本迁移脚本

因此，下面的 `alembic upgrade head` 只有在你们后续补齐 Alembic 配置后才适用。
在当前仓库里，自动建表仍主要依赖应用启动时的 `Base.metadata.create_all()`。

如果只是空库首次启动或开发环境重建表，可使用下面的建表脚本：

```bash
# 进入后端容器
docker compose exec backend bash

# 开发/空库场景重建表(会按当前模型创建缺失表)
python -c "
import asyncio
from app.database import engine
from app.models import Base
async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(migrate())
"
```

如果要把数据库结构升级流程规范化，建议后续补齐：

- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/*.py`
- 以及与发布流程配套的迁移命令

---

## 故障排查

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 页面白屏 | 前端构建失败 | `docker compose logs frontend` 查看错误 |
| 登录失败 | JWT密钥变更 | 清除浏览器缓存重新登录 |
| AI功能报错 | API配置错误 | 系统设置 > AI配置 > 测试连接 |
| 数据库连接失败 | DB未启动 | `docker compose restart db` |
| 任务列表不显示 | 后端500错误 | `docker compose logs backend` 查看错误 |

### 日志排查步骤

```bash
# 1. 查看哪个服务有问题
docker compose ps

# 2. 看具体错误
docker compose logs --tail=100 backend

# 3. 进入容器调试
docker compose exec backend bash
python -c "from app.config import settings; print(settings.database_url)"
```

### 健康检查

```bash
# 后端健康检查
curl "http://localhost:${BACKEND_PORT}/health"

# 数据库连接检查
docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# 前端检查
curl -o /dev/null -sw "%{http_code}" "http://localhost:${FRONTEND_PORT}"
```

---

## 性能调优

### 数据库优化

```bash
# 进入数据库
docker compose exec db psql -U "$POSTGRES_USER" "$POSTGRES_DB"

# 查看慢查询
SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;

# 分析表
ANALYZE tasks;
ANALYZE users;
```

### 后端调优

在 `deploy.env` 中调整:

```env
# 增加 uvicorn workers (默认1个,建议 CPU核数*2+1)
# 需要修改 backend/Dockerfile 的 CMD:
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 内存优化

```bash
# 查看各容器资源使用
docker stats

# 限制容器内存 (在 docker-compose.yml 中添加)
# deploy:
#   resources:
#     limits:
#       memory: 512M
```

---

## 安全配置

### 生产环境必做

1. **修改管理员密码**: 首次登录后立即修改 `deploy.env` 中生成的管理员密码
2. **修改JWT密钥**: 部署脚本会自动生成,确认 `deploy.env` 中的 `JWT_SECRET_KEY` 不是默认值
3. **修改数据库密码**: 修改 `deploy.env` 中的 `POSTGRES_PASSWORD`
4. **配置 HTTPS**: 在 nginx 前加一层 HTTPS 反向代理

### HTTPS 配置 (使用 Let's Encrypt)

```bash
# 安装 certbot
apt install certbot python3-certbot-nginx

# 获取证书
certbot --nginx -d your-domain.com

# 自动续期
echo "0 0 1 * * certbot renew" | crontab -
```

### 防火墙

```bash
# 只开放必要端口
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 22/tcp    # SSH
ufw enable
```

---

## 监控

### 简易监控脚本

```bash
#!/bin/bash
# save as /usr/local/bin/teampilot-check.sh

cd /path/to/teampilot
set -a
. ./deploy.env
set +a

if ! curl -sf "http://localhost:${BACKEND_PORT}/health" > /dev/null; then
    echo "[$(date)] Backend DOWN, restarting..." >> /var/log/teampilot-monitor.log
    docker compose restart backend
fi

if ! curl -sf "http://localhost:${FRONTEND_PORT}" > /dev/null; then
    echo "[$(date)] Frontend DOWN, restarting..." >> /var/log/teampilot-monitor.log
    docker compose restart frontend
fi
```

```bash
# 每5分钟检查一次
echo "*/5 * * * * /usr/local/bin/teampilot-check.sh" | crontab -
```
