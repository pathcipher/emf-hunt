#!/bin/sh
set -e

if [ -z "${SECRET_KEY:-}" ]; then
  echo "WARNING: SECRET_KEY is not set — set it in .env before a real deployment." >&2
fi

# Ensure the media directory exists (the mounted volume may start empty).
mkdir -p "${MEDIA_ROOT:-/app/media}"

# Ensure the schema exists. create_all() is idempotent: it only adds missing tables,
# so this is safe to run on every container start.
flask --app wsgi init-db

# Optionally seed clearly-fake demo puzzles (skips any that already exist).
if [ "${SEED_DEMO:-0}" = "1" ]; then
  flask --app wsgi seed-demo
fi

exec "$@"
