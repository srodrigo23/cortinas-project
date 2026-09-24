"""Configuracion leida del entorno (.env).

Un solo lugar donde aparecen los valores magicos del sistema, para poder
citarlos en el documento sin salir a buscarlos por el codigo.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

load_dotenv(RAIZ / ".env")


class Config:
    # --- Red -------------------------------------------------------------
    ESP32_IP = os.environ.get("ESP32_IP", "127.0.0.1:8080")

    # Timeout obligatorio en TODA llamada al ESP32. Sin esto, un ESP32 apagado
    # deja el request de Flask colgado hasta que el socket muera por su cuenta
    # (minutos) y el panel queda congelado. 3 s es holgado: el ESP32 responde
    # en decenas de milisegundos en LAN.
    TIMEOUT_ESP32 = float(os.environ.get("TIMEOUT_ESP32", "3"))

    # --- Ubicacion (calculo solar) ---------------------------------------
    # Por defecto Cochabamba, Bolivia.
    LAT = float(os.environ.get("LAT", "-17.3895"))
    LON = float(os.environ.get("LON", "-66.1568"))
    TZ = os.environ.get("TZ", "America/La_Paz")

    # --- Scheduler -------------------------------------------------------
    INTERVALO_TICK = int(os.environ.get("INTERVALO_TICK", "30"))  # segundos

    # Ventana de gracia: una regla cuya hora objetivo ya paso hace mas de esto
    # se registra como `omitido` en vez de ejecutarse. Ver planificador.py.
    VENTANA_GRACIA = int(os.environ.get("VENTANA_GRACIA", "900"))  # 15 minutos

    # Cada cuantos ticks se hace el chequeo de salud (GET /estado).
    TICKS_POR_CHEQUEO = int(os.environ.get("TICKS_POR_CHEQUEO", "4"))  # ~2 min

    # Margen minimo entre dos reglas activas del mismo dispositivo antes de
    # avisar por solapamiento.
    MARGEN_SOLAPAMIENTO = int(os.environ.get("MARGEN_SOLAPAMIENTO", "5"))  # min

    # --- Flask / base de datos -------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambiame-en-produccion")
    # as_posix(): en Windows la ruta sale con barras invertidas
    # (C:\...\cortinas.db) y la URL de SQLAlchemy espera barras normales.
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(RAIZ / 'instance' / 'cortinas.db').as_posix()}"
    )
