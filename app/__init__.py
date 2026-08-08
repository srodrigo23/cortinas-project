"""Fabrica de la aplicacion Flask."""

import logging

from flask import Flask

from .bd import Sesion, crear_tablas, iniciar_motor, sembrar_dispositivo_por_defecto
from .config import Config


def create_app(database_url: str | None = None, con_planificador: bool = True) -> Flask:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    app = Flask(__name__)
    app.config.from_object(Config)
    if database_url:
        app.config["DATABASE_URL"] = database_url

    iniciar_motor(app.config["DATABASE_URL"])
    crear_tablas()
    sembrar_dispositivo_por_defecto()

    from .vistas import api, paginas

    app.register_blueprint(paginas)
    app.register_blueprint(api)

    if con_planificador:
        from .planificador import iniciar

        iniciar(Sesion)

    @app.context_processor
    def _globales():
        return {"titulo_app": "Control de persiana"}

    return app


# No se instancia la aplicacion al importar el paquete a proposito: hacerlo
# abriria la base y arrancaria el hilo del planificador con solo hacer
# `import app` desde una prueba o desde un script. `flask --app app run`
# encuentra esta fabrica por si mismo.
