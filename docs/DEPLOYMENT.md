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
- v0.6.0 adds explicit migrations through `20261104_05` for team governance, planning, report history and project visibility. Existing projects retain company visibility; legacy tasks retain their data and are flagged for responsibility confirmation rather than given an arbitrary owner.
- Keep a single backend worker while WebSocket state remains in process; see `MAINTENANCE.md` for migration limits and recovery
- Restore a verified backup to roll back database changes; do not rebuild or clear an existing database as part of an ordinary update

## Model provider encryption keys

Model provider API keys and custom headers are encrypted before being saved in `system_settings`. Set `MODEL_PROVIDER_ENCRYPTION_KEY` to a Fernet key if your deployment manages secrets centrally. Without that variable, local development creates and reuses `backend/.model-provider.key`; the Compose deployment stores the generated key in the persistent `provider_secrets` volume using `MODEL_PROVIDER_KEY_FILE=/app/provider-secrets/.model-provider.key`.

Back up the database and encryption key together. Retain the same key when rebuilding containers or moving servers. Losing or changing the key prevents existing credentials from being decrypted; the application reports the error rather than clearing or silently replacing them. Keep the key out of Git, source archives and container images. A Fernet key can be generated with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and stored directly in your secret manager.

Model configuration uses existing `system_settings`; it does not convert business API connectors into model providers or delete task data. Provider URLs can target a local gateway, so configure the address as reachable from the backend container.

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
3. Copy the backup file, finalized `deploy.env` and model provider encryption key (or its `provider_secrets` volume backup) to the new server
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
