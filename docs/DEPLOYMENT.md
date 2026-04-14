# TeamPilot Deployment Guide

This guide is the canonical production deployment and server migration reference for TeamPilot.

## Runtime versions

- Backend runtime: Python `3.11`
- Frontend build runtime: Node.js `20.19+`
- Database: PostgreSQL `16`

## One-click deployment

1. Clone the repository on the target Linux server.
2. Copy `deploy.env.example` to `deploy.env` if `deploy.env` does not already exist.
   Keep `deploy.env` as a server-local configuration file and do not commit it back into the repository.
3. Update at least these values in `deploy.env` before exposing the service:
   - `POSTGRES_PASSWORD`
   - `CORS_ORIGINS`
   - `FRONTEND_PORT` and `BACKEND_PORT` if the defaults conflict
   - `SEED_DEMO_USERS=false` for production
4. Run:

```bash
bash deploy.sh
```

What `deploy.sh` now does:

- Installs Docker and Docker Compose when possible.
- Creates `deploy.env` from `deploy.env.example` if needed.
- Generates `JWT_SECRET_KEY`, `AI_ENCRYPTION_KEY`, and `ADMIN_PASSWORD` when placeholders are still present or values are blank.
- Builds and starts the Compose stack.
- Lets the backend auto-create tables on first start.
- Fails fast if the backend health check does not become ready.

## Production checklist

- Change the generated admin password after the first login.
- Replace `CORS_ORIGINS` with your public domain, for example `["https://pm.example.com"]`.
- Put HTTPS in front of the frontend container before opening the service to the public internet.
- Keep `SEED_DEMO_USERS=false` unless you explicitly want demo accounts.
- Back up the database before every upgrade.

## Server migration

Use the helper script added in this repository:

```bash
scripts/migrate_db.sh export backups/teampilot_$(date +%Y%m%d_%H%M%S).sql.gz
```

Copy the generated archive to the new server, deploy the new stack there, and then restore:

```bash
scripts/migrate_db.sh import backups/teampilot_YYYYMMDD_HHMMSS.sql.gz
```

Recommended migration sequence:

1. On the old server, stop application writes or schedule a maintenance window.
2. Run `scripts/migrate_db.sh export ...`.
3. Copy the backup archive and your finalized `deploy.env` to the new server.
4. Run `bash deploy.sh` on the new server.
5. Run `scripts/migrate_db.sh import ...` on the new server.
6. Verify `http://127.0.0.1:${BACKEND_PORT}/health` and log in with the bootstrap admin.

## Notes

- The backend now constructs its PostgreSQL connection from `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` when `DATABASE_URL` is not provided.
- `docker-compose.yml` no longer relies on Compose-time interpolation from `env_file`, which was the main source of server-to-server drift.
- The current repository does not yet include a complete Alembic migration workflow (`alembic.ini` and revision scripts are not present), so first-run schema setup still relies on application startup.
