#!/usr/bin/env bash
set -euo pipefail

SERVER="${SERVER:-grupo7@146.83.216.166}"
REMOTE_DIR="${REMOTE_DIR:-grupo7}"

echo "==> Servidor: $SERVER   Carpeta: ~/$REMOTE_DIR"

ssh "$SERVER" "mkdir -p '$REMOTE_DIR'"

echo "==> Verificando .env en el servidor..."
if ! ssh "$SERVER" "test -f '$REMOTE_DIR/.env'"; then
  echo "!! Falta ~/$REMOTE_DIR/.env en el servidor."
  echo "   Crealo una sola vez con los valores de .env.server.example:"
  echo "     scp .env.server.example $SERVER:$REMOTE_DIR/.env   # y luego editalo"
  exit 1
fi

echo "==> Copiando docker-compose..."
scp docker-compose.server.yml "$SERVER:$REMOTE_DIR/docker-compose.yml"

echo "==> Pull de imagenes + arranque..."
ssh "$SERVER" "cd '$REMOTE_DIR' && docker-compose pull && docker-compose up -d"

echo "==> Estado:"
ssh "$SERVER" "cd '$REMOTE_DIR' && docker-compose ps"

echo "==> Listo -> http://grupo7.146.83.216.166.nip.io"