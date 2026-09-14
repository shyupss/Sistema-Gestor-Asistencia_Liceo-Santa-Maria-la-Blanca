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
  # Crea el superusuario solo si no existe; si ya existe, continúa sin error
  uv run manage.py createsuperuser --noinput --username admin --email admin@gmail.com || true

  # Copia todos los archivos estáticos a STATIC_ROOT (staticfiles/)
  uv run manage.py collectstatic --noinput

  # Levanta gunicorn como proceso principal del contenedor
  exec uv run gunicorn --bind 0.0.0.0:${APP_PORT} project.wsgi:application
fi