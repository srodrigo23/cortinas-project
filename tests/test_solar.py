"""Pruebas del calculo solar."""

import datetime as dt

import pytest

from app.enums import EventoSolar
from app.solar import ZONA, hora_evento, hora_fija_del_dia

# Un dia cualquiera de invierno austral y otro de verano, para verificar que
# el resultado se mueve con la estacion y no es una constante.
INVIERNO = dt.date(2026, 6, 21)
VERANO = dt.date(2026, 12, 21)


def test_devuelve_datetime_con_zona():
    h = hora_evento(EventoSolar.AMANECER, INVIERNO)
    assert h.tzinfo is not None
    assert h.utcoffset() == dt.timedelta(hours=-4)  # Bolivia, UTC-4 todo el ano


def test_amanecer_antes_que_atardecer():
    amanecer = hora_evento(EventoSolar.AMANECER, INVIERNO)
    atardecer = hora_evento(EventoSolar.ATARDECER, INVIERNO)
    assert amanecer < atardecer


def test_amanecer_en_rango_plausible_para_cochabamba():
    # Cochabamba esta cerca del tropico: el amanecer se mueve poco, siempre
    # entre las 05:45 y las 07:00 locales.
    for fecha in (INVIERNO, VERANO):
        h = hora_evento(EventoSolar.AMANECER, fecha)
        assert dt.time(5, 45) <= h.time() <= dt.time(7, 0), fecha


def test_el_dia_es_mas_largo_en_verano():
    def duracion(fecha):
        return hora_evento(EventoSolar.ATARDECER, fecha) - hora_evento(
            EventoSolar.AMANECER, fecha
        )

    assert duracion(VERANO) > duracion(INVIERNO)


def test_offset_negativo_adelanta_el_evento():
    base = hora_evento(EventoSolar.ATARDECER, INVIERNO)
    antes = hora_evento(EventoSolar.ATARDECER, INVIERNO, offset_min=-15)
    assert base - antes == dt.timedelta(minutes=15)


def test_offset_positivo_atrasa_el_evento():
    base = hora_evento(EventoSolar.AMANECER, VERANO)
    despues = hora_evento(EventoSolar.AMANECER, VERANO, offset_min=30)
    assert despues - base == dt.timedelta(minutes=30)


def test_acepta_el_evento_como_texto():
    """La regla llega de la base como string en algunos caminos; que no importe."""
    assert hora_evento("amanecer", INVIERNO) == hora_evento(
        EventoSolar.AMANECER, INVIERNO
    )


def test_evento_desconocido_falla():
    with pytest.raises(ValueError):
        hora_evento("mediodia", INVIERNO)


def test_hora_fija_se_ancla_a_la_zona_local():
    d = hora_fija_del_dia(dt.time(7, 30), dt.date(2026, 8, 10))
    assert d.tzinfo is ZONA
    assert (d.hour, d.minute) == (7, 30)


def test_hora_fija_ignora_la_zona_que_traiga_la_hora():
    # Si por algun camino llega una `time` con tzinfo, la regla igual se
    # interpreta en la zona configurada y no en la que venia pegada.
    con_utc = dt.time(7, 30, tzinfo=dt.timezone.utc)
    d = hora_fija_del_dia(con_utc, dt.date(2026, 8, 10))
    assert (d.hour, d.minute) == (7, 30)
    assert d.utcoffset() == dt.timedelta(hours=-4)
