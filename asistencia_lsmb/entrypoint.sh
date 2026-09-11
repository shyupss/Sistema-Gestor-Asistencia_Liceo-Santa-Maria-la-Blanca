#!/bin/sh
set -e
# aplicamos las migraciones pendientes antes de levantar el servidor
uv run manage.py migrate

# =============================================================
# Si estamos en desarrollo, ejecuta runserver (con hot-reaload)
# Si no, la app se ejecuta con gunicorn (simulando producción)
# =============================================================
if [ "$#" -gt 0 ]; then
  exec "$@"
else 
  exec uv run gunicorn --bind 0.0.0.0:${APP_PORT} project.wsgi:application
fi