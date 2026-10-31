# TeamPilot Deployment Guide

## Supported deployment target

- Ubuntu `20.04.5+`

说明：

- 当前一键部署脚本 `deploy.sh` 是 Bash 脚本，面向 Ubuntu / Linux 服务器
- Windows 11 适合作为本地开发环境，不作为当前仓库的一键部署目标

## Runtime versions

- Python `3.11`
- Node.js `20.19+`
- PostgreSQL `16`
- Docker Compose Plugin

## One-click deployment

1. Clone the repository on the target Ubuntu server.
2. Copy `deploy.env.example` to `deploy.env` if it does not exist.
3. Update at least these values in `deploy.env`:
   - `POSTGRES_PASSWORD`
   - `CORS_ORIGINS`
   - `FRONTEND_PORT`
   - `BACKEND_PORT`
   - `SEED_DEMO_USERS=false` for production
   - `SMTP_*` and `REPORT_DEFAULT_RECIPIENTS` if daily/weekly report emails are required
4. Run:

```bash
bash deploy.sh
```

What `deploy.sh` does:

- Installs Docker and Docker Compose when possible
- Creates `deploy.env` from the example when missing
- Generates `JWT_SECRET_KEY` and `ADMIN_PASSWORD` when placeholders are still present
- Builds and starts the Compose stack
- Waits for the backend health check

## Production checklist

- Change the generated admin password after the first login
- Replace `CORS_ORIGINS` with your real public domain
- Put HTTPS in front of the frontend container
- Keep `SEED_DEMO_USERS=false` unless you explicitly need demo accounts
- Configure SMTP before enabling daily/weekly report email sending
- Back up PostgreSQL before every upgrade

## Upgrade policy

Current repository status:

- The project is experimental
- Database changes are tracked by Alembic, beginning with revision `20261005_01`
- `AUTO_MIGRATE=true` runs the same upgrade at startup; production can run it separately with writes stopped

That means:

- Back up the configured database before upgrading; `backend/scripts/backup_database.py` supports local backups
- Run `python -m alembic upgrade head` from `backend` before starting the upgraded application
- Keep a single backend worker while WebSocket state remains in process; see `MAINTENANCE.md` for migration limits and recovery
- Restore a verified backup to roll back database changes; do not rebuild or clear an existing database as part of an ordinary update

## Server migration

Export on the old server:

```bash
scripts/migrate_db.sh export backups/teampilot_$(date +%Y%m%d_%H%M%S).sql.gz
```

Import on the new server:

```bash
scripts/migrate_db.sh import backups/teampilot_YYYYMMDD_HHMMSS.sql.gz
```

Recommended sequence:

1. Stop application writes or open a maintenance window
2. Export the current PostgreSQL data
3. Copy the backup file and finalized `deploy.env` to the new server
4. Run `bash deploy.sh` on the new server
5. Import the backup
6. Verify `http://127.0.0.1:${BACKEND_PORT}/health`

## Notes

- When `DATABASE_URL` is not set, the backend constructs the PostgreSQL connection from:
  - `POSTGRES_HOST`
  - `POSTGRES_PORT`
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD`
  - `POSTGRES_DB`
- `docker-compose.yml` no longer depends on Compose-time interpolation from `env_file`
- If you need Windows deployment support later, it should be treated as a separate delivery target with its own scripts and service setup
