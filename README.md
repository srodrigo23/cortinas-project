# Control de persiana roller motorizada

Servidor Flask que comanda una persiana roller motorizada a traves de un ESP32
en la red local. Incluye panel web, programacion de horarios por hora fija o
evento solar, y bitacora de todos los comandos enviados.

Proyecto de grado. Universidad Mayor de San Simon, Cochabamba.

---

## Como funciona

El motor es un **AIYUHANG AT25-BE-1.1/30**, un motor tubular a bateria con su
propio controlador, finales de carrera y receptor de radio. Es un producto
cerrado: no se lo comanda directamente.

Un ESP32 emula las pulsaciones del control remoto original mediante tres
optoacopladores PC817 soldados sobre los botones ▲ / ‖ / ▼. Segun el manual del
motor:

| Pulsacion | Boton | Efecto |
|---|---|---|
| corta (~180 ms) | ▲ / ‖ / ▼ | subir / parar / bajar |
| larga (~2.3 s) | ▲ / ‖ / ▼ | posicion favorita 75 % / 50 % / 25 % |

El ESP32 expone una API HTTP que este servidor consume:

```
GET /cmd?a={subir|parar|bajar|p75|p50|p25}
    200 -> {"pos": 75, "cmd": "75 %"}
    409 -> {"error": "pulso en curso"}
GET /estado
    200 -> {"pos": -1, "cmd": "ninguno"}
```

### Limitacion central del sistema

`pos` es la **ultima posicion ordenada, no la posicion real**. El enlace hacia
el motor es unidireccional -se emulan pulsaciones de radio- y no existe
realimentacion de ningun tipo. `pos = -1` significa desconocida.

Esto no se disimula en la interfaz: el panel muestra un aviso permanente, la
lectura dice "ultima orden enviada" y el estado desconocido se dibuja con una
trama diagonal en vez de inventar una posicion. Si alguien usa el control remoto
fisico, el panel queda desfasado hasta la proxima orden.

---

## Instalacion

Requisitos: [uv](https://docs.astral.sh/uv/) y Python 3.12 (uv lo instala solo).

```bash
git clone <este-repositorio>
cd proy-cortinas

uv sync                                      # dependencias
uv run python scripts/tailwind.py obtener    # binario de Tailwind (80 MB, no versionado)
cp .env.example .env                         # configuracion
```

Los mismos comandos sirven en Windows, macOS y Linux. En Windows, el unico
cambio es copiar el `.env` con `copy .env.example .env` (cmd) o
`Copy-Item .env.example .env` (PowerShell). Ver
[Notas para Windows](#notas-para-windows).

La base de datos (`instance/cortinas.db`) no se versiona: la carpeta y el
archivo se crean solos al arrancar la aplicacion por primera vez.

El binario de Tailwind no se versiona por su tamano, pero **el CSS generado
si** (`app/static/css/app.css`): el dia de la demostracion la aplicacion tiene
que arrancar sin el watcher corriendo y sin internet.

### Configuracion (`.env`)

| Variable | Que es | Ejemplo |
|---|---|---|
| `ESP32_IP` | Direccion del ESP32 en la LAN. Acepta host o host:puerto | `192.168.1.50` |
| `LAT` / `LON` | Ubicacion para el calculo solar | `-17.3895` / `-66.1568` |
| `TZ` | Zona horaria | `America/La_Paz` |
| `SECRET_KEY` | Clave de sesion de Flask | cualquier cadena larga |

Al arrancar por primera vez se crea la base y un dispositivo con la IP de
`ESP32_IP`. Se pueden agregar mas desde la pantalla **Equipos**.

---

## Como correrlo

### Desarrollo

```bash
uv run honcho start
```

Levanta dos procesos definidos en el `Procfile`:

- `web`: Flask en <http://0.0.0.0:5000> (accesible desde el celular en la misma red)
- `css`: el watcher de Tailwind, que regenera el CSS al tocar plantillas o JS

Se usa **honcho** y no `concurrently` para no meter Node ni `node_modules` en un
proyecto que por lo demas es 100 % Python. Por la misma razon Tailwind entra por
su binario standalone y no por npm.

### Sin el hardware conectado

```bash
uv run python scripts/simular_esp32.py
```

Levanta un ESP32 falso en `127.0.0.1:8080` que replica la API del firmware,
incluidos el 409 mientras hay un pulso en curso y la duracion real de las
pulsaciones. Opciones utiles para probar los caminos de error:

```bash
# forzar el timeout de 3 s del cliente
uv run python scripts/simular_esp32.py --latencia 4000

# una de cada cuatro peticiones falla
uv run python scripts/simular_esp32.py --fallas 0.25
```

### Demostracion

```bash
uv run python scripts/tailwind.py construir                  # una sola vez
uv run flask --app app run --host 0.0.0.0 --port 5000
```

Sin watcher y sin honcho. El CSS minificado ya esta en el repositorio.

### Notas para Windows

- **Base de datos.** Se crea sola en `instance/cortinas.db`. Si se define
  `DATABASE_URL` a mano, usar barras normales:
  `sqlite:///C:/ruta/al/proyecto/instance/cortinas.db`.
- **Zona horaria.** Windows no trae la base de zonas IANA que usa `zoneinfo`;
  `uv sync` instala el paquete `tzdata` solo en Windows para cubrirlo.
- **Tailwind.** `scripts/tailwind.py` descarga `bin/tailwindcss.exe` y el
  `Procfile` ya lo usa; no hace falta bash ni curl.
- **Firewall.** La primera vez que Flask escuche en `0.0.0.0`, Windows pregunta
  si permitir Python en redes privadas. Hay que aceptarlo para entrar desde el
  celular.
- **`TZ` en el `.env`.** El runtime de C de Windows no entiende nombres como
  `America/La_Paz` y puede mostrar las horas de los logs en UTC. No afecta a la
  aplicacion, que siempre calcula con la zona de `TZ` a traves de `zoneinfo`.

### Pruebas

```bash
uv run pytest
```

---

## Estructura

```
app/
  enums.py           Accion, TipoHora, EventoSolar, Origen, Resultado
  modelos.py         dispositivos, programaciones, comandos
  bd.py              engine y scoped_session; siembra inicial
  solar.py           amanecer y atardecer con astral
  cliente_esp32.py   unico modulo que habla por la red con el hardware
  servicios.py       unico punto que comanda y registra en `comandos`
  planificador.py    hilo de fondo, tick cada 30 s, proxima ejecucion
  vistas/            paginas Jinja y endpoints JSON
scripts/             simulador del ESP32 y utilidades de build
tests/               pytest
```

### Dos decisiones de arquitectura

**`servicios.ejecutar_comando()` es el unico camino al hardware.** Ni las
vistas ni el planificador llaman al cliente HTTP directamente, y esa funcion
siempre escribe una fila en `comandos`. Es una garantia estructural de que la
bitacora esta completa, que es lo que hace confiables las metricas de
evaluacion (tasa de exito, latencia media).

**`proxima_ejecucion()` la usan el planificador y la interfaz.** La lista de
reglas muestra la hora concreta calculada -"Hoy 17:58"- y no la palabra
"atardecer". Al vivir el calculo en un solo modulo, lo que se ve en pantalla y
lo que hace el scheduler no pueden divergir.

---

## Problemas encontrados y como se resolvieron

Los tres estan comentados en `planificador.py` y cubiertos por pruebas en
`tests/test_planificador.py`.

**Comandos repetidos.** El tick corre cada 30 s y una regla de las 07:00 sigue
estando "en hora" durante toda la ventana de gracia, asi que se disparaba una y
otra vez. Se resolvio con `ultima_ejecucion`, comparada contra la **fecha** y no
contra la hora: la pregunta no es cuando corrio sino si ya corrio hoy.

**Rafaga de comandos al despertar la laptop.** Al reanudar a las 15:00, todas
las reglas de la manana estaban vencidas y se ejecutaban uno detras de otro: la
persiana subia y bajaba sola varias veces. Se agrego una **ventana de gracia de
15 minutos**: pasada esa ventana la regla se registra como `omitido` y no se
ejecuta. El registro importa, porque omitir en silencio haria imposible
distinguir "no habia regla" de "la regla se perdio" al leer la bitacora.

**Todo duplicado en modo debug.** `flask run --debug` levanta dos procesos por
el reloader de Werkzeug y quedaban dos schedulers compitiendo. Se agrego una
guarda en `planificador.iniciar()`: con el reloader activo, el hilo solo arranca
en el proceso hijo (`WERKZEUG_RUN_MAIN == "true"`).

**Flask colgado con el ESP32 apagado.** Sin `timeout` en `requests`, una
peticion a un equipo apagado dejaba el worker esperando minutos y el panel se
congelaba. Ahora toda llamada lleva `timeout=3` y el cliente traduce cada falla
de red a un `Resultado` en vez de propagar la excepcion.

---

## Supuestos

- **Bolivia no aplica horario de verano.** El pais no cambia de huso desde 1932,
  asi que `America/La_Paz` es UTC-4 todo el ano y un datetime local nunca es
  ambiguo ni inexistente. Esta escrito en `solar.py`; si el sistema se llevara a
  un pais con DST, `hora_fija_del_dia()` es el punto a revisar.
- El servidor y el ESP32 estan en la misma red local. No hay autenticacion:
  no exponer el puerto a internet.
- Un comando programado que falla por red **no se reintenta**. Reintentar
  significaria golpear un equipo caido cada 30 s durante toda la ventana; el
  fallo queda en el historial y esa es la via para enterarse.
