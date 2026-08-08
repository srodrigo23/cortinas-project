"""Enumeraciones del dominio.

Se usan enums en vez de strings sueltos para que un valor invalido falle al
construir el objeto y no al llegar a la base de datos. Todos heredan de `str`
ademas de `Enum` para que Jinja y `json.dumps` los serialicen sin conversiones
manuales en cada plantilla.

Nota sobre persistencia: SQLAlchemy guarda por defecto el NOMBRE del miembro
("SUBIR"), no su valor ("subir"). En `modelos.py` se fuerza el valor con
`values_callable`, porque ese valor es exactamente el que espera el ESP32 en
`GET /cmd?a=...` y asi lo que se lee en la base es lo que se mando por la red.
"""

import enum


class Accion(str, enum.Enum):
    """Las seis acciones del control remoto original."""

    SUBIR = "subir"
    PARAR = "parar"
    BAJAR = "bajar"
    P75 = "p75"
    P50 = "p50"
    P25 = "p25"

    @property
    def etiqueta(self) -> str:
        return {
            Accion.SUBIR: "Subir",
            Accion.PARAR: "Parar",
            Accion.BAJAR: "Bajar",
            Accion.P75: "75 %",
            Accion.P50: "50 %",
            Accion.P25: "25 %",
        }[self]

    @property
    def posicion(self) -> int | None:
        """Posicion que la accion deja ordenada, o None si no la define.

        `parar` detiene la persiana en un punto intermedio arbitrario: despues
        de un `parar` la posicion ordenada deja de ser conocida (-1 en el
        ESP32). Se devuelve None y quien llame decide como mostrarlo.
        """
        return {
            Accion.SUBIR: 100,
            Accion.BAJAR: 0,
            Accion.P75: 75,
            Accion.P50: 50,
            Accion.P25: 25,
            Accion.PARAR: None,
        }[self]

    @property
    def programable(self) -> bool:
        """`parar` no tiene sentido como accion programada: no hay movimiento
        en curso que detener a las 7 de la manana."""
        return self is not Accion.PARAR


class TipoHora(str, enum.Enum):
    FIJA = "fija"
    SOLAR = "solar"


class EventoSolar(str, enum.Enum):
    AMANECER = "amanecer"
    ATARDECER = "atardecer"

    @property
    def etiqueta(self) -> str:
        return "Amanecer" if self is EventoSolar.AMANECER else "Atardecer"


class Origen(str, enum.Enum):
    MANUAL = "manual"
    PROGRAMADO = "programado"


class Resultado(str, enum.Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
    OMITIDO = "omitido"

    @property
    def exitoso(self) -> bool:
        return self is Resultado.OK


# Dias en el mismo orden que `datetime.weekday()`: 0 = lunes ... 6 = domingo.
# El campo `dias_semana` es una cadena de 7 caracteres indexada con weekday(),
# asi que este orden no se puede cambiar sin migrar los datos existentes.
DIAS_SEMANA = ("Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom")
