"""Cliente HTTP del ESP32.

Unico modulo que habla por la red con el hardware. Nadie mas importa `requests`.

Contrato del firmware (dado, no se modifica):

    GET /cmd?a={subir|parar|bajar|p75|p50|p25}
        200 -> {"pos": 75, "cmd": "75 %"}
        409 -> {"error": "pulso en curso"}
    GET /estado
        200 -> {"pos": -1, "cmd": "ninguno"}

`pos` es la ULTIMA POSICION ORDENADA, no la real: el enlace hacia el motor es
unidireccional (se emulan pulsaciones del control remoto con optoacopladores) y
no hay realimentacion. `pos = -1` significa desconocida.
"""

import time
from dataclasses import dataclass, field

import requests

from .config import Config
from .enums import Accion, Resultado

POSICION_DESCONOCIDA = -1


@dataclass
class RespuestaESP32:
    resultado: Resultado
    latencia_ms: int
    detalle: str = ""
    datos: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.resultado is Resultado.OK

    @property
    def pos(self) -> int:
        """Posicion ordenada segun el ESP32, o -1 si no la sabemos."""
        valor = self.datos.get("pos", POSICION_DESCONOCIDA)
        return valor if isinstance(valor, int) else POSICION_DESCONOCIDA


def _url(ip: str, ruta: str) -> str:
    """Acepta '192.168.1.50', '192.168.1.50:8080' o una URL completa."""
    if ip.startswith(("http://", "https://")):
        base = ip.rstrip("/")
    else:
        base = f"http://{ip.rstrip('/')}"
    return f"{base}{ruta}"


def _pedir(ip: str, ruta: str, params: dict | None = None) -> RespuestaESP32:
    """Hace la llamada midiendo latencia y traduce todo fallo a un Resultado.

    Esta funcion NUNCA lanza excepciones de red hacia arriba: el resto del
    sistema trabaja con `RespuestaESP32`, de modo que el registro en la tabla
    `comandos` es el mismo camino de codigo para el exito y para el error.

    El timeout es obligatorio. Sin el, un ESP32 apagado deja el worker de Flask
    esperando hasta que el sistema operativo abandone el socket y el panel se
    congela; fue el primer problema real que aparecio en las pruebas.
    """
    inicio = time.perf_counter()
    try:
        r = requests.get(
            _url(ip, ruta), params=params or {}, timeout=Config.TIMEOUT_ESP32
        )
        latencia = int((time.perf_counter() - inicio) * 1000)

        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = {}

        if r.status_code == 200:
            return RespuestaESP32(Resultado.OK, latencia, cuerpo.get("cmd", ""), cuerpo)

        if r.status_code == 409:
            # El firmware rechaza un comando mientras esta generando otro pulso
            # sobre los optoacopladores. No es una falla del sistema: es el
            # hardware protegiendose de pulsos superpuestos.
            motivo = cuerpo.get("error", "pulso en curso")
            return RespuestaESP32(
                Resultado.ERROR, latencia, f"El equipo esta ocupado ({motivo})", cuerpo
            )

        return RespuestaESP32(
            Resultado.ERROR, latencia, f"Respuesta HTTP {r.status_code}", cuerpo
        )

    except requests.exceptions.Timeout:
        latencia = int((time.perf_counter() - inicio) * 1000)
        return RespuestaESP32(
            Resultado.TIMEOUT,
            latencia,
            f"Sin respuesta en {Config.TIMEOUT_ESP32:.0f} s",
        )
    except requests.exceptions.ConnectionError as e:
        latencia = int((time.perf_counter() - inicio) * 1000)
        return RespuestaESP32(
            Resultado.ERROR, latencia, f"No se pudo conectar con {ip}: {type(e).__name__}"
        )
    except requests.exceptions.RequestException as e:
        latencia = int((time.perf_counter() - inicio) * 1000)
        return RespuestaESP32(Resultado.ERROR, latencia, f"Fallo de red: {e}")


def enviar_accion(ip: str, accion: Accion) -> RespuestaESP32:
    return _pedir(ip, "/cmd", {"a": Accion(accion).value})


def consultar_estado(ip: str) -> RespuestaESP32:
    return _pedir(ip, "/estado")
