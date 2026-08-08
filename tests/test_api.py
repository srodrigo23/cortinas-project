"""Pruebas de los endpoints JSON.

El foco esta en dos cosas: que TODO comando quede registrado -la tabla es la
fuente de las metricas del informe- y que los errores que llegan a la pantalla
esten en castellano y sin codigos.
"""

import datetime as dt

from app.cliente_esp32 import RespuestaESP32
from app.enums import Resultado
from app.modelos import Comando, Programacion


def regla_valida(dispositivo_id, **cambios):
    datos = {
        "dispositivo_id": dispositivo_id,
        "nombre": "Bajar de noche",
        "accion": "bajar",
        "tipo_hora": "fija",
        "hora_fija": "19:30",
        "dias_semana": "1111111",
        "activa": True,
    }
    datos.update(cambios)
    return datos


# --------------------------------------------------------------------------
# Comandos manuales
# --------------------------------------------------------------------------

def test_un_comando_manual_queda_registrado(cliente, sesion, dispositivo, esp32_ok):
    r = cliente.post(f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "subir"})

    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    comando = sesion.query(Comando).one()
    assert comando.accion.value == "subir"
    assert comando.origen.value == "manual"
    assert comando.programado_para is None
    assert comando.latencia_ms is not None


def test_un_comando_fallido_tambien_queda_registrado(
    cliente, sesion, dispositivo, monkeypatch
):
    """Es el caso que mas importa: sin la fila, la tasa de exito seria 100 %."""
    monkeypatch.setattr(
        "app.servicios.enviar_accion",
        lambda ip, accion: RespuestaESP32(Resultado.TIMEOUT, 3000, "Sin respuesta en 3 s"),
    )

    r = cliente.post(f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "bajar"})
    cuerpo = r.get_json()

    assert r.status_code == 200  # el servidor Flask atendio bien
    assert cuerpo["ok"] is False
    assert cuerpo["mensaje"].startswith("El equipo no responde")
    assert sesion.query(Comando).count() == 1


def test_el_mensaje_de_error_no_menciona_codigos_http(
    cliente, dispositivo, monkeypatch
):
    monkeypatch.setattr(
        "app.servicios.enviar_accion",
        lambda ip, accion: RespuestaESP32(Resultado.ERROR, 8, "El equipo esta ocupado (pulso en curso)"),
    )

    mensaje = cliente.post(
        f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "subir"}
    ).get_json()["mensaje"]

    assert "500" not in mensaje and "409" not in mensaje
    assert "ocupado" in mensaje.lower()


def test_una_accion_inventada_se_rechaza(cliente, sesion, dispositivo, esp32_ok):
    r = cliente.post(f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "volar"})

    assert r.status_code == 400
    assert "desconocida" in r.get_json()["mensaje"].lower()
    assert sesion.query(Comando).count() == 0  # no se toco la red ni la bitacora


def test_parar_deja_la_posicion_desconocida(cliente, dispositivo, esp32_ok):
    cuerpo = cliente.post(
        f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "parar"}
    ).get_json()

    assert cuerpo["ok"] is True
    assert cuerpo["pos"] == -1
    assert cuerpo["pos_conocida"] is False


def test_subir_deja_la_apertura_en_100(cliente, dispositivo, esp32_ok):
    cuerpo = cliente.post(
        f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "subir"}
    ).get_json()

    assert cuerpo["pos"] == 100
    assert cuerpo["pos_conocida"] is True


def test_comando_a_un_equipo_inexistente(cliente, esp32_ok):
    r = cliente.post("/api/dispositivos/999/comando", json={"accion": "subir"})
    assert r.status_code == 404
    assert "no existe" in r.get_json()["mensaje"]


# --------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------

def test_estado_cae_a_la_bitacora_cuando_el_equipo_no_responde(
    cliente, dispositivo, monkeypatch, esp32_ok
):
    """Se manda un comando con el equipo vivo y luego se lo apaga: la posicion
    mostrada viene de nuestro registro, y se declara de donde salio."""
    cliente.post(f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "p25"})

    monkeypatch.setattr(
        "app.servicios.consultar_estado",
        lambda ip: RespuestaESP32(Resultado.TIMEOUT, 3000, "sin respuesta"),
    )
    cuerpo = cliente.get(f"/api/dispositivos/{dispositivo.id}/estado").get_json()

    assert cuerpo["en_linea"] is False
    assert cuerpo["pos"] == 25
    assert cuerpo["pos_fuente"] == "bitacora"
    assert cuerpo["mensaje"] == "El equipo no responde"


def test_el_chequeo_de_estado_no_ensucia_la_bitacora(
    cliente, sesion, dispositivo, monkeypatch
):
    """`/estado` es de solo lectura: si contara como comando, la tasa de exito
    y la latencia promedio del informe quedarian falseadas."""
    monkeypatch.setattr(
        "app.servicios.consultar_estado",
        lambda ip: RespuestaESP32(Resultado.OK, 10, "", {"pos": 50, "cmd": "50 %"}),
    )

    for _ in range(3):
        cliente.get(f"/api/dispositivos/{dispositivo.id}/estado")

    assert sesion.query(Comando).count() == 0


# --------------------------------------------------------------------------
# Programaciones
# --------------------------------------------------------------------------

def test_alta_de_una_regla(cliente, sesion, dispositivo):
    r = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id))

    assert r.status_code == 201
    p = r.get_json()["programacion"]
    assert p["proxima_ejecucion"] is not None
    assert p["dias_legibles"] == "Todos los dias"
    assert sesion.query(Programacion).count() == 1


def test_una_regla_solar_devuelve_hora_concreta(cliente, dispositivo):
    """La lista tiene que mostrar "06:23", no "amanecer"."""
    r = cliente.post(
        "/api/programaciones",
        json=regla_valida(
            dispositivo.id, tipo_hora="solar", evento_solar="amanecer", offset_min=-20
        ),
    )

    p = r.get_json()["programacion"]
    proxima = dt.datetime.fromisoformat(p["proxima_ejecucion"])
    assert 5 <= proxima.hour <= 7
    assert any(c.isdigit() for c in p["proxima_legible"])


def test_no_se_puede_programar_parar(cliente, dispositivo):
    r = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id, accion="parar"))

    assert r.status_code == 400
    assert "parar" in r.get_json()["mensaje"].lower()


def test_una_regla_sin_dias_se_rechaza(cliente, dispositivo):
    r = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id, dias_semana="0000000"))

    assert r.status_code == 400
    assert "dia" in r.get_json()["mensaje"].lower()


def test_una_hora_mal_escrita_se_rechaza(cliente, dispositivo):
    r = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id, hora_fija="25:99"))

    assert r.status_code == 400
    assert "HH:MM" in r.get_json()["mensaje"]


def test_una_regla_sin_nombre_se_rechaza(cliente, dispositivo):
    r = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id, nombre="  "))
    assert r.status_code == 400


def test_avisa_solapamiento_al_crear(cliente, dispositivo):
    cliente.post("/api/programaciones", json=regla_valida(dispositivo.id, nombre="Una", hora_fija="19:30"))
    r = cliente.post(
        "/api/programaciones", json=regla_valida(dispositivo.id, nombre="Otra", hora_fija="19:32")
    )

    solapamientos = r.get_json()["solapamientos"]
    assert len(solapamientos) == 1
    assert solapamientos[0]["minutos"] == 2


def test_pausar_y_reactivar_sin_borrar(cliente, sesion, dispositivo):
    pid = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id)).get_json()[
        "programacion"
    ]["id"]

    r = cliente.post(f"/api/programaciones/{pid}/activa", json={"activa": False})
    assert r.get_json()["programacion"]["activa"] is False
    assert r.get_json()["programacion"]["proxima_ejecucion"] is None
    assert sesion.query(Programacion).count() == 1  # sigue existiendo

    r = cliente.post(f"/api/programaciones/{pid}/activa", json={"activa": True})
    assert r.get_json()["programacion"]["activa"] is True


def test_editar_limpia_la_marca_de_idempotencia(cliente, sesion, dispositivo):
    pid = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id)).get_json()[
        "programacion"
    ]["id"]
    p = sesion.get(Programacion, pid)
    p.ultima_ejecucion = dt.date(2026, 8, 10)
    sesion.commit()

    cliente.put(f"/api/programaciones/{pid}", json=regla_valida(dispositivo.id, hora_fija="06:00"))

    sesion.refresh(p)
    assert p.ultima_ejecucion is None


def test_borrar_una_regla(cliente, sesion, dispositivo):
    pid = cliente.post("/api/programaciones", json=regla_valida(dispositivo.id)).get_json()[
        "programacion"
    ]["id"]

    assert cliente.delete(f"/api/programaciones/{pid}").get_json()["ok"] is True
    assert sesion.query(Programacion).count() == 0


def test_las_reglas_se_filtran_por_equipo(cliente, sesion, dispositivo):
    otro = cliente.post(
        "/api/dispositivos", json={"nombre": "Dormitorio", "ip": "192.168.1.51"}
    ).get_json()["dispositivo"]

    cliente.post("/api/programaciones", json=regla_valida(dispositivo.id, nombre="Sala"))
    cliente.post("/api/programaciones", json=regla_valida(otro["id"], nombre="Dormitorio"))

    listado = cliente.get(f"/api/programaciones?dispositivo_id={otro['id']}").get_json()
    assert [p["nombre"] for p in listado["programaciones"]] == ["Dormitorio"]


# --------------------------------------------------------------------------
# Dispositivos e historial
# --------------------------------------------------------------------------

def test_alta_de_un_segundo_equipo(cliente, sesion):
    r = cliente.post("/api/dispositivos", json={"nombre": "Dormitorio", "ip": "192.168.1.51"})

    assert r.status_code == 201
    assert len(cliente.get("/api/dispositivos").get_json()["dispositivos"]) == 2


def test_un_equipo_sin_ip_se_rechaza(cliente):
    r = cliente.post("/api/dispositivos", json={"nombre": "Sin IP", "ip": ""})
    assert r.status_code == 400


def test_borrar_un_equipo_se_lleva_su_historial(cliente, sesion, dispositivo, esp32_ok):
    cliente.post(f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": "subir"})
    assert sesion.query(Comando).count() == 1

    cliente.delete(f"/api/dispositivos/{dispositivo.id}")

    assert sesion.query(Comando).count() == 0


def test_resumen_del_historial(cliente, dispositivo, monkeypatch):
    respuestas = [
        RespuestaESP32(Resultado.OK, 10, "ok", {"pos": 100}),
        RespuestaESP32(Resultado.OK, 30, "ok", {"pos": 0}),
        RespuestaESP32(Resultado.TIMEOUT, 3000, "sin respuesta"),
    ]
    monkeypatch.setattr(
        "app.servicios.enviar_accion", lambda ip, accion: respuestas.pop(0)
    )

    for accion in ("subir", "bajar", "subir"):
        cliente.post(f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": accion})

    resumen = cliente.get("/api/historial").get_json()["resumen"]

    assert resumen["total"] == 3
    assert resumen["exitosos"] == 2
    assert resumen["tasa_exito"] == 66.7
    assert resumen["latencia_promedio_ms"] == 1013  # (10 + 30 + 3000) / 3


def test_el_historial_llega_en_orden_descendente(cliente, dispositivo, esp32_ok):
    for accion in ("subir", "bajar", "p50"):
        cliente.post(f"/api/dispositivos/{dispositivo.id}/comando", json={"accion": accion})

    comandos = cliente.get("/api/historial").get_json()["comandos"]

    assert [c["accion"] for c in comandos] == ["p50", "bajar", "subir"]


def test_el_historial_vacio_no_rompe(cliente):
    resumen = cliente.get("/api/historial").get_json()["resumen"]
    assert resumen == {
        "total": 0,
        "exitosos": 0,
        "tasa_exito": None,
        "latencia_promedio_ms": None,
    }


# --------------------------------------------------------------------------
# Paginas
# --------------------------------------------------------------------------

def test_las_paginas_responden(cliente):
    for ruta in ("/", "/programaciones", "/historial", "/dispositivos"):
        assert cliente.get(ruta).status_code == 200, ruta


def test_el_panel_muestra_el_aviso_de_posicion_estimada(cliente):
    html = cliente.get("/").get_data(as_text=True)
    assert "ultima orden enviada" in html
