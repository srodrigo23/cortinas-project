"""Pruebas del cliente HTTP: el mapeo de cada falla de red a un Resultado.

Se usa `responses` para no depender del ESP32 ni del simulador.
"""

import requests
import responses

from app.cliente_esp32 import (
    POSICION_DESCONOCIDA,
    consultar_estado,
    enviar_accion,
)
from app.enums import Accion, Resultado

IP = "192.168.1.50"
URL_CMD = f"http://{IP}/cmd"
URL_ESTADO = f"http://{IP}/estado"


@responses.activate
def test_200_es_ok_y_trae_la_posicion():
    responses.get(URL_CMD, json={"pos": 75, "cmd": "75 %"}, status=200)

    r = enviar_accion(IP, Accion.P75)

    assert r.resultado is Resultado.OK
    assert r.ok
    assert r.pos == 75
    assert r.latencia_ms >= 0


@responses.activate
def test_manda_la_accion_como_valor_del_enum():
    """El ESP32 espera ?a=p75, no ?a=P75 ni ?a=Accion.P75."""
    responses.get(URL_CMD, json={"pos": 75, "cmd": "75 %"}, status=200)

    enviar_accion(IP, Accion.P75)

    assert responses.calls[0].request.params == {"a": "p75"}


@responses.activate
def test_409_es_error_con_detalle_legible():
    """El firmware rechaza un comando mientras genera otro pulso."""
    responses.get(URL_CMD, json={"error": "pulso en curso"}, status=409)

    r = enviar_accion(IP, Accion.SUBIR)

    assert r.resultado is Resultado.ERROR
    assert "ocupado" in r.detalle.lower()
    assert "pulso en curso" in r.detalle
    # El detalle es para mostrarlo en pantalla: no puede decir "409".
    assert "409" not in r.detalle


@responses.activate
def test_timeout_es_timeout():
    responses.get(URL_CMD, body=requests.exceptions.Timeout())

    r = enviar_accion(IP, Accion.BAJAR)

    assert r.resultado is Resultado.TIMEOUT
    assert "respuesta" in r.detalle.lower()


@responses.activate
def test_equipo_apagado_es_error():
    responses.get(URL_CMD, body=requests.exceptions.ConnectionError("apagado"))

    r = enviar_accion(IP, Accion.BAJAR)

    assert r.resultado is Resultado.ERROR
    assert IP in r.detalle


@responses.activate
def test_otro_codigo_http_es_error():
    responses.get(URL_CMD, json={"error": "boom"}, status=500)

    r = enviar_accion(IP, Accion.SUBIR)

    assert r.resultado is Resultado.ERROR


@responses.activate
def test_respuesta_sin_json_no_revienta():
    """Un portal cautivo o un router respondiendo HTML no debe tirar el panel."""
    responses.get(URL_CMD, body="<html>no soy un ESP32</html>", status=200)

    r = enviar_accion(IP, Accion.SUBIR)

    assert r.resultado is Resultado.OK
    assert r.pos == POSICION_DESCONOCIDA


@responses.activate
def test_el_cliente_nunca_propaga_excepciones_de_red():
    """Todo el sistema depende de esto: `servicios` registra en `comandos` por
    un unico camino, sin try/except alrededor."""
    responses.get(URL_CMD, body=requests.exceptions.SSLError("raro"))

    r = enviar_accion(IP, Accion.SUBIR)

    assert r.resultado is Resultado.ERROR


@responses.activate
def test_estado_devuelve_posicion_desconocida():
    responses.get(URL_ESTADO, json={"pos": -1, "cmd": "ninguno"}, status=200)

    r = consultar_estado(IP)

    assert r.ok
    assert r.pos == POSICION_DESCONOCIDA


@responses.activate
def test_estado_de_un_equipo_caido():
    responses.get(URL_ESTADO, body=requests.exceptions.ConnectionError())

    r = consultar_estado(IP)

    assert not r.ok
    assert r.pos == POSICION_DESCONOCIDA


@responses.activate
def test_acepta_ip_con_puerto():
    responses.get("http://192.168.1.50:8080/cmd", json={"pos": 0, "cmd": "bajar"})

    r = enviar_accion("192.168.1.50:8080", Accion.BAJAR)

    assert r.ok


@responses.activate
def test_acepta_url_completa():
    responses.get("http://esp32.local/cmd", json={"pos": 0, "cmd": "bajar"})

    r = enviar_accion("http://esp32.local", Accion.BAJAR)

    assert r.ok
