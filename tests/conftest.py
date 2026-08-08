"""Andamiaje comun de las pruebas.

Cada prueba corre contra una base SQLite nueva en un directorio temporal y con
el planificador APAGADO: la logica del tick se prueba llamando a
`procesar_tick()` con un reloj falso, no esperando 30 segundos reales.
"""

import datetime as dt

import pytest

from app import create_app
from app.bd import Sesion
from app.cliente_esp32 import RespuestaESP32
from app.enums import Resultado
from app.modelos import Dispositivo
from app.solar import ZONA


@pytest.fixture
def aplicacion(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'prueba.db'}", con_planificador=False
    )
    app.config["TESTING"] = True
    yield app
    Sesion.remove()


@pytest.fixture
def sesion(aplicacion):
    with aplicacion.app_context():
        yield Sesion()


@pytest.fixture
def cliente(aplicacion):
    return aplicacion.test_client()


@pytest.fixture
def dispositivo(sesion):
    """El dispositivo sembrado por `create_app` a partir de ESP32_IP."""
    return sesion.query(Dispositivo).first()


@pytest.fixture
def esp32_ok(monkeypatch):
    """Sustituye la capa de red por un ESP32 que siempre contesta 200.

    Se parchea el nombre tal como lo importo `servicios`, que es el unico
    modulo que llama al cliente.
    """
    llamadas = []

    def falso(ip, accion):
        llamadas.append((ip, accion))
        return RespuestaESP32(Resultado.OK, 12, "ok", {"pos": 50, "cmd": "50 %"})

    monkeypatch.setattr("app.servicios.enviar_accion", falso)
    return llamadas


def momento(fecha: str, hora: str) -> dt.datetime:
    """Ayuda para escribir instantes locales legibles: momento('2026-08-10','07:05')."""
    return dt.datetime.fromisoformat(f"{fecha}T{hora}").replace(tzinfo=ZONA)
