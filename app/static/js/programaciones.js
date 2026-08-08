/* Gestion de reglas horarias. */

(function () {
  const equipos = window.EQUIPOS || [];
  if (!equipos.length) return;

  const $ = (id) => document.getElementById(id);
  const chips = Array.from(document.querySelectorAll("#selector-equipo [data-id]"));
  const botonesDia = Array.from(document.querySelectorAll("#f-dias .dia"));

  let equipo = equipos.find((e) => e.id === EquipoElegido.leer()) || equipos[0];
  let editando = null;

  /* --- Listado ---------------------------------------------------------- */

  const EVENTOS = { amanecer: "Amanecer", atardecer: "Atardecer" };

  function tarjetaRegla(p) {
    const cuando =
      p.tipo_hora === "solar"
        ? `${EVENTOS[p.evento_solar] || p.evento_solar}${p.offset_min ? ` ${p.offset_min > 0 ? "+" : ""}${p.offset_min} min` : ""}`
        : p.hora_fija.slice(0, 5);

    return `
      <article class="tarjeta p-3 ${p.activa ? "" : "opacity-60"}">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <h3 class="truncate font-semibold">${esc(p.nombre)}</h3>
            <p class="mt-0.5 text-sm text-tenue">
              ${esc(p.accion_etiqueta)} · <span class="dato">${esc(cuando)}</span>
            </p>
            <p class="text-xs text-tenue">${esc(p.dias_legibles)}</p>
          </div>
          <button type="button" class="pastilla shrink-0" data-activar="${p.id}"
                  aria-pressed="${p.activa}">
            <span class="punto ${p.activa ? "bg-vivo" : "bg-linea"}"></span>
            ${p.activa ? "Activa" : "Pausada"}
          </button>
        </div>
        <div class="mt-2 flex items-center justify-between gap-2 border-t border-linea pt-2">
          <p class="text-xs">
            <span class="rotulo">Proxima</span>
            <span class="dato ml-1 font-semibold">${esc(p.proxima_legible)}</span>
          </p>
          <button type="button" class="btn h-9 min-h-0 px-3 text-sm" data-editar="${p.id}">Editar</button>
        </div>
      </article>`;
  }

  let reglas = [];

  async function cargar() {
    const datos = await pedir(`/api/programaciones?dispositivo_id=${equipo.id}`);
    if (!datos.ok) {
      avisar(datos.mensaje || "No se pudieron cargar las reglas", "error");
      return;
    }
    reglas = datos.programaciones;

    $("lista").innerHTML = reglas.length
      ? reglas.map(tarjetaRegla).join("")
      : `<p class="tarjeta p-6 text-center text-sm text-tenue">
           No hay reglas para este equipo. Crea la primera con "Nueva regla".
         </p>`;

    mostrarSolapamientos(datos.solapamientos || []);
  }

  function mostrarSolapamientos(lista) {
    const caja = $("solapamientos");
    if (!lista.length) {
      caja.classList.add("hidden");
      return;
    }
    caja.classList.remove("hidden");
    caja.innerHTML =
      `<p><strong class="font-semibold">Reglas muy juntas.</strong> La segunda pisa a la primera:</p>` +
      `<ul class="mt-1 list-disc pl-4">` +
      lista
        .map(
          (c) =>
            `<li>${esc(c.a)} y ${esc(c.b)} caen a <span class="dato">${c.minutos}</span> min una de otra.</li>`
        )
        .join("") +
      `</ul>`;
  }

  /* --- Formulario ------------------------------------------------------- */

  function leerDias() {
    return botonesDia
      .map((b) => (b.getAttribute("aria-pressed") === "true" ? "1" : "0"))
      .join("");
  }

  function escribirDias(cadena) {
    botonesDia.forEach((b, i) =>
      b.setAttribute("aria-pressed", cadena[i] === "1" ? "true" : "false")
    );
  }

  function alternarTipoHora() {
    const tipo = document.querySelector('input[name="tipo_hora"]:checked').value;
    $("bloque-fija").classList.toggle("hidden", tipo !== "fija");
    $("bloque-solar").classList.toggle("hidden", tipo !== "solar");
  }

  function abrir(p) {
    editando = p || null;
    $("titulo-form").textContent = p ? "Editar regla" : "Nueva regla";
    $("btn-borrar").classList.toggle("hidden", !p);
    $("f-id").value = p ? p.id : "";
    $("f-nombre").value = p ? p.nombre : "";
    $("f-accion").value = p ? p.accion : "bajar";
    $("f-hora").value = p && p.hora_fija ? p.hora_fija.slice(0, 5) : "07:00";
    $("f-evento").value = p && p.evento_solar ? p.evento_solar : "atardecer";
    $("f-offset").value = p ? p.offset_min : 0;
    $("f-activa").checked = p ? p.activa : true;
    escribirDias(p ? p.dias_semana : "1111111");
    document.querySelector(
      `input[name="tipo_hora"][value="${p ? p.tipo_hora : "fija"}"]`
    ).checked = true;
    alternarTipoHora();
    $("capa").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    $("f-nombre").focus();
  }

  function cerrar() {
    $("capa").classList.add("hidden");
    document.body.style.overflow = "";
    editando = null;
  }

  async function guardar(evento) {
    evento.preventDefault();
    const tipo = document.querySelector('input[name="tipo_hora"]:checked').value;
    const cuerpo = {
      dispositivo_id: equipo.id,
      nombre: $("f-nombre").value,
      accion: $("f-accion").value,
      tipo_hora: tipo,
      hora_fija: $("f-hora").value,
      evento_solar: $("f-evento").value,
      offset_min: Number($("f-offset").value || 0),
      dias_semana: leerDias(),
      activa: $("f-activa").checked,
    };

    $("btn-guardar").disabled = true;
    const datos = editando
      ? await pedir(`/api/programaciones/${editando.id}`, { method: "PUT", cuerpo })
      : await pedir("/api/programaciones", { method: "POST", cuerpo });
    $("btn-guardar").disabled = false;

    if (!datos.ok) {
      avisar(datos.mensaje || "Revisa los datos de la regla", "error");
      return;
    }
    avisar(editando ? "Regla actualizada" : "Regla creada", "ok");
    cerrar();
    cargar();
  }

  async function borrar() {
    if (!editando) return;
    const datos = await pedir(`/api/programaciones/${editando.id}`, {
      method: "DELETE",
    });
    if (!datos.ok) {
      avisar(datos.mensaje || "No se pudo eliminar la regla", "error");
      return;
    }
    avisar("Regla eliminada", "ok");
    cerrar();
    cargar();
  }

  async function alternarActiva(id) {
    const p = reglas.find((r) => r.id === id);
    if (!p) return;
    const datos = await pedir(`/api/programaciones/${id}/activa`, {
      method: "POST",
      cuerpo: { activa: !p.activa },
    });
    if (!datos.ok) {
      avisar(datos.mensaje || "No se pudo cambiar el estado", "error");
      return;
    }
    cargar();
  }

  /* --- Eventos ---------------------------------------------------------- */

  $("lista").addEventListener("click", (e) => {
    const editar = e.target.closest("[data-editar]");
    if (editar) {
      const p = reglas.find((r) => r.id === Number(editar.dataset.editar));
      if (p) abrir(p);
      return;
    }
    const activar = e.target.closest("[data-activar]");
    if (activar) alternarActiva(Number(activar.dataset.activar));
  });

  botonesDia.forEach((b) =>
    b.addEventListener("click", () =>
      b.setAttribute(
        "aria-pressed",
        b.getAttribute("aria-pressed") === "true" ? "false" : "true"
      )
    )
  );
  document.querySelectorAll("[data-atajo]").forEach((b) =>
    b.addEventListener("click", () => escribirDias(b.dataset.atajo))
  );
  document
    .querySelectorAll('input[name="tipo_hora"]')
    .forEach((r) => r.addEventListener("change", alternarTipoHora));

  $("btn-nueva").addEventListener("click", () => abrir(null));
  $("btn-cerrar").addEventListener("click", cerrar);
  $("btn-borrar").addEventListener("click", borrar);
  $("form").addEventListener("submit", guardar);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("capa").classList.contains("hidden")) cerrar();
  });

  chips.forEach((c) =>
    c.addEventListener("click", () => {
      equipo = equipos.find((x) => x.id === Number(c.dataset.id)) || equipo;
      EquipoElegido.guardar(equipo.id);
      marcarChips();
      cargar();
    })
  );

  function marcarChips() {
    chips.forEach((c) => {
      const activo = Number(c.dataset.id) === equipo.id;
      c.setAttribute("aria-selected", activo ? "true" : "false");
      c.classList.toggle("bg-tinta", activo);
      c.classList.toggle("text-carta", activo);
      c.classList.toggle("border-tinta", activo);
    });
  }

  marcarChips();
  cargar();
})();
