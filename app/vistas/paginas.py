"""Rutas que devuelven HTML. Jinja arma el esqueleto y el JS lo rellena."""

from flask import Blueprint, redirect, render_template, url_for
from sqlalchemy import select

from ..bd import Sesion
from ..enums import DIAS_SEMANA, Accion, EventoSolar
from ..modelos import Dispositivo

paginas = Blueprint("paginas", __name__)


@paginas.teardown_request
def _cerrar_sesion(exc):
    Sesion.remove()


def _dispositivos():
    return Sesion().scalars(select(Dispositivo).order_by(Dispositivo.id)).all()


def _equipos_json(ds):
    """Version serializable para que el JS pueda cambiar de equipo sin ir al
    servidor a buscar el nombre y la IP."""
    return [{"id": d.id, "nombre": d.nombre, "ip": d.ip} for d in ds]


@paginas.get("/")
def panel():
    ds = _dispositivos()
    return render_template(
        "panel.html",
        dispositivos=ds,
        equipos_json=_equipos_json(ds),
        acciones=list(Accion),
        activo="panel",
    )


@paginas.get("/programaciones")
def programaciones():
    ds = _dispositivos()
    return render_template(
        "programaciones.html",
        dispositivos=ds,
        equipos_json=_equipos_json(ds),
        acciones=[a for a in Accion if a.programable],
        eventos=list(EventoSolar),
        dias=DIAS_SEMANA,
        activo="programaciones",
    )


@paginas.get("/historial")
def historial():
    ds = _dispositivos()
    return render_template(
        "historial.html",
        dispositivos=ds,
        equipos_json=_equipos_json(ds),
        activo="historial",
    )


@paginas.get("/dispositivos")
def dispositivos():
    ds = _dispositivos()
    return render_template(
        "dispositivos.html",
        dispositivos=ds,
        equipos_json=_equipos_json(ds),
        activo="dispositivos",
    )


@paginas.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.svg"))
