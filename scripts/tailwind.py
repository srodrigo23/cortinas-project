#!/usr/bin/env python3
"""Binario standalone de Tailwind CSS v4: descarga, build y watcher.

    uv run python scripts/tailwind.py obtener     # descarga bin/tailwindcss
    uv run python scripts/tailwind.py construir   # CSS minificado (produccion)
    uv run python scripts/tailwind.py vigilar     # watcher para desarrollo

Reemplaza a los antiguos scripts .sh para que el mismo comando funcione en
Windows, macOS y Linux sin depender de bash ni de curl.

Se usa el binario y no el paquete de npm a proposito: mete Node y un
node_modules en un proyecto que por lo demas es 100 % Python. El binario es
un solo archivo, no se versiona (80 MB) y este script lo repone.

El resultado de `construir` (app/static/css/app.css) SE VERSIONA. El dia de
la demostracion la aplicacion arranca con `flask run` a secas, sin watcher de
Tailwind y sin conexion a internet.
"""

import argparse
import platform
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ES_WINDOWS = sys.platform == "win32"
BINARIO = RAIZ / "bin" / ("tailwindcss.exe" if ES_WINDOWS else "tailwindcss")
ENTRADA = RAIZ / "app" / "static" / "src" / "input.css"
SALIDA = RAIZ / "app" / "static" / "css" / "app.css"

URL_BASE = "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/"

ARCHIVOS = {
    ("darwin", "arm64"): "tailwindcss-macos-arm64",
    ("darwin", "x86_64"): "tailwindcss-macos-x64",
    ("linux", "aarch64"): "tailwindcss-linux-arm64",
    ("linux", "arm64"): "tailwindcss-linux-arm64",
    ("linux", "x86_64"): "tailwindcss-linux-x64",
    # Windows en ARM ejecuta el binario x64 por emulacion.
    ("win32", "amd64"): "tailwindcss-windows-x64.exe",
    ("win32", "x86_64"): "tailwindcss-windows-x64.exe",
    ("win32", "arm64"): "tailwindcss-windows-x64.exe",
}


def obtener():
    clave = (sys.platform, platform.machine().lower())
    archivo = ARCHIVOS.get(clave)
    if archivo is None:
        sys.exit(f"Sistema no contemplado: {clave[0]}-{clave[1]}")

    BINARIO.parent.mkdir(exist_ok=True)
    print(f"Descargando {archivo}...")
    urllib.request.urlretrieve(URL_BASE + archivo, BINARIO)
    if not ES_WINDOWS:
        BINARIO.chmod(BINARIO.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Listo: {BINARIO.relative_to(RAIZ)}")


def _correr(*extra: str) -> int:
    if not BINARIO.exists():
        sys.exit(
            f"Falta {BINARIO.relative_to(RAIZ)}. Corre primero: "
            "uv run python scripts/tailwind.py obtener"
        )
    return subprocess.call([str(BINARIO), "-i", str(ENTRADA), "-o", str(SALIDA), *extra])


def construir():
    codigo = _correr("--minify")
    if codigo == 0:
        print(f"CSS generado: {SALIDA.stat().st_size} bytes")
    sys.exit(codigo)


def vigilar():
    try:
        sys.exit(_correr("--watch"))
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("orden", choices=["obtener", "construir", "vigilar"])
    orden = parser.parse_args().orden
    {"obtener": obtener, "construir": construir, "vigilar": vigilar}[orden]()


if __name__ == "__main__":
    main()
