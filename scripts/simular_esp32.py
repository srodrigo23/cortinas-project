#!/usr/bin/env python3
"""ESP32 falso: replica la API del firmware para desarrollar sin el hardware.

    uv run python scripts/simular_esp32.py            # puerto 8080
    uv run python scripts/simular_esp32.py --puerto 8081 --latencia 120

Endpoints (identicos a los del firmware real):

    GET /cmd?a={subir|parar|bajar|p75|p50|p25}
        200 -> {"pos": 75, "cmd": "75 %"}
        409 -> {"error": "pulso en curso"}   mientras dura un pulso anterior
    GET /estado
        200 -> {"pos": -1, "cmd": "ninguno"}

Se imita el comportamiento que importa para probar el servidor:

* el 409 mientras hay un pulso en curso, que es lo que hace el firmware real
  al estar generando la pulsacion sobre los optoacopladores;
* la duracion real de los pulsos segun el manual del motor: ~180 ms para las
  ordenes cortas y ~2.3 s para las posiciones favoritas;
* `parar` deja la posicion en -1 (desconocida), porque el motor se detiene en
  un punto arbitrario y nadie puede saber cual.

Se usa solo la biblioteca estandar a proposito: el simulador tiene que poder
correr en cualquier maquina del laboratorio sin instalar nada.
"""

import argparse
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Duracion de la pulsacion segun el manual del AIYUHANG AT25-BE-1.1/30.
PULSO_CORTO = 0.18
PULSO_LARGO = 2.3

ACCIONES = {
    "subir": (100, "subir", PULSO_CORTO),
    "parar": (-1, "parar", PULSO_CORTO),
    "bajar": (0, "bajar", PULSO_CORTO),
    "p75": (75, "75 %", PULSO_LARGO),
    "p50": (50, "50 %", PULSO_LARGO),
    "p25": (25, "25 %", PULSO_LARGO),
}


class Motor:
    """Estado compartido del ESP32 simulado."""

    def __init__(self, latencia_ms=0, tasa_fallas=0.0):
        self.pos = -1
        self.cmd = "ninguno"
        self.pulso_hasta = 0.0
        self.latencia_ms = latencia_ms
        self.tasa_fallas = tasa_fallas
        self.candado = threading.Lock()

    def ocupado(self) -> bool:
        return time.monotonic() < self.pulso_hasta

    def ejecutar(self, accion: str):
        pos, cmd, duracion = ACCIONES[accion]
        with self.candado:
            self.pulso_hasta = time.monotonic() + duracion
            self.pos = pos
            self.cmd = cmd
        return {"pos": self.pos, "cmd": self.cmd}


class Manejador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    motor: Motor = None

    def _responder(self, codigo: int, cuerpo: dict):
        datos = json.dumps(cuerpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        url = urlparse(self.path)

        # Latencia artificial: sirve para ver el timeout de 3 s del cliente
        # entrar en accion sin tener que apagar nada.
        if self.motor.latencia_ms:
            time.sleep(self.motor.latencia_ms / 1000)

        if url.path == "/estado":
            self._responder(200, {"pos": self.motor.pos, "cmd": self.motor.cmd})
            return

        if url.path == "/cmd":
            accion = (parse_qs(url.query).get("a") or [""])[0]
            if accion not in ACCIONES:
                self._responder(400, {"error": "accion invalida"})
                return
            if self.motor.ocupado():
                self._responder(409, {"error": "pulso en curso"})
                return
            if random.random() < self.motor.tasa_fallas:
                self._responder(500, {"error": "falla simulada"})
                return
            self._responder(200, self.motor.ejecutar(accion))
            return

        self._responder(404, {"error": "no encontrado"})

    def log_message(self, formato, *args):
        print(f"[esp32-falso] {self.address_string()} {formato % args}")


def main():
    p = argparse.ArgumentParser(description="ESP32 simulado")
    p.add_argument("--puerto", type=int, default=8080)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument(
        "--latencia",
        type=int,
        default=0,
        metavar="MS",
        help="latencia artificial; poner mas de 3000 fuerza el timeout del cliente",
    )
    p.add_argument(
        "--fallas",
        type=float,
        default=0.0,
        metavar="P",
        help="probabilidad de responder 500, entre 0 y 1",
    )
    args = p.parse_args()

    Manejador.motor = Motor(args.latencia, args.fallas)
    servidor = ThreadingHTTPServer((args.host, args.puerto), Manejador)
    print(
        f"ESP32 simulado en http://{args.host}:{args.puerto}  "
        f"(latencia {args.latencia} ms, fallas {args.fallas:.0%})\n"
        f"Configura ESP32_IP={args.host}:{args.puerto} en el .env"
    )
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando el simulador")
        servidor.shutdown()


if __name__ == "__main__":
    main()
