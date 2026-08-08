"""Calculo de amanecer y atardecer con astral.

SUPUESTO EXPLICITO: Bolivia no aplica horario de verano. El pais no cambia de
huso desde 1932, por lo que America/La_Paz es UTC-4 todo el ano. Gracias a eso
un `datetime` local nunca es ambiguo ni inexistente y se puede combinar fecha y
hora directamente con `tzinfo=`, sin `fold` ni normalizaciones. Si este sistema
se llevara a un pais con DST, `hora_fija_del_dia()` es el punto que hay que
revisar: alli una hora fija puede no existir o existir dos veces.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

from .config import Config
from .enums import EventoSolar

UBICACION = LocationInfo(
    "Cochabamba", "Bolivia", Config.TZ, Config.LAT, Config.LON
)

ZONA = ZoneInfo(Config.TZ)


def hora_evento(
    evento: EventoSolar | str, fecha: dt.date, offset_min: int = 0
) -> dt.datetime:
    """Devuelve el datetime local del evento solar en esa fecha, mas el offset.

    El offset es con signo: -15 significa quince minutos ANTES del evento.
    """
    evento = EventoSolar(evento)
    s = sun(UBICACION.observer, date=fecha, tzinfo=ZONA)
    base = s["sunrise"] if evento is EventoSolar.AMANECER else s["sunset"]
    return base + dt.timedelta(minutes=offset_min)


def hora_fija_del_dia(hora: dt.time, fecha: dt.date) -> dt.datetime:
    """Combina fecha y hora local en un datetime con zona.

    Se descarta cualquier tzinfo que traiga `hora` para que la regla se
    interprete siempre en la zona configurada (ver supuesto sobre DST arriba).
    """
    return dt.datetime.combine(fecha, hora.replace(tzinfo=None), tzinfo=ZONA)


def ahora() -> dt.datetime:
    """Reloj local del sistema. Centralizado aca para poder sustituirlo en los
    tests sin parchear `datetime` global."""
    return dt.datetime.now(ZONA)
