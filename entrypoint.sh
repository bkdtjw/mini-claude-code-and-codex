#!/bin/sh
set -eu

# Fix permissions for volume-mounted directories
# Docker creates them as root if they don't exist on host
chown -R appuser:appuser /app/data /app/reports 2>/dev/null || true
if [ -f /app/twitter_cookies.json ]; then
    chown appuser:appuser /app/twitter_cookies.json 2>/dev/null || true
fi

ALEMBIC_INI="/app/backend/alembic.ini"
ALEMBIC_DIR="/app/backend/alembic"
DB_WAIT_ATTEMPTS="${DB_WAIT_ATTEMPTS:-15}"
DB_WAIT_SECONDS="${DB_WAIT_SECONDS:-2}"

wait_for_database() {
    attempt=1
    while [ "$attempt" -le "$DB_WAIT_ATTEMPTS" ]; do
        if python - <<'PY'
import asyncio
from sqlalchemy import text

from backend.storage.database import engine


async def main() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


asyncio.run(main())
PY
        then
            echo "Database connection ready."
            return 0
        fi

        echo "Database unavailable (attempt ${attempt}/${DB_WAIT_ATTEMPTS}), retrying in ${DB_WAIT_SECONDS}s..."
        attempt=$((attempt + 1))
        sleep "$DB_WAIT_SECONDS"
    done

    echo "Database unavailable after ${DB_WAIT_ATTEMPTS} attempts."
    return 1
}

wait_for_database

if [ -f "$ALEMBIC_INI" ] && [ -d "$ALEMBIC_DIR" ]; then
    echo "Running Alembic migrations..."
    cd /app/backend
    alembic -c alembic.ini upgrade head
    cd /app
else
    echo "Skipping Alembic migrations: backend/alembic.ini or backend/alembic directory not found."
    cd /app
fi

# Run as appuser
exec gosu appuser gunicorn backend.main:app -c backend/gunicorn_conf.py
