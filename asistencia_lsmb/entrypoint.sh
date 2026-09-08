#!/bin/sh
set -e
uv run manage.py migrate
exec uv run gunicorn --bind 0.0.0.0:${APP_PORT:-3007} project.wsgi:application