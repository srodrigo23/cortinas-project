"""Capa de servicio: el unico punto por donde se comanda el hardware.

Ni las vistas ni el planificador llaman a `cliente_esp32` directamente. Todo
pasa por `ejecutar_comando()`, y esa funcion siempre escribe una fila en
`comandos`. Es una garantia estructural, no una convencion: mientras nadie
importe `cliente_esp32.enviar_accion` desde afuera, la bitacora esta completa y
las metricas del informe (tasa de exito, latencia media) son confiables.
"""

import datetime as dt

from sqlalchemy import func, select

from .cliente_esp32 import POSICION_DESCONOCIDA, consultar_estado, enviar_accion
from .enums import Accion, Origen, Resultado
from .modelos import Comando, Dispositivo, Programacion
from .solar import ahora


def ejecutar_comando(
    sesion,
    dispositivo: Dispositivo,
    accion: Accion,
    origen: Origen,
    programacion: Programacion | None = None,
    programado_para: dt.datetime | None = None,
) -> Comando:
    """Manda la accion al ESP32 y deja el registro. Nunca lanza por red."""
    accion = Accion(accion)
    respuesta = enviar_accion(dispositivo.ip, accion)

    comando = Comando(
        dispositivo_id=dispositivo.id,
        programacion_id=programacion.id if programacion else None,
        accion=accion,
        origen=Origen(origen),
        programado_para=programado_para,
        enviado_en=ahora(),
        latencia_ms=respuesta.latencia_ms,
        resultado=respuesta.resultado,
        detalle=respuesta.detalle[:300],
    )
    sesion.add(comando)

    # Que el equipo conteste -aunque sea con un 409- prueba que esta vivo.
    if respuesta.resultado is not Resultado.TIMEOUT and respuesta.datos:
        dispositivo.ultima_respuesta = ahora()

    sesion.commit()
    return comando


def registrar_omitido(
    sesion,
    dispositivo: Dispositivo,
    programacion: Programacion,
    programado_para: dt.datetime,
    detalle: str,
) -> Comando:
    """Deja constancia de una regla que NO se ejecuto por fuera de la ventana
    de gracia. Sin latencia porque no hubo llamada de red."""
    comando = Comando(
        dispositivo_id=dispositivo.id,
        programacion_id=programacion.id,
        accion=programacion.accion,
        origen=Origen.PROGRAMADO,
        programado_para=programado_para,
        enviado_en=ahora(),
        latencia_ms=None,
        resultado=Resultado.OMITIDO,
        detalle=detalle[:300],
    )
    sesion.add(comando)
    sesion.commit()
    return comando


def chequear_salud(sesion, dispositivo: Dispositivo) -> dict:
    """GET /estado. Actualiza `ultima_respuesta` y devuelve el estado crudo.

    A diferencia de `ejecutar_comando`, esto NO escribe en `comandos`: es una
    consulta de solo lectura y ensuciaria las metricas de comandos enviados.
    """
    respuesta = consultar_estado(dispositivo.ip)
    if respuesta.ok:
        dispositivo.ultima_respuesta = ahora()
        sesion.commit()
    return {
        "en_linea": respuesta.ok,
        "pos": respuesta.pos,
        "detalle": respuesta.detalle,
        "latencia_ms": respuesta.latencia_ms,
    }


def posicion_estimada(sesion, dispositivo: Dispositivo) -> int:
    """Ultima posicion ordenada segun nuestra propia bitacora.

    Es el respaldo para cuando el ESP32 no responde y no podemos preguntarle.
    Se recorre hacia atras porque un `parar` deja la posicion indefinida: si el
    ultimo comando exitoso fue `parar`, la posicion es desconocida y punto, no
    se hereda la del comando anterior.
    """
    ultimo = sesion.scalars(
        select(Comando)
        .where(
            Comando.dispositivo_id == dispositivo.id,
            Comando.resultado == Resultado.OK,
        )
        .order_by(Comando.enviado_en.desc(), Comando.id.desc())
        .limit(1)
    ).first()

    if ultimo is None:
        return POSICION_DESCONOCIDA
    pos = ultimo.accion.posicion
    return POSICION_DESCONOCIDA if pos is None else pos


def resumen_historial(sesion, dispositivo_id: int | None = None) -> dict:
    """Metricas agregadas para la cabecera del historial.

    Los `omitido` cuentan en el total (son eventos del sistema) pero no tienen
    latencia, por eso el promedio se calcula solo sobre los que la tienen.
    """
    filtro = []
    if dispositivo_id is not None:
        filtro.append(Comando.dispositivo_id == dispositivo_id)

    total = sesion.scalar(select(func.count(Comando.id)).where(*filtro)) or 0
    exitosos = (
        sesion.scalar(
            select(func.count(Comando.id)).where(
                Comando.resultado == Resultado.OK, *filtro
            )
        )
        or 0
    )
    latencia = sesion.scalar(
        select(func.avg(Comando.latencia_ms)).where(
            Comando.latencia_ms.is_not(None), *filtro
        )
    )

    return {
        "total": total,
        "exitosos": exitosos,
        "tasa_exito": round(100 * exitosos / total, 1) if total else None,
        "latencia_promedio_ms": round(latencia) if latencia is not None else None,
    }
