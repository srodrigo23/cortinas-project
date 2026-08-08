#!/usr/bin/env bash
# Build de produccion: genera el CSS minificado una sola vez.
#
# El resultado (app/static/css/app.css) SE VERSIONA. El dia de la
# demostracion la aplicacion arranca con `flask run` a secas, sin watcher de
# Tailwind y sin conexion a internet.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -x bin/tailwindcss ]; then
  echo "Falta bin/tailwindcss. Corre primero: ./scripts/obtener_tailwind.sh" >&2
  exit 1
fi

./bin/tailwindcss -i app/static/src/input.css -o app/static/css/app.css --minify
echo "CSS generado: $(wc -c < app/static/css/app.css) bytes"
