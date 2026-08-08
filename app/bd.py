"""Motor y sesiones de SQLAlchemy.

`Sesion` es una `scoped_session`: cada hilo obtiene su propia sesion al
llamarla. Eso es lo que permite que el hilo del planificador trabaje sin
contexto de Flask (ver comentario en modelos.py).
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import scoped_session, sessionmaker

from .config import Config
from .modelos import Base, Dispositivo

_motor = None
Sesion = scoped_session(sessionmaker(expire_on_commit=False))


def iniciar_motor(url: str | None = None):
    """Crea el engine y lo enlaza a la fabrica de sesiones."""
    global _motor
    url = url or Config.DATABASE_URL

    # check_same_thread=False: el hilo del planificador usa la misma base que
    # los requests de Flask, y SQLite lo prohibe por defecto entre hilos.
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    _motor = create_engine(url, future=True, **kwargs)
    # `configure()` no alcanza a las sesiones ya creadas en el registro, asi
    # que primero se descartan. Importa en las pruebas, donde cada test crea
    # una aplicacion nueva contra otra base: sin esto la segunda seguiria
    # escribiendo en la primera.
    Sesion.remove()
    Sesion.configure(bind=_motor)
    return _motor


def crear_tablas():
    Base.metadata.create_all(_motor)


def sembrar_dispositivo_por_defecto(nombre: str = "Persiana principal") -> Dispositivo:
    """Crea el dispositivo inicial con la IP de ESP32_IP si la base esta vacia.

    Idempotente: si ya hay algun dispositivo cargado no toca nada, para que un
    `flask run` repetido no duplique filas ni pise una IP editada a mano.
    """
    sesion = Sesion()
    existente = sesion.scalars(select(Dispositivo)).first()
    if existente is not None:
        return existente

    disp = Dispositivo(nombre=nombre, ip=Config.ESP32_IP)
    sesion.add(disp)
    sesion.commit()
    return disp
