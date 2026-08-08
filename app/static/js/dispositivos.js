/* Alta, edicion y baja de equipos ESP32. */

(function () {
  const $ = (id) => document.getElementById(id);
  let equipos = [];
  let editando = null;

  function tarjeta(d) {
    return `
      <article class="tarjeta p-3">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="truncate font-semibold">${esc(d.nombre)}</h3>
            <p class="dato truncate text-xs text-tenue">${esc(d.ip)}</p>
            <p class="mt-1 text-xs text-tenue">
              Ultima respuesta:
              <span class="dato">${horaLocal(d.ultima_respuesta)}</span>
            </p>
          </div>
          <div class="flex shrink-0 flex-col gap-1">
            <button type="button" class="btn h-9 min-h-0 px-3 text-sm" data-probar="${d.id}">Probar</button>
            <button type="button" class="btn h-9 min-h-0 px-3 text-sm" data-editar="${d.id}">Editar</button>
            <button type="button" class="btn h-9 min-h-0 px-3 text-sm text-falla" data-borrar="${d.id}">Quitar</button>
          </div>
        </div>
      </article>`;
  }

  async function cargar() {
    const datos = await pedir("/api/dispositivos");
    if (!datos.ok) {
      avisar(datos.mensaje || "No se pudieron cargar los equipos", "error");
      return;
    }
    equipos = datos.dispositivos;
    $("lista").innerHTML = equipos.length
      ? equipos.map(tarjeta).join("")
      : `<p class="tarjeta p-6 text-center text-sm text-tenue">
           No hay equipos cargados. Agrega el ESP32 con su direccion IP.
         </p>`;
  }

  function abrir(d) {
    editando = d || null;
    $("f-id").value = d ? d.id : "";
    $("f-nombre").value = d ? d.nombre : "";
    $("f-ip").value = d ? d.ip : "";
    $("form").classList.remove("hidden");
    $("f-nombre").focus();
  }

  function cerrar() {
    $("form").classList.add("hidden");
    editando = null;
  }

  async function guardar(e) {
    e.preventDefault();
    const cuerpo = { nombre: $("f-nombre").value, ip: $("f-ip").value };
    const datos = editando
      ? await pedir(`/api/dispositivos/${editando.id}`, { method: "PUT", cuerpo })
      : await pedir("/api/dispositivos", { method: "POST", cuerpo });
    if (!datos.ok) {
      avisar(datos.mensaje || "Revisa los datos del equipo", "error");
      return;
    }
    avisar(editando ? "Equipo actualizado" : "Equipo agregado", "ok");
    cerrar();
    cargar();
  }

  async function probar(id) {
    const datos = await pedir(`/api/dispositivos/${id}/estado`);
    if (datos.ok && datos.en_linea) {
      avisar(`Responde en ${datos.latencia_ms} ms`, "ok");
    } else {
      avisar("El equipo no responde", "error");
    }
    cargar();
  }

  async function borrar(id) {
    const d = equipos.find((x) => x.id === id);
    // confirm() bloquea la pagina pero es la unica barrera antes de borrar el
    // historial completo del equipo, que es dato de evaluacion.
    if (!confirm(`Quitar "${d ? d.nombre : "el equipo"}" y todo su historial?`)) return;
    const datos = await pedir(`/api/dispositivos/${id}`, { method: "DELETE" });
    if (!datos.ok) {
      avisar(datos.mensaje || "No se pudo quitar el equipo", "error");
      return;
    }
    avisar("Equipo quitado", "ok");
    cargar();
  }

  $("lista").addEventListener("click", (e) => {
    const b = e.target.closest("[data-editar],[data-borrar],[data-probar]");
    if (!b) return;
    if (b.dataset.editar) {
      abrir(equipos.find((x) => x.id === Number(b.dataset.editar)));
    } else if (b.dataset.borrar) {
      borrar(Number(b.dataset.borrar));
    } else {
      probar(Number(b.dataset.probar));
    }
  });

  $("btn-nuevo").addEventListener("click", () => abrir(null));
  $("btn-cancelar").addEventListener("click", cerrar);
  $("form").addEventListener("submit", guardar);

  cargar();
})();
