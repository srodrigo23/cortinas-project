"""Endpoints JSON consumidos por `fetch` desde el navegador.

Las plantillas Jinja renderizan el esqueleto una sola vez; todo lo que cambia
(estado del equipo, alta de reglas, historial) viaja por aca sin recargar.
"""

import datetime as dt

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from ..bd import Sesion
from ..cliente_esp32 import POSICION_DESCONOCIDA
from ..enums import Accion, EventoSolar, Origen, Resultado, TipoHora
from ..modelos import Comando, Dispositivo, Programacion
from ..planificador import detectar_solapamientos, proxima_ejecucion
from ..servicios import (
    chequear_salud,
    ejecutar_comando,
    posicion_estimada,
    resumen_historial,
)
from ..solar import ZONA

api = Blueprint("api", __name__, url_prefix="/api")

# Mensajes para la interfaz. La regla es no mostrarle al usuario ni codigos
# HTTP ni nombres de excepciones: el panel lo opera alguien que quiere subir
# una persiana, no depurar una request.
MENSAJES = {
    Resultado.OK: "Comando enviado",
    Resultado.TIMEOUT: "El equipo no responde",
    Resultado.ERROR: "No se pudo enviar el comando",
    Resultado.OMITIDO: "Comando omitido",
}


class ErrorDeDatos(ValueError):
    """Datos invalidos enviados por el formulario."""


@api.errorhandler(ErrorDeDatos)
def _error_datos(e):
    return jsonify({"ok": False, "mensaje": str(e)}), 400


@api.teardown_request
def _cerrar_sesion(exc):
    # La scoped_session se limpia al final de cada request para que el hilo del
    # servidor no arrastre objetos de un request al siguiente.
    Sesion.remove()


# --------------------------------------------------------------------------
# Serializadores
# --------------------------------------------------------------------------

def _iso(valor: dt.datetime | dt.date | dt.time | None):
    return valor.isoformat() if valor is not None else None


def _dispositivo_json(d: Dispositivo) -> dict:
    return {
        "id": d.id,
        "nombre": d.nombre,
        "ip": d.ip,
        "ultima_respuesta": _iso(d.ultima_respuesta),
    }


def _programacion_json(p: Programacion) -> dict:
    proxima = proxima_ejecucion(p)
    return {
        "id": p.id,
        "dispositivo_id": p.dispositivo_id,
        "nombre": p.nombre,
        "accion": p.accion.value,
        "accion_etiqueta": p.accion.etiqueta,
        "tipo_hora": p.tipo_hora.value,
        "hora_fija": _iso(p.hora_fija),
        "evento_solar": p.evento_solar.value if p.evento_solar else None,
        "offset_min": p.offset_min,
        "dias_semana": p.dias_semana,
        "dias_legibles": p.dias_legibles,
        "activa": p.activa,
        "ultima_ejecucion": _iso(p.ultima_ejecucion),
        "proxima_ejecucion": _iso(proxima),
        # Texto ya armado en el servidor: para una regla solar la interfaz
        # tiene que mostrar la hora concreta calculada, no la palabra
        # "amanecer".
        "proxima_legible": _texto_proxima(proxima),
    }


def _texto_proxima(proxima: dt.datetime | None) -> str:
    if proxima is None:
        return "Sin proxima ejecucion"
    from ..solar import ahora

    hoy = ahora().date()
    dias = (proxima.date() - hoy).days
    hora = proxima.strftime("%H:%M")
    if dias == 0:
        return f"Hoy {hora}"
    if dias == 1:
        return f"Manana {hora}"
    from ..enums import DIAS_SEMANA

    return f"{DIAS_SEMANA[proxima.weekday()]} {proxima.strftime('%d/%m')} {hora}"


def _comando_json(c: Comando) -> dict:
    return {
        "id": c.id,
        "dispositivo_id": c.dispositivo_id,
        "dispositivo": c.dispositivo.nombre if c.dispositivo else "",
        "accion": c.accion.value,
        "accion_etiqueta": c.accion.etiqueta,
        "origen": c.origen.value,
        "programacion": c.programacion.nombre if c.programacion else None,
        "programado_para": _iso(c.programado_para),
        "enviado_en": _iso(c.enviado_en),
        "hora": c.enviado_en.astimezone(ZONA).strftime("%d/%m %H:%M:%S"),
        "latencia_ms": c.latencia_ms,
        "resultado": c.resultado.value,
        "detalle": c.detalle,
    }


# --------------------------------------------------------------------------
# Dispositivos
# --------------------------------------------------------------------------

@api.get("/dispositivos")
def listar_dispositivos():
    sesion = Sesion()
    ds = sesion.scalars(select(Dispositivo).order_by(Dispositivo.id)).all()
    return jsonify({"ok": True, "dispositivos": [_dispositivo_json(d) for d in ds]})


@api.post("/dispositivos")
def crear_dispositivo():
    sesion = Sesion()
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    ip = (datos.get("ip") or "").strip()
    if not nombre or not ip:
        raise ErrorDeDatos("Hace falta un nombre y una direccion IP")

    d = Dispositivo(nombre=nombre, ip=ip)
    sesion.add(d)
    sesion.commit()
    return jsonify({"ok": True, "dispositivo": _dispositivo_json(d)}), 201


@api.put("/dispositivos/<int:did>")
def editar_dispositivo(did: int):
    sesion = Sesion()
    d = sesion.get(Dispositivo, did)
    if d is None:
        return jsonify({"ok": False, "mensaje": "El equipo no existe"}), 404

    datos = request.get_json(silent=True) or {}
    if "nombre" in datos:
        nombre = (datos["nombre"] or "").strip()
        if not nombre:
            raise ErrorDeDatos("El nombre no puede quedar vacio")
        d.nombre = nombre
    if "ip" in datos:
        ip = (datos["ip"] or "").strip()
        if not ip:
            raise ErrorDeDatos("La direccion IP no puede quedar vacia")
        d.ip = ip
    sesion.commit()
    return jsonify({"ok": True, "dispositivo": _dispositivo_json(d)})


@api.delete("/dispositivos/<int:did>")
def borrar_dispositivo(did: int):
    sesion = Sesion()
    d = sesion.get(Dispositivo, did)
    if d is None:
        return jsonify({"ok": False, "mensaje": "El equipo no existe"}), 404
    sesion.delete(d)  # cascada: se llevan sus reglas y su historial
    sesion.commit()
    return jsonify({"ok": True})


@api.get("/dispositivos/<int:did>/estado")
def estado_dispositivo(did: int):
    """Estado en vivo. Si el equipo no contesta se devuelve la posicion que
    surge de nuestra bitacora, marcada como tal para que la interfaz pueda
    aclararlo en vez de fingir que sabe."""
    sesion = Sesion()
    d = sesion.get(Dispositivo, did)
    if d is None:
        return jsonify({"ok": False, "mensaje": "El equipo no existe"}), 404

    salud = chequear_salud(sesion, d)
    if salud["en_linea"]:
        pos, fuente = salud["pos"], "equipo"
    else:
        pos, fuente = posicion_estimada(sesion, d), "bitacora"

    return jsonify(
        {
            "ok": True,
            "dispositivo": _dispositivo_json(d),
            "en_linea": salud["en_linea"],
            "pos": pos,
            "pos_conocida": pos != POSICION_DESCONOCIDA,
            "pos_fuente": fuente,
            "latencia_ms": salud["latencia_ms"],
            "mensaje": "" if salud["en_linea"] else "El equipo no responde",
        }
    )


@api.post("/dispositivos/<int:did>/comando")
def enviar_comando(did: int):
    sesion = Sesion()
    d = sesion.get(Dispositivo, did)
    if d is None:
        return jsonify({"ok": False, "mensaje": "El equipo no existe"}), 404

    datos = request.get_json(silent=True) or {}
    try:
        accion = Accion(datos.get("accion", ""))
    except ValueError:
        raise ErrorDeDatos("Accion desconocida")

    comando = ejecutar_comando(sesion, d, accion, Origen.MANUAL)

    # Tras un comando exitoso la posicion ordenada es la de la accion; tras un
    # fallo se mantiene la anterior, porque el motor no recibio nada.
    pos = (
        comando.accion.posicion
        if comando.resultado is Resultado.OK
        else posicion_estimada(sesion, d)
    )
    if pos is None:
        pos = POSICION_DESCONOCIDA

    cuerpo = {
        "ok": comando.resultado is Resultado.OK,
        "mensaje": MENSAJES[comando.resultado]
        + (f": {comando.detalle}" if comando.detalle and comando.resultado is not Resultado.OK else ""),
        "comando": _comando_json(comando),
        "pos": pos,
        "pos_conocida": pos != POSICION_DESCONOCIDA,
    }
    # 200 siempre: la peticion al servidor Flask se atendio bien; lo que fallo
    # es el enlace con el hardware, y eso viaja en el cuerpo. Asi el JS no
    # tiene que distinguir entre "se cayo el servidor" y "no responde el ESP32".
    return jsonify(cuerpo)


# --------------------------------------------------------------------------
# Programaciones
# --------------------------------------------------------------------------

def _leer_programacion(datos: dict, p: Programacion | None = None) -> Programacion:
    """Valida el formulario y arma (o actualiza) la regla."""
    p = p or Programacion()

    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ErrorDeDatos("Poneles un nombre a la regla")
    p.nombre = nombre

    try:
        p.accion = Accion(datos.get("accion", ""))
    except ValueError:
        raise ErrorDeDatos("Accion desconocida")
    if not p.accion.programable:
        raise ErrorDeDatos("'Parar' no se puede programar: no hay nada que detener")

    try:
        p.tipo_hora = TipoHora(datos.get("tipo_hora", ""))
    except ValueError:
        raise ErrorDeDatos("Elegi si la hora es fija o solar")

    if p.tipo_hora is TipoHora.FIJA:
        crudo = (datos.get("hora_fija") or "").strip()
        try:
            p.hora_fija = dt.time.fromisoformat(crudo)
        except ValueError:
            raise ErrorDeDatos("La hora tiene que estar en formato HH:MM")
        p.evento_solar = None
        p.offset_min = 0
    else:
        try:
            p.evento_solar = EventoSolar(datos.get("evento_solar", ""))
        except ValueError:
            raise ErrorDeDatos("Elegi amanecer o atardecer")
        p.hora_fija = None
        try:
            offset = int(datos.get("offset_min") or 0)
        except (TypeError, ValueError):
            raise ErrorDeDatos("El desfase tiene que ser un numero de minutos")
        if abs(offset) > 180:
            raise ErrorDeDatos("El desfase no puede pasar de 180 minutos")
        p.offset_min = offset

    dias = (datos.get("dias_semana") or "").strip()
    if len(dias) != 7 or set(dias) - {"0", "1"}:
        raise ErrorDeDatos("Los dias se envian como 7 caracteres 0 o 1")
    if "1" not in dias:
        raise ErrorDeDatos("Elegi al menos un dia de la semana")
    p.dias_semana = dias

    p.activa = bool(datos.get("activa", True))
    return p


@api.get("/programaciones")
def listar_programaciones():
    sesion = Sesion()
    consulta = select(Programacion).order_by(Programacion.id)
    did = request.args.get("dispositivo_id", type=int)
    if did is not None:
        consulta = consulta.where(Programacion.dispositivo_id == did)
    ps = sesion.scalars(consulta).all()
    cuerpo = {"ok": True, "programaciones": [_programacion_json(p) for p in ps]}
    if did is not None:
        cuerpo["solapamientos"] = detectar_solapamientos(sesion, did)
    return jsonify(cuerpo)


@api.post("/programaciones")
def crear_programacion():
    sesion = Sesion()
    datos = request.get_json(silent=True) or {}
    did = datos.get("dispositivo_id")
    d = sesion.get(Dispositivo, did) if did else None
    if d is None:
        raise ErrorDeDatos("Elegi a que equipo pertenece la regla")

    p = _leer_programacion(datos)
    p.dispositivo_id = d.id
    sesion.add(p)
    sesion.commit()
    return (
        jsonify(
            {
                "ok": True,
                "programacion": _programacion_json(p),
                "solapamientos": detectar_solapamientos(sesion, d.id),
            }
        ),
        201,
    )


@api.put("/programaciones/<int:pid>")
def editar_programacion(pid: int):
    sesion = Sesion()
    p = sesion.get(Programacion, pid)
    if p is None:
        return jsonify({"ok": False, "mensaje": "La regla no existe"}), 404

    datos = request.get_json(silent=True) or {}
    _leer_programacion(datos, p)
    # Al cambiar el horario se limpia la marca de idempotencia: si la regla se
    # movio de las 07:00 a las 18:00, la de hoy todavia no corrio.
    p.ultima_ejecucion = None
    sesion.commit()
    return jsonify(
        {
            "ok": True,
            "programacion": _programacion_json(p),
            "solapamientos": detectar_solapamientos(sesion, p.dispositivo_id),
        }
    )


@api.post("/programaciones/<int:pid>/activa")
def alternar_programacion(pid: int):
    """Activar o desactivar sin borrar: la regla y su historial se conservan."""
    sesion = Sesion()
    p = sesion.get(Programacion, pid)
    if p is None:
        return jsonify({"ok": False, "mensaje": "La regla no existe"}), 404

    datos = request.get_json(silent=True) or {}
    p.activa = bool(datos.get("activa", not p.activa))
    if p.activa:
        # Al reactivar se limpia la marca para que la regla pueda correr hoy
        # si su hora todavia no paso.
        p.ultima_ejecucion = None
    sesion.commit()
    return jsonify({"ok": True, "programacion": _programacion_json(p)})


@api.delete("/programaciones/<int:pid>")
def borrar_programacion(pid: int):
    sesion = Sesion()
    p = sesion.get(Programacion, pid)
    if p is None:
        return jsonify({"ok": False, "mensaje": "La regla no existe"}), 404
    sesion.delete(p)
    sesion.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Historial
# --------------------------------------------------------------------------

@api.get("/historial")
def historial():
    sesion = Sesion()
    limite = min(request.args.get("limite", default=50, type=int), 500)
    did = request.args.get("dispositivo_id", type=int)

    consulta = select(Comando).order_by(Comando.enviado_en.desc(), Comando.id.desc())
    if did is not None:
        consulta = consulta.where(Comando.dispositivo_id == did)
    cs = sesion.scalars(consulta.limit(limite)).all()

    return jsonify(
        {
            "ok": True,
            "resumen": resumen_historial(sesion, did),
            "comandos": [_comando_json(c) for c in cs],
        }
    )
