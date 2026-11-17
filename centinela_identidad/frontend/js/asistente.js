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
  // Pipeline rápido (streaming + Whisper + edge-tts). El endpoint clásico de arriba queda de respaldo.
  const API_STREAM = `${DJANGO}/api/ia/asistente/stream/`;
  const API_STT    = `${DJANGO}/api/ia/stt/`;
  const API_TTS    = `${DJANGO}/api/ia/tts/`;
  const API_SOS    = `${DJANGO}/api/ia/sos-aviso/`;
  const API_ESTADO = `${DJANGO}/api/ia/estado/`;

  // Atajos locales (SOS / navegación) — se cargan junto al asistente, sin tocar las páginas
  (function () {
    if (window.CentinelaAtajos) return;
    const base = (document.currentScript && document.currentScript.src)
      ? document.currentScript.src.replace(/asistente\.js.*$/, '') : 'js/';
    const s = document.createElement('script');
    s.src = base + 'asistente-atajos.js';
    document.head.appendChild(s);
  })();

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
  // Voz por partes: cada oración se pide a edge-tts (es-MX-DaliaNeural) en cuanto llega y se
  // reproduce en orden. Si el servidor de voz falla → speechSynthesis del navegador (como antes).
  const vozCola = [];            // [{texto, promesaAudio}]
  let vozReproduciendo = false;
  let vozAudio = null;
  let vozEpoca = 0;              // sube con cada interrupción: invalida lo pendiente
  // Blindaje: si edge-tts no entrega el PRIMER audio en 1.2 s (o falla), esa respuesta completa se dice
  // con la voz del navegador. La siguiente respuesta vuelve a intentar edge-tts automáticamente.
  const VOZ_PRIMER_AUDIO_MS = 1200;
  let vozRespNavegador = false;  // true = lo que queda de esta respuesta usa la voz del navegador
  let vozPrimeraFrase = true;    // la próxima oración es la primera de una respuesta
  let ultimoHablado = '';
  const vozWaiters = [];

  function limpiarParaVoz(t) {
    return String(t).replace(/[\u{1F000}-\u{1FAFF}☀-➿•*_#`\n]/gu, ' ').replace(/\s+/g, ' ').trim();
  }

  function pedirAudio(texto, primero) {
    if (vozRespNavegador || navigator.onLine === false) return Promise.resolve(null);
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), primero ? VOZ_PRIMER_AUDIO_MS : 4000);
    return fetch(API_TTS, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto }), signal: ctl.signal,
    }).then(r => {
      if (!r.ok) throw new Error('tts ' + r.status);
      return r.blob();
    }).then(b => {
      if (b.size <= 200) throw new Error('tts vacío');
      return URL.createObjectURL(b);
    }).catch(() => {
      vozRespNavegador = true;      // esta respuesta sigue con la voz del navegador, sin esperar más
      return null;
    }).finally(() => clearTimeout(to));
  }

  function hablarNavegador(texto) {
    return new Promise(res => {
      if (!window.speechSynthesis) return res();
      const u = new SpeechSynthesisUtterance(texto);
      u.lang = 'es-MX'; u.rate = 1.05;
      u.onend = u.onerror = () => res();
      speechSynthesis.speak(u);
    });
  }

  function tocarUrl(url) {
    return new Promise(res => {
      const a = new Audio(url);
      vozAudio = a;
      a.onended = a.onerror = () => { URL.revokeObjectURL(url); res(); };
      a.play().catch(() => { URL.revokeObjectURL(url); res(); });
    });
  }

  function vozOciosa() {
    if (vozReproduciendo || vozCola.length) return;
    vozRespNavegador = false;   // reintento automático de edge-tts en la siguiente respuesta
    vozPrimeraFrase = true;
    setEstado(null);
    while (vozWaiters.length) vozWaiters.shift()();
  }

  async function bombaVoz() {
    if (vozReproduciendo) return;
    vozReproduciendo = true;
    const epoca = vozEpoca;
    while (vozCola.length && epoca === vozEpoca) {
      const item = vozCola.shift();
      const url = await item.promesaAudio;
      if (epoca !== vozEpoca) break;
      setEstado('hablando');
      if (url && !vozRespNavegador) await tocarUrl(url);
      else { if (url) URL.revokeObjectURL(url); await hablarNavegador(item.texto); }
    }
    if (epoca === vozEpoca) vozReproduciendo = false;
    vozOciosa();
  }

  function hablar(texto) {
    if (!ttsActivo) return;
    const t = limpiarParaVoz(texto);
    if (!t) return;
    ultimoHablado = (ultimoHablado + ' ' + t).slice(-600);
    const primero = vozPrimeraFrase;
    vozPrimeraFrase = false;
    vozCola.push({ texto: t, promesaAudio: pedirAudio(t, primero) });
    bombaVoz();
  }

  // Interrumpir: silencia todo lo que se está diciendo o está en cola
  function callarVoz() {
    vozEpoca++;
    vozCola.length = 0;
    vozReproduciendo = false;
    vozRespNavegador = false;
    vozPrimeraFrase = true;
    ultimoHablado = '';
    try { if (vozAudio) { vozAudio.pause(); vozAudio.src = ''; } } catch (_) {}
    vozAudio = null;
    try { window.speechSynthesis && speechSynthesis.cancel(); } catch (_) {}
    vozOciosa();
  }

  function esperarVoz(maxMs) {
    if (!ttsActivo || (!vozReproduciendo && !vozCola.length)) return Promise.resolve();
    return new Promise(res => {
      const t = setTimeout(res, maxMs);
      vozWaiters.push(() => { clearTimeout(t); res(); });
    });
  }

  // ── Chips de estado + proveedor (demo) ───────────────────────────
  const statusBar  = document.getElementById('ca-status');
  const stateChip  = document.getElementById('ca-state-chip');
  const provEl     = document.getElementById('ca-prov');
  const ESTADOS = {
    escuchando: 'Escuchando…', pensando: 'Pensando…', consultando_avisos: 'Consultando avisos…',
    hablando: 'Hablando…', transcribiendo: 'Transcribiendo…',
  };
  function setEstado(e) {
    if (!statusBar) return;
    if (!e) { stateChip.textContent = ''; stateChip.style.display = 'none'; if (!provEl.textContent) statusBar.classList.remove('ca-on'); return; }
    stateChip.textContent = ESTADOS[e] || e;
    stateChip.style.display = '';
    statusBar.classList.add('ca-on');
  }
  const PROV_NOMBRE = { groq: 'Groq', gemini: 'Gemini', claude: 'Claude', local: 'Local', atajo: 'Atajo local', bitacora: 'Bitácora de accesos', ninguno: '—' };
  function mostrarProveedor(nombre, ms) {
    if (!provEl) return;
    provEl.textContent = `⚡ ${PROV_NOMBRE[nombre] || nombre}${ms != null ? ' · ' + ms + ' ms' : ''}`;
    statusBar.classList.add('ca-on');
  }

  // ── Modo feria: avisa por voz del navegador si se cae el internet (atajos y respuestas locales siguen) ──
  let modoFeria = false;
  function avisoSinInternet() {
    const m = 'Sin internet. Puedo abrir secciones y activar emergencia.';
    agregarMsg('bot', '📴 ' + m);
    if (ttsActivo) hablarNavegador(m);
  }
  fetch(API_ESTADO).then(r => r.json()).then(j => {
    modoFeria = !!j.modo_feria;
    if (modoFeria && j.internet === false) avisoSinInternet();
  }).catch(() => {});
  window.addEventListener('offline', () => { if (modoFeria) avisoSinInternet(); });
  window.addEventListener('online', () => {
    if (!modoFeria) return;
    agregarMsg('bot', '📶 Conexión recuperada.');
    if (ttsActivo) hablarNavegador('Conexión recuperada.');
  });

  ttsBtn.addEventListener('click', () => {
    ttsActivo = !ttsActivo;
    ttsBtn.textContent = ttsActivo ? '🔊' : '🔇';
    if (!ttsActivo) callarVoz();
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
  // ── Ejecuta la acción del asistente (contrato original: tipos, destinos y borradores en localStorage) ──
  function irA(url, msEspera, inmediato) {
    if (inmediato) { window.location.href = url; return; }
    if (!ttsActivo) { setTimeout(() => { window.location.href = url; }, Math.min(msEspera, 600)); return; }
    esperarVoz(4000).then(() => setTimeout(() => { window.location.href = url; }, 250));
  }

  async function ejecutarAccion(data, texto, yaHablado) {
    const resp = data.respuesta || '¿En qué más puedo ayudarte?';
    const decir = (m) => { if (!yaHablado) { agregarMsg('bot', m); hablar(m); } };
    // ACTIVAR_SOS: el LLM o el atajo pidió emergencia aunque el tipo venga distinto
    if (data.activar_sos && data.tipo !== 'emergencia') data = { ...data, tipo: 'emergencia' };

    switch (data.tipo) {

      case 'emergencia':
        // Si lo pidió el LLM (no el atajo local) no se activa solo: se pide confirmación
        if (data.requiere_confirmacion && !confirm('El asistente detectó una posible emergencia. ¿Abrir el botón de pánico?')) {
          if (!yaHablado) decir(resp);
          break;
        }
        if (!yaHablado) { agregarMsg('bot', '🚨 ' + resp); hablar(resp); }
        irA('panico.html', 0, true);
        break;

      case 'navegacion':
        decir(resp);
        if (data.destino) irA(data.destino, 1200);
        break;

      case 'reporte':
        decir(resp);
        if (data.reporte_completo && data.datos_reporte) {
          await extraerReporte(
            data.datos_reporte.transcripcion || texto,
            data.datos_reporte.prioridad_usuario
          );
        }
        break;

      case 'mensaje_vecino': {
        decir(resp);
        const dm = data.datos_mensaje;
        if (dm && dm.destinatario) {
          localStorage.setItem('chatPrivadoCon', dm.destinatario);
          if (dm.contenido) localStorage.setItem('chatMensajePendiente', dm.contenido);
          irA('chat.html', 1500);
        }
        break;
      }

      case 'nuevo_evento': {
        decir(resp);
        if (data.datos_evento) {
          localStorage.setItem('centinela_borrador_evento', JSON.stringify(data.datos_evento));
        }
        irA('eventos.html', 1500);
        break;
      }

      case 'nueva_encuesta': {
        decir(resp);
        if (data.datos_encuesta) {
          localStorage.setItem('centinela_borrador_encuesta', JSON.stringify(data.datos_encuesta));
        }
        irA('encuestas.html', 1500);
        break;
      }

      case 'nuevo_aviso': {
        decir(resp);
        if (data.datos_aviso) {
          localStorage.setItem('centinela_borrador_aviso', JSON.stringify(data.datos_aviso));
        }
        irA('avisos.html', 1500);
        break;
      }

      case 'incompleto':
        decir(resp);
        break;

      default:
        decir(resp);
    }
  }

  // ═══ PIPELINE RÁPIDO ═════════════════════════════════════════════
  // 1) atajos locales (SOS / navegación) sin red ni LLM  2) streaming del LLM con voz por oraciones
  // 3) si el streaming falla antes de dar texto → flujo clásico de siempre (Claude, JSON único)
  const historial = [];
  let abortStream = null;

  // Texto que aparece poco a poco (efecto de escritura sobre el mensaje del bot)
  function escribirGradual(el, completo) {
    el.__meta = el.__meta || { shown: 0, target: '', timer: null };
    const m = el.__meta;
    m.target = completo;
    if (m.timer) return;
    m.timer = setInterval(() => {
      m.shown = Math.min(m.target.length, m.shown + 3);
      el.textContent = m.target.slice(0, m.shown);
      msgs.scrollTop = msgs.scrollHeight;
      if (m.shown >= m.target.length) { clearInterval(m.timer); m.timer = null; }
    }, 16);
  }

  function activarSOSLocal(texto, atajo) {
    // Sin esperar a nada: ni IA ni internet. El aviso al backend es "dispara y olvida" (queda en el log).
    agregarMsg('bot', '🚨 ' + atajo.respuesta);
    mostrarProveedor('atajo', 0);
    try {
      fetch(API_SOS, { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto }) }).catch(() => {});
    } catch (_) {}
    window.location.href = atajo.destino || 'panico.html';
  }

  async function caEnviar(forzado) {
    const texto = (forzado !== undefined ? forzado : input.value).trim();
    if (!texto) return;
    callarVoz();                       // interrumpe lo que esté diciendo
    if (abortStream) { abortStream.abort(); abortStream = null; }
    input.value = '';
    rcard.style.display = 'none';
    agregarMsg('user', texto);

    const A = window.CentinelaAtajos;
    const atajo = A && A.resolver(texto);
    if (atajo) {
      if (atajo.activar_sos) { activarSOSLocal(texto, atajo); return; }
      agregarMsg('bot', atajo.respuesta);
      mostrarProveedor('atajo', 0);
      setTimeout(() => { window.location.href = atajo.destino; }, 150);
      return;
    }
    await caEnviarRapido(texto);
  }

  async function caEnviarRapido(texto) {
    const ctl = new AbortController();
    abortStream = ctl;
    const token = localStorage.getItem('token') || '';
    let el = null, acum = '', hayTexto = false, accion = null, fin = null;
    setEstado('pensando');
    setTyping(true);
    try {
      const res = await fetch(API_STREAM, {
        method: 'POST', signal: ctl.signal,
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Token ${token}` } : {}) },
        body: JSON.stringify({ mensaje: texto, historial: historial.slice(-6) }),
      });
      if (!res.ok || !res.body) throw new Error('http ' + res.status);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const bloque = buf.slice(0, i); buf = buf.slice(i + 2);
          const m = /^event: (\w+)\ndata: ([\s\S]*)$/.exec(bloque);
          if (!m) continue;
          let d; try { d = JSON.parse(m[2]); } catch (_) { continue; }
          if (m[1] === 'estado') setEstado(d.estado);
          else if (m[1] === 'frase') {
            if (!el) { setTyping(false); el = agregarMsg('bot', ''); }
            hayTexto = true;
            acum += (acum ? ' ' : '') + d.texto;
            escribirGradual(el, acum);
            hablar(d.texto);               // la primera oración suena mientras llega el resto
          } else if (m[1] === 'accion') accion = d;
          else if (m[1] === 'fin') fin = d;
        }
      }
      setTyping(false);
      if (!hayTexto) throw new Error('sin texto');
      historial.push({ role: 'user', content: texto }, { role: 'assistant', content: acum });
      if (fin) mostrarProveedor(fin.proveedor, fin.ms_primer_texto);
      if (!ttsActivo || (!vozReproduciendo && !vozCola.length)) setEstado(null);
      if (accion) await ejecutarAccion(accion, texto, true);
    } catch (e) {
      setTyping(false);
      if (e && e.name === 'AbortError') return;
      if (!hayTexto) { setEstado(null); await caEnviarClasico(texto); }   // respaldo: flujo anterior
    } finally {
      if (abortStream === ctl) abortStream = null;
    }
  }

  // ═══ VOZ: MediaRecorder + corte por silencio + Whisper ═══════════
  const puedeGrabar = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  let sttCaidoHasta = 0;            // si Whisper falla, durante 60 s se usa solo el navegador
  let capturaActiva = null;
  let procesandoVoz = false;
  let pttActivo = false;
  let textoNavegadorCmd = '';

  function mimeSoportado() {
    for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']) {
      try { if (MediaRecorder.isTypeSupported(m)) return m; } catch (_) {}
    }
    return '';
  }

  // Devuelve un controlador {listo: Promise<{blob,hablo}|null>, parar(), cancelar()}
  function capturar({ manual = false, silencioMs = 900, sinVozMs = 5000, maxMs = 15000 } = {}) {
    let parar = () => {}, cancelar = () => {};
    let pedirParar = false, pedirCancelar = false;
    const ctrl = { parar: () => { pedirParar = true; parar(); }, cancelar: () => { pedirCancelar = true; cancelar(); } };
    ctrl.listo = (async () => {
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      } catch (e) { return null; }
      const mime = mimeSoportado();
      let rec;
      try { rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); }
      catch (e) { stream.getTracks().forEach(t => t.stop()); return null; }
      const trozos = [];
      rec.ondataavailable = ev => { if (ev.data && ev.data.size) trozos.push(ev.data); };

      let ctx = null, an = null;
      try {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        an = ctx.createAnalyser(); an.fftSize = 1024;
        ctx.createMediaStreamSource(stream).connect(an);
      } catch (_) { an = null; }
      const datos = an ? new Float32Array(an.fftSize) : null;
      const t0 = Date.now();
      let hablo = manual, ultimaVoz = t0, piso = 0.008, cancelado = false;

      return await new Promise(resolve => {
        let timer = null;
        const cerrar = (cancel) => {
          clearInterval(timer);
          cancelado = cancel;
          rec.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            try { ctx && ctx.close(); } catch (_) {}
            resolve(cancelado ? null : { blob: new Blob(trozos, { type: rec.mimeType || mime || 'audio/webm' }), hablo });
          };
          try { rec.state !== 'inactive' ? rec.stop() : rec.onstop(); } catch (_) { rec.onstop(); }
        };
        parar = () => cerrar(false);
        cancelar = () => cerrar(true);
        timer = setInterval(() => {
          const ahora = Date.now();
          if (an) {
            an.getFloatTimeDomainData(datos);
            let s = 0; for (let i = 0; i < datos.length; i++) s += datos[i] * datos[i];
            const rms = Math.sqrt(s / datos.length);
            if (ahora - t0 < 300) piso = Math.min(0.03, Math.max(piso, rms));   // calibra el ruido de fondo
            else if (rms > Math.max(0.02, piso * 2.5)) { hablo = true; ultimaVoz = ahora; }
          }
          if (ahora - t0 > (manual ? 20000 : maxMs)) return cerrar(false);
          if (manual) return;
          if (an && hablo && ahora - ultimaVoz > silencioMs) cerrar(false);       // cortó por silencio
          else if (an && !hablo && ahora - t0 > sinVozMs) cerrar(false);          // nadie habló
        }, 50);
        rec.start();
        if (pedirCancelar) cerrar(true); else if (pedirParar) cerrar(false);
      });
    })();
    return ctrl;
  }

  async function transcribirWhisper(blob) {
    if (!blob || blob.size < 1500 || Date.now() < sttCaidoHasta) return null;
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), 7000);
    try {
      const ext = (blob.type || '').includes('mp4') ? 'mp4' : 'webm';
      const fd = new FormData();
      fd.append('audio', blob, 'voz.' + ext);
      const r = await fetch(API_STT, { method: 'POST', body: fd, signal: ctl.signal });
      if (!r.ok) throw new Error('stt ' + r.status);
      const j = await r.json();
      return (j.texto || '').trim() || null;
    } catch (_) {
      sttCaidoHasta = Date.now() + 60000;   // Whisper/internet caído → reconocimiento del navegador
      return null;
    } finally { clearTimeout(to); }
  }

  function sinActivacion(t) {
    const s = String(t || '');
    const m = /centinela[\s,.:;!¡¿?-]*/i.exec(s);
    return (m ? s.slice(m.index + m[0].length) : s).trim();
  }
  function nPalabras(t) { return (t.match(/\S+/g) || []).length; }

  // Whisper manda, salvo que haya recortado el inicio (la grabación arranca al oír "Centinela")
  function elegirTexto(whisper, navegador) {
    const w = sinActivacion(whisper), n = sinActivacion(navegador);
    if (w.length < 2) return n;
    if (!n) return w;
    return nPalabras(n) - nPalabras(w) >= 2 ? n : w;
  }

  async function procesarVoz(res, textoNav) {
    procesandoVoz = true;
    setEstado('transcribiendo');
    try {
      const w = res && res.hablo ? await transcribirWhisper(res.blob) : null;
      const t = elegirTexto(w, textoNav);
      tbarText.textContent = t ? `"${t}"` : 'Esperando "Centinela..."';
      if (!t) { setEstado(null); agregarMsg('bot', 'No alcancé a escucharte. Inténtalo de nuevo.'); return; }
      if (!panel.classList.contains('ca-open')) { panel.classList.add('ca-open'); sessionStorage.setItem('ca-seen', '1'); }
      await caEnviar(t);
    } finally { procesandoVoz = false; textoNavegadorCmd = ''; }
  }

  // Tras oír "Centinela": interrumpe la voz y graba el comando hasta que haya silencio
  async function iniciarComandoPorVoz() {
    if (capturaActiva || procesandoVoz || pttActivo) return;
    callarVoz();
    setEstado('escuchando');
    if (!panel.classList.contains('ca-open')) { panel.classList.add('ca-open'); sessionStorage.setItem('ca-seen', '1'); }
    if (!puedeGrabar || Date.now() < sttCaidoHasta) return;   // lo atenderá el reconocimiento del navegador
    const cap = capturar();
    capturaActiva = cap;
    const res = await cap.listo;
    if (capturaActiva === cap) capturaActiva = null; else return;   // cancelada
    if (!res) { setEstado(null); return; }
    await procesarVoz(res, textoNavegadorCmd);
  }

  function cancelarCaptura() {
    if (capturaActiva) { const c = capturaActiva; capturaActiva = null; c.cancelar(); }
  }

  // Flujo anterior (Claude, una sola respuesta JSON). Se conserva como respaldo del streaming.
  async function caEnviarClasico(texto) {
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

      await ejecutarAccion(data, texto, false);
    } catch (e) {
      setTyping(false);
      agregarMsg('bot', 'No pude conectar con el asistente. Verifica que el backend de Django (:9000) esté corriendo. Mientras tanto puedo abrir secciones ("abre eventos") y activar el SOS ("auxilio").');
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
      const A = window.CentinelaAtajos;
      const esFinal = e.results[e.results.length - 1].isFinal;

      // SOS inequívoco ("auxilio", "me están robando"): no espera a que termine la frase ni a "Centinela"
      if (A && !procesandoVoz && A.esSOSSinActivacion(textoPrincipal)) {
        cancelarCaptura();
        caEnviar(textoPrincipal);
        return;
      }

      const norm = normText(textoPrincipal);
      const idx  = norm.indexOf('centinela');
      if (idx < 0) return;
      // Eco: si lo que dice el propio asistente contiene "Centinela", no se toma como palabra de activación
      if (vozReproduciendo && normText(ultimoHablado).includes('centinela')) return;

      const comando = textoPrincipal.substring(idx + 9).trim();
      textoNavegadorCmd = comando;
      // Al oír "Centinela" (aun sin terminar la frase): se calla la voz y se empieza a grabar para Whisper
      if (!capturaActiva && !procesandoVoz && !pttActivo) iniciarComandoPorVoz();

      if (!esFinal) return;
      if (comando.length < 3) {
        tbarText.textContent = 'Esperando "Centinela..."';
        return;
      }
      if (procesandoVoz || pttActivo) return;

      // Atajo (SOS / navegación) o Whisper no disponible → se usa el texto del navegador al instante.
      // Si no, el grabador entrega el comando a Whisper cuando detecta silencio.
      const atajo = A && A.resolver(comando);
      if (atajo || !capturaActiva) {
        cancelarCaptura();
        tbarText.textContent = `Procesando: "${comando}"`;
        if (!panel.classList.contains('ca-open')) {
          panel.classList.add('ca-open');
          sessionStorage.setItem('ca-seen', '1');
        }
        caEnviar(comando);
      }
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
    callarVoz();            // tocar el micrófono interrumpe al asistente
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

    callarVoz();            // tocar el micrófono interrumpe al asistente
    cancelarCaptura();
    manualRec.start();
  });

  // ── PUSH-TO-TALK: mantén presionado, suelta para enviar (Whisper → respaldo navegador) ──
  const pttBtn = document.getElementById('ca-ptt');
  if (pttBtn) {
    let ptt = null;   // { cap, sr, textoSR }

    async function pttInicio(ev) {
      ev.preventDefault();
      if (pttActivo) return;
      pttActivo = true;
      callarVoz();            // interrumpe la voz y escucha
      cancelarCaptura();
      pttBtn.classList.add('ca-recording');
      setEstado('escuchando');
      try { pttBtn.setPointerCapture(ev.pointerId); } catch (_) {}
      ptt = { cap: null, sr: null, textoSR: '' };
      // Reconocimiento del navegador en paralelo: es el respaldo si Whisper falla
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SR) {
        try {
          const sr = new SR();
          sr.lang = 'es-MX'; sr.continuous = true; sr.interimResults = true;
          sr.onresult = (e) => {
            let t = '';
            for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript + ' ';
            ptt && (ptt.textoSR = t.trim());
            input.value = t.trim();
          };
          sr.onerror = () => {};
          sr.start();
          ptt.sr = sr;
        } catch (_) {}
      }
      if (puedeGrabar) ptt.cap = capturar({ manual: true });
      if (!panel.classList.contains('ca-open')) { panel.classList.add('ca-open'); sessionStorage.setItem('ca-seen', '1'); }
    }

    async function pttFin() {
      if (!pttActivo || !ptt) return;
      const cur = ptt; ptt = null;
      pttBtn.classList.remove('ca-recording');
      try { cur.sr && cur.sr.stop(); } catch (_) {}
      let res = null;
      if (cur.cap) { cur.cap.parar(); res = await cur.cap.listo; }
      setEstado('transcribiendo');
      procesandoVoz = true;
      try {
        const w = res ? await transcribirWhisper(res.blob) : null;
        await new Promise(r => setTimeout(r, w ? 0 : 450));          // deja cerrar al reconocimiento del navegador
        const t = (w || cur.textoSR || input.value || '').trim();
        input.value = '';
        if (!t) { setEstado(null); agregarMsg('bot', 'No alcancé a escucharte. Mantén presionado y habla.'); return; }
        pttActivo = false;
        await caEnviar(t);
      } finally { procesandoVoz = false; pttActivo = false; }
    }

    pttBtn.addEventListener('pointerdown', pttInicio);
    pttBtn.addEventListener('pointerup', pttFin);
    pttBtn.addEventListener('pointercancel', pttFin);
    pttBtn.addEventListener('contextmenu', e => e.preventDefault());
  }

})();
