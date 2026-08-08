"""Pruebas de la logica del tick.

Son las tres decisiones documentadas en `planificador.py`: idempotencia,
ventana de gracia y filtro de dias. Se prueban llamando a `procesar_tick()`
con un instante inyectado; no hay hilos ni esperas.
"""

import datetime as dt

import pytest

from app.enums import Accion, EventoSolar, Resultado, TipoHora
from app.modelos import Comando, Programacion
from app.planificador import detectar_solapamientos, procesar_tick, proxima_ejecucion
from app.solar import hora_evento

from .conftest import momento

# 2026-08-10 es un lunes: weekday() == 0, primer caracter de dias_semana.
LUNES = "2026-08-10"
MARTES = "2026-08-11"
SABADO = "2026-08-15"


def regla(sesion, dispositivo, **cambios):
    datos = dict(
        dispositivo_id=dispositivo.id,
        nombre="Prueba",
        accion=Accion.BAJAR,
        tipo_hora=TipoHora.FIJA,
        hora_fija=dt.time(7, 0),
        dias_semana="1111111",
        activa=True,
    )
    datos.update(cambios)
    p = Programacion(**datos)
    sesion.add(p)
    sesion.commit()
    return p


# --------------------------------------------------------------------------
# Disparo basico
# --------------------------------------------------------------------------

def test_ejecuta_cuando_llega_la_hora(sesion, dispositivo, esp32_ok):
    p = regla(sesion, dispositivo)
    acciones = procesar_tick(sesion, momento(LUNES, "07:00"))

    assert [a["accion"] for a in acciones] == ["ejecutada"]
    assert len(esp32_ok) == 1
    comando = sesion.query(Comando).one()
    assert comando.resultado is Resultado.OK
    assert comando.origen.value == "programado"
    assert comando.programacion_id == p.id
    # El instante objetivo queda guardado para poder medir el atraso despues.
    assert comando.programado_para.hour == 7


def test_no_ejecuta_antes_de_la_hora(sesion, dispositivo, esp32_ok):
    regla(sesion, dispositivo)
    assert procesar_tick(sesion, momento(LUNES, "06:59")) == []
    assert esp32_ok == []


def test_una_regla_inactiva_no_dispara(sesion, dispositivo, esp32_ok):
    regla(sesion, dispositivo, activa=False)
    assert procesar_tick(sesion, momento(LUNES, "07:00")) == []
    assert esp32_ok == []


# --------------------------------------------------------------------------
# (1) Idempotencia
# --------------------------------------------------------------------------

def test_no_repite_en_ticks_sucesivos(sesion, dispositivo, esp32_ok):
    """El tick corre cada 30 s; la regla tiene que salir una sola vez."""
    p = regla(sesion, dispositivo)
    for segundos in (0, 30, 60, 120, 600):
        procesar_tick(sesion, momento(LUNES, "07:00") + dt.timedelta(seconds=segundos))

    assert len(esp32_ok) == 1
    assert sesion.query(Comando).count() == 1
    assert p.ultima_ejecucion == dt.date(2026, 8, 10)


def test_vuelve_a_correr_al_dia_siguiente(sesion, dispositivo, esp32_ok):
    """La marca es una FECHA: cambia el dia, la regla vuelve a estar pendiente."""
    regla(sesion, dispositivo)
    procesar_tick(sesion, momento(LUNES, "07:00"))
    procesar_tick(sesion, momento(MARTES, "07:00"))
    assert len(esp32_ok) == 2


def test_un_fallo_de_red_igual_marca_el_dia(sesion, dispositivo, monkeypatch):
    """Si el ESP32 no contesta, la regla NO se reintenta en el proximo tick.

    Reintentar significaria golpear un equipo caido cada 30 s durante toda la
    ventana de gracia. El fallo queda registrado en `comandos` y se ve en el
    historial; esa es la via para enterarse, no el reintento.
    """
    from app.cliente_esp32 import RespuestaESP32

    monkeypatch.setattr(
        "app.servicios.enviar_accion",
        lambda ip, accion: RespuestaESP32(Resultado.TIMEOUT, 3000, "sin respuesta"),
    )
    regla(sesion, dispositivo)
    procesar_tick(sesion, momento(LUNES, "07:00"))
    procesar_tick(sesion, momento(LUNES, "07:05"))

    comandos = sesion.query(Comando).all()
    assert len(comandos) == 1
    assert comandos[0].resultado is Resultado.TIMEOUT


# --------------------------------------------------------------------------
# (2) Ventana de gracia
# --------------------------------------------------------------------------

@pytest.mark.parametrize("hora", ["07:00", "07:05", "07:14"])
def test_dentro_de_la_ventana_ejecuta(sesion, dispositivo, esp32_ok, hora):
    regla(sesion, dispositivo)
    acciones = procesar_tick(sesion, momento(LUNES, hora))
    assert [a["accion"] for a in acciones] == ["ejecutada"]


def test_fuera_de_la_ventana_se_omite(sesion, dispositivo, esp32_ok):
    """La laptop desperto a las 15:00: la regla de las 07:00 no se ejecuta."""
    regla(sesion, dispositivo)
    acciones = procesar_tick(sesion, momento(LUNES, "15:00"))

    assert [a["accion"] for a in acciones] == ["omitida"]
    assert esp32_ok == []  # no se toco la red

    comando = sesion.query(Comando).one()
    assert comando.resultado is Resultado.OMITIDO
    assert comando.latencia_ms is None  # no hubo llamada que medir
    assert "gracia" in comando.detalle.lower()


def test_omitir_tambien_marca_el_dia(sesion, dispositivo, esp32_ok):
    """Sin esto, la regla vencida se reevaluaria en cada tick del resto del dia
    y llenaria el historial de `omitido` repetidos."""
    regla(sesion, dispositivo)
    procesar_tick(sesion, momento(LUNES, "15:00"))
    procesar_tick(sesion, momento(LUNES, "15:30"))
    assert sesion.query(Comando).count() == 1


def test_varias_reglas_vencidas_no_disparan_en_rafaga(sesion, dispositivo, esp32_ok):
    """El caso que motivo la ventana: al despertar la laptop, tres reglas de la
    manana pretendian ejecutarse una detras de otra."""
    regla(sesion, dispositivo, nombre="A", hora_fija=dt.time(6, 0))
    regla(sesion, dispositivo, nombre="B", hora_fija=dt.time(7, 0))
    regla(sesion, dispositivo, nombre="C", hora_fija=dt.time(8, 0))

    acciones = procesar_tick(sesion, momento(LUNES, "15:00"))
    assert [a["accion"] for a in acciones] == ["omitida"] * 3
    assert esp32_ok == []


# --------------------------------------------------------------------------
# (3) Filtro de dias
# --------------------------------------------------------------------------

def test_no_corre_en_un_dia_no_marcado(sesion, dispositivo, esp32_ok):
    regla(sesion, dispositivo, dias_semana="1111100")  # lunes a viernes
    assert procesar_tick(sesion, momento(SABADO, "07:00")) == []
    assert esp32_ok == []


def test_corre_en_un_dia_marcado(sesion, dispositivo, esp32_ok):
    regla(sesion, dispositivo, dias_semana="1111100")
    acciones = procesar_tick(sesion, momento(LUNES, "07:00"))
    assert [a["accion"] for a in acciones] == ["ejecutada"]


def test_el_indice_de_dias_sigue_a_weekday(sesion, dispositivo, esp32_ok):
    """'0000011' = sabado y domingo. Si el indice se corriera, esta prueba cae."""
    regla(sesion, dispositivo, dias_semana="0000011")
    assert procesar_tick(sesion, momento(LUNES, "07:00")) == []
    acciones = procesar_tick(sesion, momento(SABADO, "07:00"))
    assert [a["accion"] for a in acciones] == ["ejecutada"]


# --------------------------------------------------------------------------
# Reglas solares dentro del tick
# --------------------------------------------------------------------------

def test_una_regla_solar_dispara_a_la_hora_calculada(sesion, dispositivo, esp32_ok):
    regla(
        sesion,
        dispositivo,
        tipo_hora=TipoHora.SOLAR,
        hora_fija=None,
        evento_solar=EventoSolar.ATARDECER,
        offset_min=-15,
    )
    objetivo = hora_evento(EventoSolar.ATARDECER, dt.date(2026, 8, 10), -15)

    assert procesar_tick(sesion, objetivo - dt.timedelta(minutes=1)) == []
    acciones = procesar_tick(sesion, objetivo + dt.timedelta(seconds=10))
    assert [a["accion"] for a in acciones] == ["ejecutada"]


# --------------------------------------------------------------------------
# Proxima ejecucion (lo que muestra la interfaz)
# --------------------------------------------------------------------------

def test_proxima_ejecucion_hoy_si_todavia_no_paso(sesion, dispositivo):
    p = regla(sesion, dispositivo, hora_fija=dt.time(20, 0))
    proxima = proxima_ejecucion(p, momento(LUNES, "07:00"))
    assert proxima.date() == dt.date(2026, 8, 10)
    assert proxima.hour == 20


def test_proxima_ejecucion_manana_si_ya_paso(sesion, dispositivo):
    p = regla(sesion, dispositivo, hora_fija=dt.time(7, 0))
    proxima = proxima_ejecucion(p, momento(LUNES, "09:00"))
    assert proxima.date() == dt.date(2026, 8, 11)


def test_proxima_ejecucion_salta_el_dia_ya_ejecutado(sesion, dispositivo, esp32_ok):
    p = regla(sesion, dispositivo, hora_fija=dt.time(7, 0))
    procesar_tick(sesion, momento(LUNES, "07:00"))
    # Aunque la hora de hoy ya paso, lo importante es que no ofrezca hoy otra vez.
    proxima = proxima_ejecucion(p, momento(LUNES, "07:01"))
    assert proxima.date() == dt.date(2026, 8, 11)


def test_proxima_ejecucion_de_una_regla_de_un_solo_dia(sesion, dispositivo):
    p = regla(sesion, dispositivo, dias_semana="0000010")  # solo sabados
    proxima = proxima_ejecucion(p, momento(LUNES, "07:00"))
    assert proxima.date() == dt.date(2026, 8, 15)


def test_una_regla_inactiva_no_tiene_proxima(sesion, dispositivo):
    p = regla(sesion, dispositivo, activa=False)
    assert proxima_ejecucion(p, momento(LUNES, "07:00")) is None


def test_una_regla_solar_devuelve_hora_concreta(sesion, dispositivo):
    """Lo que la lista muestra tiene que ser una hora, no la palabra 'amanecer'."""
    p = regla(
        sesion,
        dispositivo,
        tipo_hora=TipoHora.SOLAR,
        hora_fija=None,
        evento_solar=EventoSolar.AMANECER,
    )
    proxima = proxima_ejecucion(p, momento(LUNES, "03:00"))
    assert isinstance(proxima, dt.datetime)
    assert 5 <= proxima.hour <= 7


# --------------------------------------------------------------------------
# Solapamientos
# --------------------------------------------------------------------------

def test_avisa_cuando_dos_reglas_caen_muy_juntas(sesion, dispositivo):
    regla(sesion, dispositivo, nombre="Bajar", hora_fija=dt.time(18, 0))
    regla(sesion, dispositivo, nombre="Bajar de nuevo", hora_fija=dt.time(18, 3))

    conflictos = detectar_solapamientos(sesion, dispositivo.id)
    assert len(conflictos) == 1
    assert {conflictos[0]["a"], conflictos[0]["b"]} == {"Bajar", "Bajar de nuevo"}
    assert conflictos[0]["minutos"] == 3


def test_no_avisa_si_estan_separadas(sesion, dispositivo):
    regla(sesion, dispositivo, nombre="A", hora_fija=dt.time(7, 0))
    regla(sesion, dispositivo, nombre="B", hora_fija=dt.time(19, 0))
    assert detectar_solapamientos(sesion, dispositivo.id) == []


def test_no_avisa_si_caen_en_dias_distintos(sesion, dispositivo):
    regla(sesion, dispositivo, nombre="A", hora_fija=dt.time(7, 0), dias_semana="1000000")
    regla(sesion, dispositivo, nombre="B", hora_fija=dt.time(7, 2), dias_semana="0100000")
    assert detectar_solapamientos(sesion, dispositivo.id) == []


def test_una_regla_pausada_no_genera_conflicto(sesion, dispositivo):
    regla(sesion, dispositivo, nombre="A", hora_fija=dt.time(7, 0))
    regla(sesion, dispositivo, nombre="B", hora_fija=dt.time(7, 2), activa=False)
    assert detectar_solapamientos(sesion, dispositivo.id) == []
