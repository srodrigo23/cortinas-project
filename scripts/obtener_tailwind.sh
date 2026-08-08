#!/usr/bin/env bash
# Descarga el binario standalone de Tailwind CSS v4 en bin/tailwindcss.
#
# Se usa el binario y no el paquete de npm a proposito: mete Node y un
# node_modules en un proyecto que por lo demas es 100 % Python. El binario es
# un solo archivo, no se versiona (80 MB) y este script lo repone.
set -euo pipefail

cd "$(dirname "$0")/.."

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)  ARCHIVO=tailwindcss-macos-arm64 ;;
  Darwin-x86_64) ARCHIVO=tailwindcss-macos-x64 ;;
  Linux-aarch64) ARCHIVO=tailwindcss-linux-arm64 ;;
  Linux-x86_64)  ARCHIVO=tailwindcss-linux-x64 ;;
  *) echo "Sistema no contemplado: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

URL="https://github.com/tailwindlabs/tailwindcss/releases/latest/download/${ARCHIVO}"

mkdir -p bin
echo "Descargando ${ARCHIVO}..."
curl -fsSL -o bin/tailwindcss "$URL"
chmod +x bin/tailwindcss
echo "Listo: $(./bin/tailwindcss --help | head -1)"
