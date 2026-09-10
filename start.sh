#!/usr/bin/env bash
set -euo pipefail

# Render Free does not provide the paid pre-deploy command, so migrations are
# intentionally run once at process startup. Django migrations are idempotent.
python manage.py migrate --noinput
python manage.py ensure_admin_from_env

exec gunicorn mms.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-2} \
  --timeout ${GUNICORN_TIMEOUT:-120} \
  --access-logfile - \
  --error-logfile -
