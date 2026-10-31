"""Consistent local SQLite backup, or a PostgreSQL pg_dump custom archive."""
import argparse
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from app.config import settings


def backup(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    url = make_url(settings.database_url)
    if url.drivername.startswith("sqlite"):
        source = Path(url.database).resolve()
        if not source.is_file():
            raise RuntimeError("SQLite database does not exist")
        output = destination / f"teampilot-{stamp}.sqlite3"
        with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as live, sqlite3.connect(output) as snapshot:
            live.backup(snapshot)
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
    elif url.drivername.startswith("postgresql"):
        executable = shutil.which("pg_dump")
        if not executable:
            raise RuntimeError("Install PostgreSQL client tools (pg_dump) before backing up")
        output = destination / f"teampilot-{stamp}.dump"
        env = dict(os.environ, PGPASSWORD=url.password or "")
        subprocess.run([executable, "--format=custom", "--host", url.host or "localhost", "--port", str(url.port or 5432), "--username", url.username or "postgres", "--dbname", url.database, "--file", str(output)], env=env, check=True)
    else:
        raise RuntimeError("Only SQLite and PostgreSQL are supported")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("backups"))
    args = parser.parse_args()
    print(backup(args.output_dir).resolve())
