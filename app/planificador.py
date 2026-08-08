"""Planificador de horarios.

Un hilo de fondo despierta cada 30 s y revisa las reglas activas. Tres
decisiones de diseno merecen explicacion porque los tres problemas aparecieron
en las pruebas y son material del capitulo de problemas encontrados.

1. IDEMPOTENCIA. El tick corre cada 30 s. Una regla de las 07:00 sigue estando
   "en hora" durante toda la ventana de gracia, asi que sin marca de estado se
   dispararia una y otra vez: la persiana recibia el mismo comando decenas de
   veces. La marca es `ultima_ejecucion` y se compara contra la FECHA, no
   contra la hora: la pregunta no es "cuando corrio" sino "ya corrio hoy".
   Se marca tambien cuando se omite, para que una regla vencida no se reevalue
   en cada tick del resto del dia.

2. VENTANA DE GRACIA DE 15 MINUTOS. La laptop de demostracion se suspende. Al
   despertar a las 15:00, todas las reglas de la manana estan "vencidas" y sin
   proteccion disparan en rafaga: la persiana sube y baja sola varias veces
   seguidas. Con la ventana, una regla que ya paso hace mas de 15 minutos se
   registra como `omitido` y no se ejecuta. El registro importa: omitir en
   silencio haria imposible distinguir "no habia regla" de "la regla se perdio"
   al analizar la bitacora.

3. DOBLE HILO POR EL RELOADER DE FLASK. Con `debug=True` Werkzeug levanta dos
   procesos (el supervisor y el hijo que recarga). El scheduler se instanciaba
   en los dos y cada comando salia duplicado, ademas de que ambos competian por
   marcar `ultima_ejecucion`. La guarda esta en `iniciar()`: solo arranca en el
   proceso hijo (`WERKZEUG_RUN_MAIN == "true"`) o cuando el reloader esta
   apagado.
"""

import datetime as dt
import logging
import threading

from sqlalchemy import select

from .config import Config
from .enums import TipoHora
from .modelos import Dispositivo, Programacion
from .servicios import chequear_salud, ejecutar_comando, registrar_omitido
from .solar import ahora, hora_evento, hora_fija_del_dia

log = logging.getLogger("planificador")

# Handle del hilo, para que los tests puedan verificar que no se duplica.
_hilo: threading.Thread | None = None
_parar = threading.Event()


# --------------------------------------------------------------------------
# Calculo de horarios
# --------------------------------------------------------------------------

def objetivo_del_dia(p: Programacion, fecha: dt.date) -> dt.datetime:
    """Momento exacto en que la regla debe disparar ese dia."""
    if p.tipo_hora is TipoHora.SOLAR:
        return hora_evento(p.evento_solar, fecha, p.offset_min)
    return hora_fija_del_dia(p.hora_fija, fecha)


def proxima_ejecucion(p: Programacion, desde: dt.datetime | None = None):
    """Proximo disparo real de la regla, o None si no corre ningun dia.

    Se usa en dos lugares distintos a proposito: el planificador no la necesita
    (el tick evalua el dia en curso) pero la lista de programaciones si, porque
    para una regla solar hay que mostrar la hora concreta de manana -"06:23"-
    y no la palabra "amanecer". Manteniendo el calculo en un solo modulo, lo
    que muestra la interfaz y lo que hace el scheduler no pueden divergir.

    Se miran 8 dias para cubrir una regla que corre un solo dia de la semana.
    """
    desde = desde or ahora()
    if not p.activa or "1" not in p.dias_semana:
        return None

    for delta in range(8):
        fecha = desde.date() + dt.timedelta(days=delta)
        if not p.corre_el_dia(fecha.weekday()):
            continue
        # Si hoy ya se resolvio (ejecutada u omitida), no se vuelve a ofrecer.
        if delta == 0 and p.ultima_ejecucion == fecha:
            continue
        objetivo = objetivo_del_dia(p, fecha)
        if objetivo > desde:
            return objetivo
    return None


def detectar_solapamientos(
    sesion, dispositivo_id: int, margen_min: int | None = None
) -> list[dict]:
    """Pares de reglas activas del mismo dispositivo que caen muy juntas.

    Es solo un aviso, no un bloqueo: dos ordenes seguidas no rompen nada, pero
    la segunda pisa a la primera y el usuario probablemente no lo quiso. Se
    comparan las proximas ejecuciones dia por dia durante una semana, porque
    dos reglas solares con offsets distintos pueden acercarse en unas fechas y
    no en otras.
    """
    margen = margen_min if margen_min is not None else Config.MARGEN_SOLAPAMIENTO
    reglas = sesion.scalars(
        select(Programacion).where(
            Programacion.dispositivo_id == dispositivo_id,
            Programacion.activa.is_(True),
        )
    ).all()

    hoy = ahora().date()
    conflictos: list[dict] = []
    vistos: set[tuple[int, int]] = set()

    for delta in range(7):
        fecha = hoy + dt.timedelta(days=delta)
        delvia = [r for r in reglas if r.corre_el_dia(fecha.weekday())]
        horarios = [(r, objetivo_del_dia(r, fecha)) for r in delvia]
        for i, (ra, ha) in enumerate(horarios):
            for rb, hb in horarios[i + 1 :]:
                diferencia = abs((ha - hb).total_seconds()) / 60
                if diferencia >= margen:
                    continue
                clave = tuple(sorted((ra.id, rb.id)))
                if clave in vistos:
                    continue
                vistos.add(clave)
                conflictos.append(
                    {
                        "a": ra.nombre,
                        "b": rb.nombre,
                        "fecha": fecha.isoformat(),
                        "minutos": round(diferencia, 1),
                    }
                )
    return conflictos


# --------------------------------------------------------------------------
# Tick
# --------------------------------------------------------------------------

def procesar_tick(sesion, momento: dt.datetime | None = None) -> list[dict]:
    """Una pasada del planificador. Devuelve lo que hizo, para tests y logs.

    Recibe la sesion y el momento por parametro (no los toma del entorno) para
    poder probar la logica con un reloj falso sin tocar hilos ni esperar 30 s.
    """
    momento = momento or ahora()
    hoy = momento.date()
    acciones: list[dict] = []

    activas = sesion.scalars(
        select(Programacion).where(Programacion.activa.is_(True))
    ).all()

    for p in activas:
        # (1) idempotencia: comparacion contra la fecha, no contra la hora.
        if p.ultima_ejecucion == hoy:
            continue
        # Filtro de dia de la semana. weekday(): 0 = lunes.
        if not p.corre_el_dia(hoy.weekday()):
            continue

        objetivo = objetivo_del_dia(p, hoy)
        atraso = (momento - objetivo).total_seconds()

        if atraso < 0:
            continue  # todavia no es la hora

        dispositivo = sesion.get(Dispositivo, p.dispositivo_id)
        if dispositivo is None:
            continue

        if atraso <= Config.VENTANA_GRACIA:
            comando = ejecutar_comando(
                sesion,
                dispositivo,
                p.accion,
                origen="programado",
                programacion=p,
                programado_para=objetivo,
            )
            p.ultima_ejecucion = hoy  # marca ANTES de soltar la sesion
            sesion.commit()
            acciones.append(
                {
                    "programacion_id": p.id,
                    "accion": "ejecutada",
                    "resultado": comando.resultado.value,
                    "atraso_s": round(atraso),
                }
            )
            log.info(
                "Regla %r ejecutada (%s, atraso %ds)",
                p.nombre,
                comando.resultado.value,
                atraso,
            )
        else:
            # (2) fuera de la ventana de gracia: se registra y no se ejecuta.
            registrar_omitido(
                sesion,
                dispositivo,
                p,
                objetivo,
                f"Fuera de la ventana de gracia: la hora prevista paso hace "
                f"{round(atraso / 60)} minutos",
            )
            p.ultima_ejecucion = hoy
            sesion.commit()
            acciones.append(
                {
                    "programacion_id": p.id,
                    "accion": "omitida",
                    "atraso_s": round(atraso),
                }
            )
            log.warning(
                "Regla %r omitida: %d minutos de atraso", p.nombre, atraso / 60
            )

    return acciones


# --------------------------------------------------------------------------
# Hilo
# --------------------------------------------------------------------------

def _bucle(Sesion):
    contador = 0
    while not _parar.is_set():
        sesion = Sesion()
        try:
            procesar_tick(sesion)

            contador += 1
            if contador % Config.TICKS_POR_CHEQUEO == 0:
                for d in sesion.scalars(select(Dispositivo)).all():
                    chequear_salud(sesion, d)
        except Exception:
            # Una excepcion no atrapada mata el hilo en silencio y el sistema
            # queda sin scheduler sin que nadie se entere hasta la demo.
            log.exception("Error en el tick del planificador")
            sesion.rollback()
        finally:
            Sesion.remove()

        _parar.wait(Config.INTERVALO_TICK)


def iniciar(Sesion) -> bool:
    """Arranca el hilo si corresponde. Devuelve True si lo arranco.

    (3) Guarda contra el doble hilo del reloader de Flask: en modo debug
    Werkzeug corre dos procesos y solo el hijo tiene WERKZEUG_RUN_MAIN='true'.
    Sin esta guarda cada comando programado salia dos veces.
    """
    global _hilo
    import os

    en_debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    es_hijo_del_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if en_debug and not es_hijo_del_reloader:
        log.info("Proceso supervisor del reloader: no se arranca el planificador")
        return False

    if _hilo is not None and _hilo.is_alive():
        return False

    _parar.clear()
    _hilo = threading.Thread(
        target=_bucle, args=(Sesion,), name="planificador", daemon=True
    )
    _hilo.start()
    log.info("Planificador iniciado (tick cada %d s)", Config.INTERVALO_TICK)
    return True


def detener():
    _parar.set()
    if _hilo is not None:
        _hilo.join(timeout=2)
