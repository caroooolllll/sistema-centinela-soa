/* ═══════════════════════════════════════════════════════════════
   ASISTENTE CENTINELA v2 — lógica JS
   Cargado dinámicamente DESPUÉS de inyectar asistente.html en el body
   ═══════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  // Guard: evita doble ejecución si el script se carga más de una vez
  if (window.__caInit) return;
  window.__caInit = true;

  console.log('[Asistente] script cargado');

  // ── CONFIG ────────────────────────────────────────────────────────
  const HOST = window.location.hostname || 'localhost';
  const PROTO = window.location.protocol === 'https:' ? 'https:' : 'http:';
  const DJANGO = `${PROTO}//${HOST}:9000`;
  const SDRI   = `${PROTO}//${HOST}:9001`;
  const API_ASISTENTE = `${DJANGO}/api/ia/asistente/`;
  const API_REPORTE   = `${DJANGO}/api/ia/extraer-reporte/`;
  const API_REPORTAR  = `${SDRI}/api/reportar_incidencia`;

  // ── STATE ─────────────────────────────────────────────────────────
  let ttsActivo   = true;
  let micActivo   = false;
  let escucha     = false;
  let typingEl    = null;
  let contRec     = null;
  let manualRec   = null;
  let reporteData = null;

  function escapeXml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  // ── DOM ───────────────────────────────────────────────────────────
  const fab       = document.getElementById('ca-fab');
  const panel     = document.getElementById('ca-panel');
  const closeBtn  = document.getElementById('ca-close');
  const ttsBtn    = document.getElementById('ca-tts-btn');
  const micToggle = document.getElementById('ca-mic-toggle');
  const micBtn    = document.getElementById('ca-mic-btn');
  const input     = document.getElementById('ca-input');
  const sendBtn   = document.getElementById('ca-send');
  const msgs      = document.getElementById('ca-msgs');
  const tbar      = document.getElementById('ca-tbar');
  const tbarText  = document.getElementById('ca-tbar-text');
  const rcard     = document.getElementById('ca-rcard');
  const tooltip   = document.getElementById('ca-tooltip');

  if (!fab || !panel) {
    console.error('[Asistente] FAB o panel no encontrados en el DOM. ¿Se inyectó asistente.html?');
    return;
  }
  console.log('[Asistente] FAB encontrado:', !!fab);

  // ── BIENVENIDA ────────────────────────────────────────────────────
  if (!sessionStorage.getItem('ca-seen')) {
    tooltip.style.display = 'block';
    setTimeout(() => {
      tooltip.classList.add('ca-fade-out');
      setTimeout(() => { tooltip.style.display = 'none'; }, 500);
    }, 4500);
  }

  // ── PANEL TOGGLE ─────────────────────────────────────────────────
  fab.addEventListener('click', () => {
    console.log('[Asistente] click detectado en FAB');
    panel.classList.toggle('ca-open');
    tooltip.style.display = 'none';
    sessionStorage.setItem('ca-seen', '1');
    if (panel.classList.contains('ca-open') && msgs.children.length === 0) {
      agregarMsg('bot',
        '¡Hola! Soy Centinela, tu asistente IA. Puedo ayudarte a:\n' +
        '• Crear un reporte de incidencia\n' +
        '• Mandarle un mensaje a un vecino\n' +
        '• Crear eventos, encuestas o avisos\n' +
        '• Navegar a cualquier sección\n' +
        '• Activar emergencia SOS\n\n' +
        'Escribe o di "Centinela, ..." y yo me encargo.'
      );
    }
  });
  closeBtn.addEventListener('click', () => panel.classList.remove('ca-open'));

  // ── TTS ───────────────────────────────────────────────────────────
  function hablar(texto) {
    if (!ttsActivo || !window.speechSynthesis) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(texto.replace(/[📝💬📅📢🚨✅⚠️📤•\n]/g, ' '));
    u.lang = 'es-MX'; u.rate = 1.05;
    speechSynthesis.speak(u);
  }

  ttsBtn.addEventListener('click', () => {
    ttsActivo = !ttsActivo;
    ttsBtn.textContent = ttsActivo ? '🔊' : '🔇';
    if (!ttsActivo) speechSynthesis.cancel();
  });

  // ── MESSAGES ─────────────────────────────────────────────────────
  function agregarMsg(tipo, texto) {
    const d = document.createElement('div');
    d.className = `ca-msg ca-msg-${tipo}`;
    d.style.whiteSpace = 'pre-line';
    d.textContent = texto;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
    return d;
  }

  function setTyping(on) {
    if (on) {
      typingEl = document.createElement('div');
      typingEl.className = 'ca-msg ca-msg-bot';
      typingEl.innerHTML = '<span class="ca-typing"><span>.</span><span>.</span><span>.</span></span>';
      msgs.appendChild(typingEl);
      msgs.scrollTop = msgs.scrollHeight;
    } else if (typingEl) {
      typingEl.remove(); typingEl = null;
    }
  }

  // ── SEND ─────────────────────────────────────────────────────────
  async function caEnviar(forzado) {
    const texto = (forzado !== undefined ? forzado : input.value).trim();
    if (!texto) return;
    input.value = '';
    rcard.style.display = 'none';
    agregarMsg('user', texto);
    setTyping(true);

    const token = localStorage.getItem('token') || '';
    try {
      const res = await fetch(API_ASISTENTE, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Token ${token}` } : {}),
        },
        body: JSON.stringify({ mensaje: texto }),
      });

      setTyping(false);

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 503) {
          agregarMsg('bot', '⚠️ El servicio de IA no está disponible. Verifica que el backend de Django esté corriendo y que ANTHROPIC_API_KEY esté configurada en el .env.');
        } else {
          agregarMsg('bot', `Error del servidor: ${err.error || res.status}`);
        }
        return;
      }

      const data = await res.json();
      const resp = data.respuesta || '¿En qué más puedo ayudarte?';

      switch (data.tipo) {

        case 'emergencia':
          agregarMsg('bot', '🚨 ' + resp);
          hablar(resp);
          setTimeout(() => { window.location.href = 'panico.html'; }, 2000);
          break;

        case 'navegacion':
          agregarMsg('bot', resp);
          hablar(resp);
          if (data.destino) setTimeout(() => { window.location.href = data.destino; }, 1200);
          break;

        case 'reporte':
          agregarMsg('bot', resp);
          hablar(resp);
          if (data.reporte_completo && data.datos_reporte) {
            await extraerReporte(
              data.datos_reporte.transcripcion || texto,
              data.datos_reporte.prioridad_usuario
            );
          }
          break;

        case 'mensaje_vecino': {
          agregarMsg('bot', resp);
          hablar(resp);
          const dm = data.datos_mensaje;
          if (dm && dm.destinatario) {
            localStorage.setItem('chatPrivadoCon', dm.destinatario);
            if (dm.contenido) localStorage.setItem('chatMensajePendiente', dm.contenido);
            setTimeout(() => { window.location.href = 'chat.html'; }, 1500);
          }
          break;
        }

        case 'nuevo_evento': {
          agregarMsg('bot', resp);
          hablar(resp);
          if (data.datos_evento) {
            localStorage.setItem('centinela_borrador_evento', JSON.stringify(data.datos_evento));
          }
          setTimeout(() => { window.location.href = 'eventos.html'; }, 1500);
          break;
        }

        case 'nueva_encuesta': {
          agregarMsg('bot', resp);
          hablar(resp);
          if (data.datos_encuesta) {
            localStorage.setItem('centinela_borrador_encuesta', JSON.stringify(data.datos_encuesta));
          }
          setTimeout(() => { window.location.href = 'encuestas.html'; }, 1500);
          break;
        }

        case 'nuevo_aviso': {
          agregarMsg('bot', resp);
          hablar(resp);
          if (data.datos_aviso) {
            localStorage.setItem('centinela_borrador_aviso', JSON.stringify(data.datos_aviso));
          }
          setTimeout(() => { window.location.href = 'avisos.html'; }, 1500);
          break;
        }

        case 'incompleto':
          agregarMsg('bot', resp);
          hablar(resp);
          break;

        default:
          agregarMsg('bot', resp);
          hablar(resp);
      }
    } catch (e) {
      setTyping(false);
      agregarMsg('bot', 'No pude conectar con el asistente. Verifica que el backend de Django (:9000) esté corriendo.');
    }
  }

  window.caEnviar = caEnviar;
  input.addEventListener('keydown', e => { if (e.key === 'Enter') caEnviar(); });
  sendBtn.addEventListener('click', () => caEnviar());

  // ── REPORT EXTRACTION → navega a avisos.html con borrador ────────
  async function extraerReporte(transcripcion, prioridadUsuario) {
    const loadEl = agregarMsg('bot', '');
    loadEl.innerHTML = '<span class="ca-typing"><span>.</span><span>.</span><span>.</span></span> Analizando con IA...';

    const token = localStorage.getItem('token') || '';
    try {
      const res = await fetch(API_REPORTE, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Token ${token}` } : {}),
        },
        body: JSON.stringify({ transcripcion }),
      });

      loadEl.remove();
      const datos = await res.json();

      if (datos.error) {
        agregarMsg('bot', `No pude analizar el reporte: ${datos.error}`);
        return;
      }

      localStorage.setItem('centinela_borrador_reporte', JSON.stringify({
        ...datos,
        prioridad_usuario: prioridadUsuario || null,
      }));

      const msg = '📋 Formulario listo. Revísalo en Reportes y pulsa "Enviar reporte" cuando estés listo.';
      agregarMsg('bot', msg);
      hablar('Formulario listo. Te llevo a Reportes.');
      setTimeout(() => { window.location.href = 'avisos.html'; }, 1800);
    } catch (e) {
      loadEl.remove();
      agregarMsg('bot', 'Error al analizar el reporte. Verifica tu conexión con Django :9000.');
    }
  }

  function getPrioLevel(p) {
    return { baja: 1, media: 2, alta: 3, crítica: 4, critica: 4 }[(p || '').toLowerCase()] || 0;
  }

  function mostrarTarjeta(datos, prioridadUsuario) {
    const prioIA   = datos.prioridad || 'Baja';
    const prioUser = prioridadUsuario || prioIA;
    const conflicto = prioridadUsuario &&
      getPrioLevel(prioIA) > getPrioLevel(prioridadUsuario);

    const cat = datos.categoria === 'ambiental' ? 'ambiental' : 'seguridad';
    const catLabel = cat === 'ambiental' ? '🌿 Ambiental' : '🛡️ Seguridad';

    const tiposOpts = cat === 'ambiental'
      ? ['Tiradero clandestino','Fuga de agua','Árbol caído o dañado','Riesgo de incendio o quema','Alumbrado desperdiciando energía','Animal en peligro o maltrato']
      : ['Robo','Vandalismo','Ruido excesivo','Persona sospechosa','Accidente vial','Daño a propiedad','Emergencia médica','Otro'];

    const tipoOptions = tiposOpts.map(t =>
      `<option${t === datos.tipo ? ' selected' : ''}>${t}</option>`
    ).join('');

    const prioOptions = ['Baja','Media','Alta','Crítica'].map(p =>
      `<option${p === prioUser ? ' selected' : ''}>${p}</option>`
    ).join('');

    rcard.innerHTML = `
      <div class="ca-rc-head">
        <span class="ca-rc-badge ${cat}">${catLabel}</span>
        <span class="ca-rc-chip">✨ Llenado por Centinela</span>
      </div>
      ${conflicto ? `
      <div class="ca-rc-alert">
        ⚠️ Dijiste importancia <strong>${prioridadUsuario}</strong>, pero este tipo de incidente suele ser prioridad <strong>${prioIA}</strong>.
        <div class="ca-rc-alert-btns">
          <button class="ca-rc-btn-yes" onclick="caCambiarPrio('${prioIA}')">Sí, cambiar a ${prioIA}</button>
          <button class="ca-rc-btn-no"  onclick="caCambiarPrio('${prioridadUsuario}')">No, dejar en ${prioridadUsuario}</button>
        </div>
      </div>` : ''}
      <div class="ca-rc-body">
        <div class="ca-rc-field">
          <label>Tipo de incidente</label>
          <select id="rc-tipo">${tipoOptions}</select>
        </div>
        <div class="ca-rc-field">
          <label>Prioridad</label>
          <select id="rc-prio">${prioOptions}</select>
        </div>
        <div class="ca-rc-field">
          <label>Ubicación</label>
          <input id="rc-ubic" value="${datos.ubicacion || ''}" placeholder="Ingresa la ubicación..." />
        </div>
        <div class="ca-rc-field">
          <label>Descripción</label>
          <textarea id="rc-desc" rows="3">${datos.descripcion || ''}</textarea>
        </div>
        <div class="ca-rc-field">
          <label>📷 Foto del incidente <span style="font-size:10px;color:#6B9E96;font-weight:normal">(opcional)</span></label>
          <input type="file" id="rc-foto" accept="image/*" style="font-size:11.5px;color:#a0cfc7;cursor:pointer;padding:5px 0;">
          <img id="rc-foto-prev" style="display:none;margin-top:4px;max-width:100%;max-height:100px;border-radius:8px;object-fit:contain;border:1px solid #1E3330;">
        </div>
      </div>
      <div class="ca-rc-actions">
        <button class="ca-btn-primary" id="rc-pub-btn" onclick="caPublicarReporte()">📤 Publicar reporte</button>
        <button class="ca-btn-ghost"   onclick="caOcultarReporte()">Cancelar</button>
      </div>
    `;
    rcard.style.display = 'block';
    const rcFoto = document.getElementById('rc-foto');
    const rcFotoPrev = document.getElementById('rc-foto-prev');
    if (rcFoto && rcFotoPrev) {
      rcFoto.addEventListener('change', () => {
        if (rcFoto.files[0]) {
          rcFotoPrev.src = URL.createObjectURL(rcFoto.files[0]);
          rcFotoPrev.style.display = 'block';
        }
      });
    }
    msgs.scrollTop = msgs.scrollHeight;

    const sug = '💡 Revisa los campos, edita lo que necesites y pulsa "Publicar reporte" cuando estés listo.';
    agregarMsg('bot', sug);
    hablar(sug);
  }

  window.caCambiarPrio = function (p) {
    const sel = document.getElementById('rc-prio');
    if (sel) sel.value = p;
    const alerta = rcard.querySelector('.ca-rc-alert');
    if (alerta) alerta.style.display = 'none';
    agregarMsg('bot', `Prioridad actualizada a ${p}. Tu criterio prevalece.`);
    hablar(`Prioridad actualizada a ${p}.`);
  };

  window.caOcultarReporte = function () { rcard.style.display = 'none'; };

  window.caPublicarReporte = async function () {
    const tipo    = document.getElementById('rc-tipo')?.value || 'Otro';
    const prio    = document.getElementById('rc-prio')?.value || 'Baja';
    const ubic    = document.getElementById('rc-ubic')?.value || '';
    const desc    = document.getElementById('rc-desc')?.value || '';
    const nombre  = localStorage.getItem('usuarioActual') || 'Vecino';
    const pubBtn  = document.getElementById('rc-pub-btn');
    const fotoInp = document.getElementById('rc-foto');

    if (!desc.trim()) {
      agregarMsg('bot', 'Por favor escribe una descripción antes de publicar.');
      return;
    }

    if (pubBtn) { pubBtn.disabled = true; pubBtn.textContent = 'Publicando...'; }

    // Encode photo to base64 if provided
    let imagenesStr = '[]';
    if (fotoInp?.files?.length > 0) {
      try {
        const b64 = await new Promise((resolve, reject) => {
          const fr = new FileReader();
          fr.onload = () => resolve(fr.result);
          fr.onerror = reject;
          fr.readAsDataURL(fotoInp.files[0]);
        });
        imagenesStr = JSON.stringify([b64]);
      } catch (_) { /* skip photo on error */ }
    }

    // Date and time
    const now   = new Date();
    const fecha = now.toISOString().slice(0, 10);
    const hora  = now.toTimeString().slice(0, 8);
    const cat   = reporteData?.categoria || 'seguridad';

    // Build XML — SDRI expects ET.fromstring(request.data)
    const xml = `<reporte>\n  <usuario>${escapeXml(nombre)}</usuario>\n  <descripcion>${escapeXml(desc)}</descripcion>\n  <fecha>${fecha}</fecha>\n  <hora>${hora}</hora>\n  <prioridad>${escapeXml(prio)}</prioridad>\n  <categoria>${escapeXml(cat)}</categoria>\n  <tipo>${escapeXml(tipo)}</tipo>\n  <latitud></latitud>\n  <longitud></longitud>\n  <imagenes>${escapeXml(imagenesStr)}</imagenes>\n</reporte>`;

    try {
      const res = await fetch(API_REPORTAR, {
        method: 'POST',
        headers: { 'Content-Type': 'application/xml' },
        body: xml,
      });

      if (res.ok) {
        rcard.style.display = 'none';
        const ok = '✅ ¡Reporte publicado con éxito! El equipo de Centinela lo atenderá pronto.';
        agregarMsg('bot', ok);
        hablar('Tu reporte fue publicado con éxito.');
      } else {
        const txt = await res.text().catch(() => '');
        console.warn('[CA] SDRI error response:', txt);
        agregarMsg('bot', `Error al publicar (HTTP ${res.status}). Verifica que el SDRI esté corriendo en :9001.`);
        if (pubBtn) { pubBtn.disabled = false; pubBtn.textContent = '📤 Publicar reporte'; }
      }
    } catch (e) {
      agregarMsg('bot', 'No se pudo conectar con el SDRI (:9001). Verifica que el servicio esté corriendo.');
      if (pubBtn) { pubBtn.disabled = false; pubBtn.textContent = '📤 Publicar reporte'; }
    }
  };

  // ── CONTINUOUS VOICE ("Centinela, ...") ──────────────────────────
  function normText(t) {
    return t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function iniciarEscucha() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      agregarMsg('bot', 'Tu navegador no soporta reconocimiento de voz. Usa texto en el campo de abajo.');
      return;
    }

    contRec = new SR();
    contRec.lang = 'es-MX';
    contRec.continuous = true;
    contRec.interimResults = true;
    contRec.maxAlternatives = 3;

    contRec.onstart = () => {
      escucha = true;
      micToggle.classList.add('ca-listening');
      tbar.style.display = 'flex';
      tbarText.textContent = 'Esperando "Centinela..."';
    };

    contRec.onresult = (e) => {
      const todos = [];
      for (let i = e.resultIndex; i < e.results.length; i++) {
        for (let j = 0; j < e.results[i].length; j++) {
          todos.push(e.results[i][j].transcript);
        }
      }

      const textoPrincipal = todos[0] || '';
      tbarText.textContent = textoPrincipal || 'Escuchando...';

      if (!e.results[e.results.length - 1].isFinal) return;

      const norm = normText(textoPrincipal);
      const idx  = norm.indexOf('centinela');
      if (idx < 0) return;

      const comando = textoPrincipal.substring(idx + 9).trim();
      if (comando.length < 3) {
        tbarText.textContent = 'Esperando "Centinela..."';
        return;
      }

      tbarText.textContent = `Procesando: "${comando}"`;
      if (!panel.classList.contains('ca-open')) {
        panel.classList.add('ca-open');
        sessionStorage.setItem('ca-seen', '1');
      }
      caEnviar(comando);
    };

    contRec.onerror = (e) => {
      console.warn('[CA] onerror:', e.error);
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        escucha = false;
        micToggle.classList.remove('ca-listening');
        tbar.style.display = 'none';
        agregarMsg('bot', 'Permiso de micrófono denegado. Actívalo en la configuración del navegador.');
      }
      // no-speech, network, audio-capture: non-fatal — let onend restart
    };

    contRec.onend = () => {
      if (escucha) {
        setTimeout(() => {
          try { contRec.start(); } catch (err) { console.warn('[CA] restart:', err); }
        }, 300);
      } else {
        micToggle.classList.remove('ca-listening');
        tbar.style.display = 'none';
      }
    };

    try {
      contRec.start();
      console.log('[CA] Escucha continua iniciada');
    } catch (e) {
      escucha = false;
      agregarMsg('bot', 'No se pudo iniciar el micrófono. Intenta de nuevo.');
    }
  }

  function detenerEscucha() {
    escucha = false;
    try { contRec?.abort(); } catch (e) {}
    micToggle.classList.remove('ca-listening');
    tbar.style.display = 'none';
  }

  micToggle.addEventListener('click', () => {
    if (escucha) {
      detenerEscucha();
      agregarMsg('bot', 'Escucha continua desactivada.');
    } else {
      iniciarEscucha();
      if (!panel.classList.contains('ca-open')) {
        panel.classList.add('ca-open');
        sessionStorage.setItem('ca-seen', '1');
        if (msgs.children.length === 0) {
          agregarMsg('bot', 'Escucha activada. Di "Centinela" seguido de tu comando.\nEjemplo: "Centinela, abre el chat"');
        }
      } else {
        agregarMsg('bot', '🎤 Escucha activada. Di "Centinela" seguido de tu comando.\nEjemplos:\n• "Centinela, haz un reporte sobre ruido en la calle Rosas"\n• "Centinela, mándale un mensaje a Sofia que diga: la junta es el sábado"\n• "Centinela, crea un evento de reunión vecinal el viernes a las 6pm"\n• "Centinela, publica un aviso de que el agua se corta mañana"');
      }
      hablar('Escucha activada. Di Centinela seguido de tu comando.');
    }
  });

  // ── MANUAL MIC (footer) ──────────────────────────────────────────
  micBtn.addEventListener('click', () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      agregarMsg('bot', 'Tu navegador no soporta reconocimiento de voz.');
      return;
    }
    if (micActivo) {
      manualRec?.stop();
      return;
    }

    manualRec = new SR();
    manualRec.lang = 'es-MX';
    manualRec.continuous = false;
    manualRec.interimResults = true;
    manualRec.maxAlternatives = 3;

    manualRec.onstart = () => {
      micActivo = true;
      micBtn.classList.add('ca-recording');
      input.placeholder = 'Escuchando...';
    };

    manualRec.onresult = (e) => {
      let t = '';
      for (let i = e.resultIndex; i < e.results.length; i++) t += e.results[i][0].transcript;
      input.value = t;
    };

    manualRec.onend = () => {
      micActivo = false;
      micBtn.classList.remove('ca-recording');
      input.placeholder = "Escribe o di 'Centinela, ...'...";
      if (input.value.trim()) caEnviar();
    };

    manualRec.onerror = () => {
      micActivo = false;
      micBtn.classList.remove('ca-recording');
      input.placeholder = "Escribe o di 'Centinela, ...'...";
    };

    manualRec.start();
  });

})();
