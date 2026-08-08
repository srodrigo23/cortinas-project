"""Modelo de datos (SQLAlchemy 2.0 declarativo).

Se usa SQLAlchemy "pelado" en vez de Flask-SQLAlchemy a proposito: el
planificador corre en un hilo de fondo, fuera de cualquier request. Con
Flask-SQLAlchemy ese hilo necesita un `app_context()` empujado a mano en cada
tick para poder tocar `db.session`. Con una `scoped_session` propia (ver
`bd.py`) el hilo abre su sesion y la cierra, sin depender de Flask.
"""

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as EnumSQL,
    ForeignKey,
    Integer,
    String,
    Time,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import Accion, EventoSolar, Origen, Resultado, TipoHora


class Base(DeclarativeBase):
    pass


def _enum(tipo, nombre):
    """Columna Enum que guarda el VALOR del miembro, no su nombre.

    Sin `values_callable` SQLAlchemy escribiria 'SUBIR' en la base; queremos
    'subir', que es literalmente lo que viaja en `GET /cmd?a=subir`.
    """
    return EnumSQL(
        tipo,
        name=nombre,
        values_callable=lambda e: [m.value for m in e],
        native_enum=False,  # SQLite no tiene ENUM nativo: VARCHAR + CHECK
    )


class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    ip: Mapped[str] = mapped_column(String(64))
    # Ultimo momento en que el ESP32 contesto algo. None = nunca contesto.
    ultima_respuesta: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    programaciones: Mapped[list["Programacion"]] = relationship(
        back_populates="dispositivo", cascade="all, delete-orphan"
    )
    comandos: Mapped[list["Comando"]] = relationship(
        back_populates="dispositivo", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Dispositivo {self.id} {self.nombre!r} {self.ip}>"


class Programacion(Base):
    __tablename__ = "programaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispositivo_id: Mapped[int] = mapped_column(
        ForeignKey("dispositivos.id", ondelete="CASCADE")
    )
    nombre: Mapped[str] = mapped_column(String(120))
    accion: Mapped[Accion] = mapped_column(_enum(Accion, "accion"))

    tipo_hora: Mapped[TipoHora] = mapped_column(_enum(TipoHora, "tipo_hora"))
    # Solo uno de los dos bloques siguientes esta poblado, segun `tipo_hora`.
    hora_fija: Mapped[dt.time | None] = mapped_column(Time, default=None)
    evento_solar: Mapped[EventoSolar | None] = mapped_column(
        _enum(EventoSolar, "evento_solar"), default=None
    )
    # Minutos con signo respecto del evento solar: -15 = quince minutos antes.
    offset_min: Mapped[int] = mapped_column(Integer, default=0)

    # Cadena de 7 caracteres '0'/'1' indexada con datetime.weekday().
    # '1111100' = de lunes a viernes.
    dias_semana: Mapped[str] = mapped_column(String(7), default="1111111")
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    # Fecha (no datetime) del ultimo dia en que esta regla ya se resolvio,
    # sea ejecutada u omitida. Es la clave de la idempotencia: ver planificador.
    ultima_ejecucion: Mapped[dt.date | None] = mapped_column(Date, default=None)
    creada_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )

    dispositivo: Mapped[Dispositivo] = relationship(back_populates="programaciones")

    def corre_el_dia(self, weekday: int) -> bool:
        """weekday en formato datetime.weekday(): 0 = lunes."""
        return len(self.dias_semana) == 7 and self.dias_semana[weekday] == "1"

    @property
    def dias_legibles(self) -> str:
        from .enums import DIAS_SEMANA

        if self.dias_semana == "1111111":
            return "Todos los dias"
        if self.dias_semana == "1111100":
            return "Lunes a viernes"
        if self.dias_semana == "0000011":
            return "Fines de semana"
        marcados = [d for d, c in zip(DIAS_SEMANA, self.dias_semana) if c == "1"]
        return ", ".join(marcados) if marcados else "Ningun dia"

    def __repr__(self) -> str:
        return f"<Programacion {self.id} {self.nombre!r}>"


class Comando(Base):
    """Bitacora de TODO comando enviado al ESP32.

    Manual o programado, exitoso o fallido: todo pasa por
    `servicios.ejecutar_comando()` y todo deja una fila aca. Esta tabla es la
    fuente de las metricas de evaluacion del proyecto (tasa de exito, latencia),
    asi que un comando sin registrar es un dato perdido para el informe.
    """

    __tablename__ = "comandos"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispositivo_id: Mapped[int] = mapped_column(
        ForeignKey("dispositivos.id", ondelete="CASCADE")
    )
    programacion_id: Mapped[int | None] = mapped_column(
        ForeignKey("programaciones.id", ondelete="SET NULL"), default=None
    )
    accion: Mapped[Accion] = mapped_column(_enum(Accion, "accion"))
    origen: Mapped[Origen] = mapped_column(_enum(Origen, "origen"))

    # Hora a la que la regla DEBIA disparar. None en comandos manuales.
    # La diferencia con `enviado_en` es el atraso del scheduler, un dato que se
    # reporta en el informe.
    programado_para: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    enviado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    # None cuando no hubo llamada de red (caso `omitido`).
    latencia_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    resultado: Mapped[Resultado] = mapped_column(_enum(Resultado, "resultado"))
    detalle: Mapped[str] = mapped_column(String(300), default="")

    dispositivo: Mapped[Dispositivo] = relationship(back_populates="comandos")
    programacion: Mapped[Programacion | None] = relationship()

    def __repr__(self) -> str:
        return f"<Comando {self.id} {self.accion} {self.resultado}>"
