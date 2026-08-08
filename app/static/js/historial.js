/* Bitacora de comandos y metricas agregadas. */

(function () {
  const $ = (id) => document.getElementById(id);

  const ESTILO = {
    ok: { punto: "bg-vivo", texto: "Enviado" },
    timeout: { punto: "bg-falla", texto: "Sin respuesta" },
    error: { punto: "bg-falla", texto: "Error" },
    omitido: { punto: "bg-sol", texto: "Omitido" },
  };

  function fila(c) {
    const e = ESTILO[c.resultado] || ESTILO.error;
    const origen =
      c.origen === "programado"
        ? `Programado${c.programacion ? ` · ${esc(c.programacion)}` : ""}`
        : "Manual";
    // Atraso del scheduler: solo tiene sentido en comandos programados.
    let atraso = "";
    if (c.programado_para && c.enviado_en) {
      const d = Math.round(
        (new Date(c.enviado_en) - new Date(c.programado_para)) / 1000
      );
      if (Math.abs(d) >= 1) atraso = ` · atraso <span class="dato">${d}s</span>`;
    }

    return `
      <article class="tarjeta flex items-center gap-3 px-3 py-2">
        <span class="punto ${e.punto}"></span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-semibold">
            ${esc(c.accion_etiqueta)}
            <span class="font-normal text-tenue">· ${esc(c.dispositivo)}</span>
          </p>
          <p class="truncate text-xs text-tenue">${origen}${atraso}</p>
          ${
            c.detalle && c.resultado !== "ok"
              ? `<p class="truncate text-xs text-falla">${esc(c.detalle)}</p>`
              : ""
          }
        </div>
        <div class="shrink-0 text-right">
          <p class="dato text-xs">${esc(c.hora)}</p>
          <p class="dato text-xs text-tenue">
            ${c.latencia_ms != null ? c.latencia_ms + " ms" : "--"}
          </p>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-tenue">${e.texto}</p>
        </div>
      </article>`;
  }

  async function cargar() {
    const did = $("filtro-equipo").value;
    const url = "/api/historial?limite=100" + (did ? `&dispositivo_id=${did}` : "");
    const datos = await pedir(url);
    if (!datos.ok) {
      avisar(datos.mensaje || "No se pudo cargar el historial", "error");
      return;
    }

    const r = datos.resumen;
    $("m-total").textContent = r.total;
    $("m-exito").textContent = r.tasa_exito != null ? r.tasa_exito + " %" : "--";
    $("m-latencia").textContent =
      r.latencia_promedio_ms != null ? r.latencia_promedio_ms + " ms" : "--";

    $("lista").innerHTML = datos.comandos.length
      ? datos.comandos.map(fila).join("")
      : `<p class="tarjeta p-6 text-center text-sm text-tenue">
           Todavia no se envio ningun comando.
         </p>`;
  }

  $("filtro-equipo").addEventListener("change", cargar);
  $("btn-refrescar").addEventListener("click", cargar);
  cargar();
})();
