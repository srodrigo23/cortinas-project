/* Utilidades compartidas. JS vanilla, sin framework ni dependencias. */

/**
 * Envoltorio de fetch que devuelve siempre un objeto {ok, mensaje, ...}.
 *
 * La API responde 200 aunque el ESP32 no conteste (el fallo va en el cuerpo),
 * asi que aca solo se atrapan las fallas del servidor Flask y de la red del
 * navegador. Ningun mensaje que llegue a la pantalla menciona codigos HTTP.
 */
async function pedir(url, opciones = {}) {
  const config = { headers: { "Content-Type": "application/json" }, ...opciones };
  if (config.cuerpo !== undefined) {
    config.body = JSON.stringify(config.cuerpo);
    delete config.cuerpo;
  }
  try {
    const r = await fetch(url, config);
    let datos = {};
    try {
      datos = await r.json();
    } catch (_) {
      /* respuesta sin JSON: se cae al mensaje generico de abajo */
    }
    if (!r.ok && datos.mensaje === undefined) {
      return { ok: false, mensaje: "No se pudo completar la operacion" };
    }
    return datos;
  } catch (_) {
    return { ok: false, mensaje: "Se perdio la conexion con el servidor" };
  }
}

/** Aviso breve al pie de la pantalla. */
function avisar(mensaje, tipo = "info") {
  const caja = document.getElementById("avisos");
  if (!caja) return;
  const colores = {
    ok: "border-vivo/50 bg-vivo text-white",
    error: "border-falla/50 bg-falla text-white",
    info: "border-linea bg-tinta text-white",
  };
  const nodo = document.createElement("div");
  nodo.className =
    "mb-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-lg " +
    (colores[tipo] || colores.info);
  nodo.textContent = mensaje;
  caja.appendChild(nodo);
  setTimeout(() => nodo.remove(), 4000);
}

/** Formatea una fecha ISO como hora local legible. */
function horaLocal(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  return d.toLocaleString("es-BO", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Escapa texto que viene de la base antes de meterlo en innerHTML. */
function esc(texto) {
  const d = document.createElement("div");
  d.textContent = texto == null ? "" : String(texto);
  return d.innerHTML;
}

/* Recuerda el ultimo equipo elegido para no obligar a seleccionarlo en cada
   pantalla ni en cada visita. */
const EquipoElegido = {
  leer() {
    const v = localStorage.getItem("equipo");
    return v ? Number(v) : null;
  },
  guardar(id) {
    localStorage.setItem("equipo", String(id));
  },
};
