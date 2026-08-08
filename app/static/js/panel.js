/* Panel de control: indicador de la persiana y los seis botones. */

(function () {
  const equipos = window.EQUIPOS || [];
  if (!equipos.length) return;

  const $ = (id) => document.getElementById(id);
  const botones = Array.from(document.querySelectorAll(".btn-control"));
  const chips = Array.from(document.querySelectorAll("#selector-equipo [data-id]"));

  const POS_DESCONOCIDA = -1;
  let equipo = equipos.find((e) => e.id === EquipoElegido.leer()) || equipos[0];
  let enVuelo = false;
  let temporizador = null;

  /* --- Dibujo ---------------------------------------------------------- */

  function pintarPosicion(pos, fuente) {
    const tela = $("tela");
    const borde = $("borde-tela");
    const conocida = pos !== POS_DESCONOCIDA && pos !== null && pos !== undefined;

    if (!conocida) {
      // Trama diagonal sobre toda la ventana: se declara la ignorancia en vez
      // de dibujar una posicion inventada.
      tela.classList.add("tela-incognita");
      tela.style.height = "100%";
      borde.style.opacity = "0";
      $("lectura").textContent = "--";
      $("lectura-texto").textContent = "Posicion desconocida";
      return;
    }

    tela.classList.remove("tela-incognita");
    // Apertura 100 % = tela totalmente enrollada, ventana despejada.
    tela.style.height = 100 - pos + "%";
    borde.style.opacity = "1";
    borde.style.top = 100 - pos + "%";
    $("lectura").textContent = pos + " %";
    $("lectura-texto").textContent =
      fuente === "bitacora" ? "Ultima orden registrada" : "Ultima orden enviada";
  }

  function pintarConexion(enLinea, latencia) {
    const caja = $("conexion");
    const punto = caja.querySelector(".punto");
    const texto = caja.querySelector("span:last-child");
    if (enLinea) {
      punto.className = "punto bg-vivo";
      texto.textContent = latencia != null ? `En linea · ${latencia} ms` : "En linea";
      caja.classList.remove("text-falla");
    } else {
      punto.className = "punto bg-falla";
      texto.textContent = "Sin respuesta";
      caja.classList.add("text-falla");
    }
  }

  function bloquear(bloqueado, accionEnVuelo) {
    enVuelo = bloqueado;
    botones.forEach((b) => {
      b.disabled = bloqueado;
      if (bloqueado && b.dataset.accion === accionEnVuelo) {
        b.dataset.vuelo = "1";
      } else {
        delete b.dataset.vuelo;
      }
    });
  }

  /* --- Datos ----------------------------------------------------------- */

  async function refrescar() {
    // Mientras un comando esta en vuelo no se pisa la lectura con el sondeo.
    if (enVuelo) return;
    const datos = await pedir(`/api/dispositivos/${equipo.id}/estado`);
    if (!datos.ok) {
      pintarConexion(false, null);
      return;
    }
    pintarConexion(datos.en_linea, datos.latencia_ms);
    pintarPosicion(datos.pos, datos.pos_fuente);
    $("ultima-respuesta").textContent = horaLocal(datos.dispositivo.ultima_respuesta);
  }

  async function enviar(accion, boton) {
    if (enVuelo) return;
    bloquear(true, accion);
    try {
      const datos = await pedir(`/api/dispositivos/${equipo.id}/comando`, {
        method: "POST",
        cuerpo: { accion },
      });
      if (datos.ok) {
        pintarPosicion(datos.pos, "equipo");
        pintarConexion(true, datos.comando ? datos.comando.latencia_ms : null);
      } else {
        avisar(datos.mensaje || "El equipo no responde", "error");
        pintarConexion(false, null);
      }
    } finally {
      bloquear(false);
    }
    refrescar();
  }

  /* --- Cambio de equipo ------------------------------------------------ */

  function seleccionar(id) {
    equipo = equipos.find((e) => e.id === id) || equipo;
    EquipoElegido.guardar(equipo.id);
    $("nombre-equipo").textContent = equipo.nombre;
    $("ip-equipo").textContent = equipo.ip;
    chips.forEach((c) => {
      const activo = Number(c.dataset.id) === equipo.id;
      c.setAttribute("aria-selected", activo ? "true" : "false");
      c.classList.toggle("bg-tinta", activo);
      c.classList.toggle("text-carta", activo);
      c.classList.toggle("border-tinta", activo);
    });
    pintarPosicion(POS_DESCONOCIDA);
    refrescar();
  }

  /* --- Arranque -------------------------------------------------------- */

  botones.forEach((b) =>
    b.addEventListener("click", () => enviar(b.dataset.accion, b))
  );
  chips.forEach((c) =>
    c.addEventListener("click", () => seleccionar(Number(c.dataset.id)))
  );

  seleccionar(equipo.id);

  // Sondeo cada 10 s. Se detiene con la pestana oculta para no golpear al
  // ESP32 con consultas que nadie esta mirando.
  function programarSondeo() {
    clearInterval(temporizador);
    temporizador = setInterval(refrescar, 10000);
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearInterval(temporizador);
    } else {
      refrescar();
      programarSondeo();
    }
  });
  programarSondeo();
})();
