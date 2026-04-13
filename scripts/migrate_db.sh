#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_ENV="${PROJECT_DIR}/deploy.env"

if [ ! -f "$DEPLOY_ENV" ]; then
    echo "deploy.env not found at ${DEPLOY_ENV}" >&2
    exit 1
fi

set -a
. "$DEPLOY_ENV"
set +a

POSTGRES_USER="${POSTGRES_USER:-teampilot}"
POSTGRES_DB="${POSTGRES_DB:-teampilot}"

COMPOSE_CMD=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
fi

usage() {
    cat <<'EOF'
Usage:
  scripts/migrate_db.sh export [output.sql.gz]
  scripts/migrate_db.sh import <input.sql.gz>

Examples:
  scripts/migrate_db.sh export backups/teampilot_20260413.sql.gz
  scripts/migrate_db.sh import backups/teampilot_20260413.sql.gz
EOF
}

command_name="${1:-}"
archive_path="${2:-}"

case "$command_name" in
    export)
        if [ -z "$archive_path" ]; then
            archive_path="${PROJECT_DIR}/backups/teampilot_$(date +%Y%m%d_%H%M%S).sql.gz"
        fi
        mkdir -p "$(dirname "$archive_path")"
        "${COMPOSE_CMD[@]}" exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip -c > "$archive_path"
        echo "Database backup written to $archive_path"
        ;;
    import)
        if [ -z "$archive_path" ] || [ ! -f "$archive_path" ]; then
            echo "A valid backup archive is required for import." >&2
            usage
            exit 1
        fi
        gunzip -c "$archive_path" | "${COMPOSE_CMD[@]}" exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
        echo "Database restore completed from $archive_path"
        ;;
    *)
        usage
        exit 1
        ;;
esac
