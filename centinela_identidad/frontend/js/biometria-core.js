/* ═══════════════════════════════════════════════════════════════════════════
   BIOMETRÍA FACIAL — Centinela
   · Detección, malla, iris y prueba de vida: MediaPipe Face Landmarker (local, sin internet)
   · Plantilla facial (vector de 128 valores): @vladmandic/face-api (local)
   · NUNCA se guarda ni se envía una foto: solo el vector, y solo si el usuario pulsa "Guardar".
   Uso:  CentinelaBio.registrar({guardar})  /  CentinelaBio.verificar({origen})  /  CentinelaBio.Motor (portón)
   ═══════════════════════════════════════════════════════════════════════════ */
(function (root) {
  'use strict';
  if (root.CentinelaBio) return;

  const SCRIPT = document.currentScript && document.currentScript.src;
  const BASE = SCRIPT ? SCRIPT.replace(/js\/biometria-core\.js.*$/, '') : '';
  const HOST = location.hostname || 'localhost';
  const API = `${location.protocol === 'https:' ? 'https:' : 'http:'}//${HOST}:9000/api/biometria`;

  // Umbrales de la prueba de vida / calidad (ajustables)
  const CFG = {
    ojoCerrado: 0.62,        // parpadeo: EAR < 62 % del EAR con ojos abiertos
    ojoMinAbs: 0.17,         // ...o EAR absoluto menor a esto
    giroCabeza: 0.10,        // desplazamiento de la nariz (fracción del ancho de la cara)
    giroMaxMirada: 0.13,     // en el paso "sigue el punto" la cabeza casi no debe moverse
    miradaDelta: 0.05,       // desplazamiento del iris (fracción del ancho del ojo)
    carasMin: 0.20, carasMax: 0.78,  // ancho de la cara / ancho del video
    luzMin: 55,              // luminancia media 0-255
    tiempoPaso: 9000,        // ms máx. por paso
    cuadrosPlantilla: 8,
  };
  const OJO_D = [33, 160, 158, 133, 153, 144];     // ojo en el lado izquierdo de la imagen
  const OJO_I = [362, 385, 387, 263, 373, 380];    // ojo en el lado derecho de la imagen

  const dist = (a, b, W, H) => Math.hypot((a.x - b.x) * W, (a.y - b.y) * H);
  const mediana = (arr) => { const s = [...arr].sort((a, b) => a - b); return s[Math.floor(s.length / 2)] || 0; };
  const dormir = (ms) => new Promise(r => setTimeout(r, ms));
  const barajar = (a) => { a = [...a]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

  function ear(L, idx, W, H) {
    const p = idx.map(i => L[i]);
    return (dist(p[1], p[5], W, H) + dist(p[2], p[4], W, H)) / (2 * dist(p[0], p[3], W, H));
  }

  // ── carga de librerías locales ─────────────────────────────────────────
  let libsPromesa = null;
  function cargarLibs(onEstado) {
    if (libsPromesa) return libsPromesa;
    libsPromesa = (async () => {
      onEstado && onEstado('Cargando modelos (local)…');
      await new Promise((ok, mal) => {
        if (root.faceapi) return ok();
        const s = document.createElement('script');
        s.src = BASE + 'vendor/face-api/face-api.js';
        s.onload = ok; s.onerror = () => mal(new Error('No se pudo cargar face-api local'));
        document.head.appendChild(s);
      });
      const fa = root.faceapi;
      try { await fa.tf.setBackend('webgl'); } catch (_) { await fa.tf.setBackend('cpu'); }
      await fa.tf.ready();
      const m = BASE + 'vendor/face-api/model';
      await Promise.all([fa.nets.tinyFaceDetector.loadFromUri(m), fa.nets.faceLandmark68Net.loadFromUri(m),
                         fa.nets.faceRecognitionNet.loadFromUri(m)]);
      const mp = await import(BASE + 'vendor/mediapipe/vision_bundle_esm.js');
      const fileset = await mp.FilesetResolver.forVisionTasks(BASE + 'vendor/mediapipe/wasm');
      const crear = (delegate) => mp.FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: BASE + 'vendor/mediapipe/face_landmarker.task', delegate },
        runningMode: 'VIDEO', numFaces: 2, outputFaceBlendshapes: false,
      });
      let lm;
      try { lm = await crear('GPU'); } catch (_) { lm = await crear('CPU'); }
      return { mp, lm };
    })().catch(e => { libsPromesa = null; throw e; });
    return libsPromesa;
  }

  // ═══ MOTOR: cámara + landmarks + dibujo + métricas por cuadro ══════════════
  class Motor {
    constructor(canvas, opts = {}) {
      this.canvas = canvas; this.ctx = canvas.getContext('2d');
      this.video = document.createElement('video');
      this.video.playsInline = true; this.video.muted = true;
      this.opts = opts; this.m = { n: 0 }; this.waiters = []; this.activo = false;
      this.dot = null;                       // {x,y} 0..1 en pantalla (ya espejada)
      this.lumTick = 0; this.lum = 120;
      this.lumCanvas = document.createElement('canvas'); this.lumCanvas.width = 64; this.lumCanvas.height = 48;
    }
    async iniciar(onEstado) {
      if (!window.isSecureContext) throw new Error('La cámara requiere un contexto seguro: abre Centinela desde http://localhost (o HTTPS).');
      this.libs = await cargarLibs(onEstado);
      this.du = new this.libs.mp.DrawingUtils(this.ctx);
      onEstado && onEstado('Activando cámara…');
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
      } catch (e) {
        throw new Error(e.name === 'NotAllowedError' ? 'Permiso de cámara denegado. Actívalo en el candado de la barra de direcciones.'
                                                      : 'No se encontró una cámara disponible.');
      }
      this.video.srcObject = this.stream;
      await this.video.play();
      this.canvas.width = this.video.videoWidth || 640; this.canvas.height = this.video.videoHeight || 480;
      this.activo = true; this.ultT = -1; this.tsMp = 0;
      this._tick = this._tick.bind(this);
      requestAnimationFrame(this._tick);
    }
    detener() {
      this.activo = false;
      try { this.stream && this.stream.getTracks().forEach(t => t.stop()); } catch (_) {}
      try { this.video.srcObject = null; } catch (_) {}
      this.waiters.splice(0).forEach(w => w.fin({ ok: false, cancelado: true }));
    }
    _tick() {
      if (!this.activo) return;
      if (this.video.readyState >= 2 && this.video.currentTime !== this.ultT) {
        this.ultT = this.video.currentTime;
        try { this._procesar(); } catch (e) { console.warn('[Bio] cuadro', e); }
      }
      requestAnimationFrame(this._tick);
    }
    _luz() {
      if (++this.lumTick % 8) return;
      const c = this.lumCanvas.getContext('2d', { willReadFrequently: true });
      c.drawImage(this.video, 0, 0, 64, 48);
      const d = c.getImageData(0, 0, 64, 48).data; let s = 0;
      for (let i = 0; i < d.length; i += 4) s += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      this.lum = s / (d.length / 4);
    }
    _procesar() {
      const W = this.canvas.width, H = this.canvas.height, ctx = this.ctx;
      this.tsMp = Math.max(this.tsMp + 1, performance.now());
      const res = this.libs.lm.detectForVideo(this.video, this.tsMp);
      this._luz();
      const caras = res.faceLandmarks || [];
      // fondo espejado (como un espejo)
      ctx.save(); ctx.translate(W, 0); ctx.scale(-1, 1); ctx.drawImage(this.video, 0, 0, W, H);
      const m = { n: caras.length, luz: this.lum, W, H };
      if (caras.length) {
        const L = caras[0], FL = this.libs.mp.FaceLandmarker;
        this.du.drawConnectors(L, FL.FACE_LANDMARKS_TESSELATION, { color: 'rgba(13,242,204,0.22)', lineWidth: 0.6 });
        this.du.drawConnectors(L, FL.FACE_LANDMARKS_FACE_OVAL, { color: 'rgba(13,242,204,0.8)', lineWidth: 1.4 });
        this.du.drawConnectors(L, FL.FACE_LANDMARKS_RIGHT_EYE, { color: '#7CFFB2', lineWidth: 1.4 });
        this.du.drawConnectors(L, FL.FACE_LANDMARKS_LEFT_EYE, { color: '#7CFFB2', lineWidth: 1.4 });
        this.du.drawConnectors(L, FL.FACE_LANDMARKS_LIPS, { color: 'rgba(255,255,255,0.35)', lineWidth: 1 });
        // medidas
        const xs = [L[234].x, L[454].x], xl = Math.min(...xs), xr = Math.max(...xs);
        m.anchoCara = xr - xl; m.centro = { x: (xl + xr) / 2, y: L[1].y };
        m.yaw = (L[1].x - (xl + xr) / 2) / (xr - xl);            // + = nariz hacia la derecha de la imagen (tu izquierda)
        m.earD = ear(L, OJO_D, W, H); m.earI = ear(L, OJO_I, W, H); m.ear = (m.earD + m.earI) / 2;
        if (L.length >= 478) {
          const irisA = L[468], irisB = L[473];
          const par = (c1, c2) => {                                // asigna cada iris al ojo más cercano
            const mid = { x: (L[c1].x + L[c2].x) / 2, y: (L[c1].y + L[c2].y) / 2 };
            return Math.hypot(irisA.x - mid.x, irisA.y - mid.y) <= Math.hypot(irisB.x - mid.x, irisB.y - mid.y) ? irisA : irisB;
          };
          const iD = par(33, 133), iI = iD === irisA ? irisB : irisA;
          const ratio = (c1, c2, p) => {
            const ax = (L[c2].x - L[c1].x) * W, ay = (L[c2].y - L[c1].y) * H, px = (p.x - L[c1].x) * W, py = (p.y - L[c1].y) * H;
            return (px * ax + py * ay) / (ax * ax + ay * ay);
          };
          m.gx = ((ratio(33, 133, iD) + ratio(362, 263, iI)) / 2) - 0.5;   // + = miras a tu izquierda
          // pupila + hacia dónde mira
          ctx.fillStyle = '#FFD84D';
          [[iD, 33, 133], [iI, 362, 263]].forEach(([p, a, b]) => {
            const cx = (L[a].x + L[b].x) / 2, cy = (L[a].y + L[b].y) / 2;
            ctx.beginPath(); ctx.arc(p.x * W, p.y * H, 3.2, 0, 7); ctx.fill();
            ctx.strokeStyle = '#FFD84D'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(p.x * W, p.y * H);
            ctx.lineTo(p.x * W + (p.x - cx) * W * 5, p.y * H + (p.y - cy) * H * 5); ctx.stroke();
          });
        }
      }
      ctx.restore();
      if (caras.length) { /* ya dibujado */ }
      // punto a seguir (coordenadas de pantalla: 0 = izquierda de lo que ve el usuario)
      if (this.dot) {
        const g = ctx.createRadialGradient(this.dot.x * W, this.dot.y * H, 2, this.dot.x * W, this.dot.y * H, 22);
        g.addColorStop(0, '#FF4D6D'); g.addColorStop(1, 'rgba(255,77,109,0)');
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(this.dot.x * W, this.dot.y * H, 22, 0, 7); ctx.fill();
        ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(this.dot.x * W, this.dot.y * H, 5, 0, 7); ctx.fill();
      }
      this.m = m;
      this.waiters.slice().forEach(w => { try { const v = w.fn(m); if (v) w.fin({ ok: true, valor: v }); } catch (e) { w.fin({ ok: false, error: e }); } });
    }
    // Resuelve cuando fn(métricas) devuelve algo verdadero, o al agotar el tiempo
    esperar(fn, ms) {
      return new Promise(res => {
        const w = { fn, fin: (r) => { clearTimeout(w.t); const i = this.waiters.indexOf(w); if (i >= 0) this.waiters.splice(i, 1); res(r); } };
        w.t = setTimeout(() => w.fin({ ok: false, tiempo: true }), ms);
        this.waiters.push(w);
      });
    }
    // → mensaje en español si el cuadro NO sirve, o null si es bueno
    problema(m = this.m) {
      if (!m || m.n === 0) return 'No veo ningún rostro. Colócate frente a la cámara.';
      if (m.n > 1) return 'Hay más de una cara en la imagen. Debe aparecer una sola persona.';
      if (m.luz < CFG.luzMin) return 'Hay poca luz. Busca un lugar más iluminado.';
      if (m.anchoCara < CFG.carasMin) return 'Estás muy lejos. Acércate a la cámara.';
      if (m.anchoCara > CFG.carasMax) return 'Estás muy cerca. Aléjate un poco.';
      return null;
    }
    // Espera un rostro bueno y estable durante `ms`
    async rostroEstable(ms, ui, timeout = 15000) {
      let desde = null, ultimoMsg = '';
      const r = await this.esperar(m => {
        const p = this.problema(m);
        if (p) { desde = null; if (p !== ultimoMsg) { ultimoMsg = p; ui && ui.mensaje(p, 'aviso'); } return false; }
        if (Math.abs(m.yaw) > 0.12) { desde = null; ui && ui.mensaje('Mira de frente a la cámara.', 'aviso'); return false; }
        if (!desde) desde = performance.now();
        return performance.now() - desde >= ms;
      }, timeout);
      return r.ok;
    }
    // Descriptor facial (128) del cuadro actual; null si no se pudo
    async descriptor() {
      const fa = root.faceapi;
      const r = await fa.detectSingleFace(this.video, new fa.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 }))
        .withFaceLandmarks().withFaceDescriptor();
      return r ? Array.from(r.descriptor) : null;
    }
  }

  // ═══ PRUEBA DE VIDA ═════════════════════════════════════════════════════
  const baseEar = (motor) => motor.esperar(((arr) => (m) => { if (m.n === 1) arr.push(m.ear); return arr.length >= 14 ? mediana(arr) : false; })([]), 4000);

  async function pasoParpadeo(motor, ui, veces) {
    ui.instruccion(veces === 1 ? 'Parpadea una vez' : `Parpadea ${veces} veces`, '👁️');
    const b = await baseEar(motor);
    if (!b.ok) return { ok: false, motivo: motor.problema() || 'No pude medir tus ojos. Mira de frente.' };
    const base = b.valor, umbral = Math.max(CFG.ojoMinAbs, base * CFG.ojoCerrado);
    let cerrado = 0, cuenta = 0, abierto = true;
    const r = await motor.esperar(m => {
      if (m.n !== 1) return false;
      if (m.ear < umbral) { cerrado++; if (cerrado >= 1) abierto = false; }
      else { if (!abierto && cerrado >= 1 && m.ear > base * 0.85) { cuenta++; ui.mensaje(`Parpadeos: ${cuenta}/${veces}`, 'ok'); } if (m.ear > base * 0.85) { cerrado = 0; abierto = true; } }
      return cuenta >= veces;
    }, CFG.tiempoPaso);
    return r.ok ? { ok: true } : { ok: false, motivo: `No detecté ${veces === 1 ? 'el parpadeo' : 'los ' + veces + ' parpadeos'}. Intenta de nuevo.` };
  }

  async function pasoMirada(motor, ui) {
    ui.instruccion('Sigue el punto rojo solo con los ojos', '🎯');
    const lados = barajar(['izquierda', 'derecha']);
    const b = await motor.esperar(((arr) => (m) => { if (m.n === 1 && m.gx !== undefined) arr.push([m.gx, m.yaw]); return arr.length >= 10 ? arr : false; })([]), 4000);
    if (!b.ok) return { ok: false, motivo: motor.problema() || 'No pude seguir tus ojos. Mejora la luz y mira de frente.' };
    const gx0 = mediana(b.valor.map(v => v[0])), yaw0 = mediana(b.valor.map(v => v[1]));
    let pos = 0.5;
    for (const lado of lados) {
      const destino = lado === 'izquierda' ? 0.1 : 0.9;      // pantalla (espejada): izquierda = tu izquierda
      const signo = lado === 'izquierda' ? +1 : -1;           // izquierda del usuario = gx positivo
      // el punto se desliza hasta el lado
      const t0 = performance.now(), p0 = pos;
      await new Promise(res => { const f = () => { const k = Math.min(1, (performance.now() - t0) / 700); pos = p0 + (destino - p0) * k; motor.dot = { x: pos, y: 0.5 }; k < 1 ? requestAnimationFrame(f) : res(); }; f(); });
      ui.mensaje(`Mira el punto (a tu ${lado})`, 'info');
      let seguidos = 0, cabeza = false;
      const r = await motor.esperar(m => {
        if (m.n !== 1 || m.gx === undefined) { seguidos = 0; return false; }
        if (Math.abs(m.yaw - yaw0) > CFG.giroMaxMirada) { if (!cabeza) { cabeza = true; ui.mensaje('Mueve solo los ojos, no la cabeza.', 'aviso'); } seguidos = 0; return false; }
        if ((m.gx - gx0) * signo >= CFG.miradaDelta) seguidos++; else seguidos = 0;
        return seguidos >= 3;
      }, 5500);
      if (!r.ok) { motor.dot = null; return { ok: false, motivo: `No vi que siguieras el punto hacia tu ${lado}.` }; }
    }
    motor.dot = null;
    return { ok: true };
  }

  async function pasoGiro(motor, ui) {
    const lado = Math.random() < 0.5 ? 'izquierda' : 'derecha';
    ui.instruccion(`Gira un poco la cabeza hacia tu ${lado}`, lado === 'izquierda' ? '↩️' : '↪️');
    const b = await motor.esperar(((arr) => (m) => { if (m.n === 1) arr.push(m.yaw); return arr.length >= 8 ? mediana(arr) : false; })([]), 4000);
    if (!b.ok) return { ok: false, motivo: motor.problema() || 'No pude medir tu cabeza. Mira de frente.' };
    const yaw0 = b.valor, signo = lado === 'izquierda' ? +1 : -1;
    const r = await motor.esperar(m => m.n === 1 && (m.yaw - yaw0) * signo >= CFG.giroCabeza, CFG.tiempoPaso);
    return r.ok ? { ok: true } : { ok: false, motivo: `No detecté el giro de tu cabeza hacia tu ${lado}.` };
  }

  const PASOS = {
    parpadeo2: (m, u) => pasoParpadeo(m, u, 2),
    parpadeo1: (m, u) => pasoParpadeo(m, u, 1),
    mirada: pasoMirada,
    giro: pasoGiro,
  };
  const dotBar = (ui, i, n) => ui.progreso && ui.progreso(i, n);

  // modo 'completo' (registro / segundo factor): 3 pruebas en orden aleatorio · 'rapido' (portón): 1 parpadeo
  async function pruebaDeVida(motor, ui, modo = 'completo') {
    const pasos = modo === 'rapido' ? ['parpadeo1'] : barajar(['parpadeo2', 'mirada', 'giro']);
    // huella inicial: la misma persona debe hacer la prueba y dejar la plantilla (anti-cambiazo)
    const d0 = await motor.descriptor();
    for (let i = 0; i < pasos.length; i++) {
      dotBar(ui, i, pasos.length);
      const p = motor.problema();
      if (p) return { ok: false, motivo: p };
      const r = await PASOS[pasos[i]](motor, ui);
      if (!r.ok) return { ok: false, motivo: r.motivo, paso: pasos[i] };
      ui.mensaje('¡Bien!', 'ok'); await dormir(250);
    }
    dotBar(ui, pasos.length, pasos.length);
    return { ok: true, pasos, d0 };
  }

  const cos = (a, b) => { let s = 0, na = 0, nb = 0; for (let i = 0; i < a.length; i++) { s += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; } return s / Math.sqrt(na * nb); };
  const promedio = (vs) => { const o = new Array(vs[0].length).fill(0); vs.forEach(v => v.forEach((x, i) => { o[i] += x / vs.length; })); const n = Math.hypot(...o); return o.map(x => x / n); };

  // Plantilla = promedio de varios cuadros buenos (de frente, ojos abiertos, una sola cara)
  async function capturarPlantilla(motor, ui, n = CFG.cuadrosPlantilla, d0 = null) {
    ui.instruccion('Mira de frente y no te muevas', '📸');
    const ds = []; let intentos = 0;
    while (ds.length < n && intentos < n * 4) {
      intentos++;
      const ok = await motor.rostroEstable(150, ui, 6000);
      if (!ok) { await dormir(150); continue; }
      const base = motor.m.ear;
      if (base < 0.17) { await dormir(100); continue; }        // ojos cerrados
      const d = await motor.descriptor();
      if (d) { ds.push(d); ui.progreso && ui.progreso(ds.length, n, 'captura'); }
      await dormir(120);
    }
    if (ds.length < Math.min(3, n)) return { ok: false, motivo: motor.problema() || 'No pude capturar tu rostro con claridad. Intenta de nuevo.' };
    const m0 = promedio(ds);
    const buenos = ds.filter(d => cos(d, m0) > 0.90);                 // descarta cuadros raros
    if (buenos.length < Math.min(3, ds.length)) return { ok: false, motivo: 'Las capturas no coinciden entre sí. Mantén tu cara quieta e inténtalo de nuevo.' };
    const vector = promedio(buenos);
    if (d0 && cos(d0, vector) < 0.85) return { ok: false, motivo: 'La persona al final no coincide con la del inicio de la prueba.' };
    return { ok: true, vector, cuadros: buenos.length };
  }

  // ═══ UI modal reutilizable ═════════════════════════════════════════════════
  const CSS = `
  .cb-ov{position:fixed;inset:0;background:rgba(3,10,9,.86);z-index:100000;display:flex;align-items:center;justify-content:center;font-family:'Outfit','Segoe UI',sans-serif;padding:12px}
  .cb-box{background:#0D1C19;border:1px solid #1E3330;border-radius:18px;width:min(560px,100%);max-height:100%;overflow:auto;color:#d0ece8;box-shadow:0 12px 60px rgba(0,0,0,.7)}
  .cb-h{padding:14px 18px;border-bottom:1px solid #1E3330;display:flex;justify-content:space-between;align-items:center}
  .cb-h b{color:#0DF2CC;font-size:16px}.cb-x{background:none;border:1px solid #1E3330;color:#6B9E96;border-radius:8px;cursor:pointer;padding:3px 9px}
  .cb-cv{width:100%;aspect-ratio:4/3;background:#000;display:block}
  .cb-info{padding:14px 18px}.cb-ins{font-size:20px;font-weight:700;color:#fff;min-height:28px}
  .cb-msg{margin-top:6px;font-size:14px;min-height:20px;color:#6B9E96}.cb-msg.ok{color:#7CFFB2}.cb-msg.aviso{color:#FFD84D}.cb-msg.error{color:#ff6b6b}
  .cb-bar{display:flex;gap:6px;margin-top:10px}.cb-bar i{flex:1;height:6px;border-radius:3px;background:#1E3330}.cb-bar i.on{background:#0DF2CC}
  .cb-btns{display:flex;gap:10px;padding:0 18px 16px}.cb-btn{flex:1;padding:11px;border-radius:11px;border:1px solid #1E3330;background:#152321;color:#d0ece8;cursor:pointer;font-weight:700;font-family:inherit;font-size:14px}
  .cb-btn.pri{background:#0DF2CC;color:#0D1C19;border:none}.cb-btn:disabled{opacity:.5;cursor:not-allowed}
  .cb-aviso{font-size:12px;color:#6B9E96;padding:0 18px 12px;line-height:1.5}
  `;
  function inyectarCSS() { if (document.getElementById('cb-css')) return; const s = document.createElement('style'); s.id = 'cb-css'; s.textContent = CSS; document.head.appendChild(s); }

  function crearModal(titulo) {
    inyectarCSS();
    const ov = document.createElement('div'); ov.className = 'cb-ov';
    ov.innerHTML = `<div class="cb-box"><div class="cb-h"><b>${titulo}</b><button class="cb-x" aria-label="Cerrar">✕</button></div>
      <canvas class="cb-cv"></canvas><div class="cb-info"><div class="cb-ins">Preparando…</div><div class="cb-msg"></div><div class="cb-bar"></div></div>
      <div class="cb-btns"></div><div class="cb-aviso">🔒 Tu foto nunca se guarda ni se envía: solo se calcula un vector numérico cifrado, y únicamente si tú decides guardarlo.</div></div>`;
    document.body.appendChild(ov);
    const q = (s) => ov.querySelector(s);
    const ui = {
      canvas: q('.cb-cv'), ov,
      instruccion: (t, ic) => { q('.cb-ins').textContent = (ic ? ic + ' ' : '') + t; },
      mensaje: (t, tipo) => { const e = q('.cb-msg'); e.textContent = t; e.className = 'cb-msg ' + (tipo || ''); },
      progreso: (i, n) => { q('.cb-bar').innerHTML = Array.from({ length: n }, (_, k) => `<i class="${k < i ? 'on' : ''}"></i>`).join(''); },
      botones: (lista) => { const b = q('.cb-btns'); b.innerHTML = ''; lista.forEach(([txt, cls, fn]) => { const x = document.createElement('button'); x.className = 'cb-btn ' + (cls || ''); x.textContent = txt; x.onclick = fn; b.appendChild(x); }); },
      cerrar: () => ov.remove(),
    };
    return { ui, cerrarBtn: q('.cb-x') };
  }

  // ── Flujo: REGISTRO (Guardar / No guardar) ───────────────────────────────
  // opts.guardar(vector) → Promise<{ok, mensaje}>. Devuelve {guardado:boolean}
  async function registrar(opts = {}) {
    const { ui, cerrarBtn } = crearModal(opts.titulo || 'Registro facial');
    const motor = new Motor(ui.canvas);
    let cancelado = false;
    const fin = () => { cancelado = true; motor.detener(); ui.cerrar(); loopSig(); };
    cerrarBtn.onclick = fin;
    let vector = null;
    try {
      await motor.iniciar(t => ui.mensaje(t));
      while (!cancelado) {
        ui.botones([]); ui.mensaje('');
        ui.instruccion('Colócate frente a la cámara', '🙂');
        if (!(await motor.rostroEstable(800, ui, 30000))) { if (cancelado) break; ui.mensaje('No encontré un rostro estable.', 'error'); ui.botones([['Reintentar', 'pri', () => { ui.botones([]); loopSig(); }], ['Cancelar', '', fin]]); await new Promise(r => { loopSig = r; }); continue; }
        const vida = await pruebaDeVida(motor, ui, 'completo');
        if (cancelado) break;
        if (!vida.ok) { ui.instruccion('Prueba de vida no superada', '⚠️'); ui.mensaje(vida.motivo, 'error'); ui.botones([['Reintentar', 'pri', () => loopSig()], ['Cancelar', '', fin]]); await new Promise(r => { loopSig = r; }); continue; }
        const cap = await capturarPlantilla(motor, ui, CFG.cuadrosPlantilla, vida.d0);
        if (cancelado) break;
        if (!cap.ok) { ui.instruccion('No se pudo crear la plantilla', '⚠️'); ui.mensaje(cap.motivo, 'error'); ui.botones([['Reintentar', 'pri', () => loopSig()], ['Cancelar', '', fin]]); await new Promise(r => { loopSig = r; }); continue; }
        vector = cap.vector;
        motor.detener();
        ui.instruccion('Rostro capturado ✔', '✅'); ui.mensaje(`Plantilla creada con ${cap.cuadros} capturas. ¿Quieres guardarla?`, 'ok'); ui.progreso(1, 1);
        const decision = await new Promise(res => ui.botones([['Guardar', 'pri', () => res(true)], ['No guardar', '', () => res(false)]]));
        if (!decision) { vector = null; ui.cerrar(); return { guardado: false }; }   // se descarta todo de memoria
        ui.botones([]); ui.mensaje('Guardando…');
        const r = await opts.guardar(vector);
        vector = null;
        if (r && r.ok) { ui.instruccion('Registro guardado', '🔐'); ui.mensaje(r.mensaje || 'Listo.', 'ok'); ui.botones([['Cerrar', 'pri', () => ui.cerrar()]]); return { guardado: true }; }
        ui.instruccion('No se pudo guardar', '⚠️'); ui.mensaje((r && r.mensaje) || 'Error desconocido', 'error'); ui.botones([['Cerrar', 'pri', () => ui.cerrar()]]);
        return { guardado: false, error: r && r.mensaje };
      }
    } catch (e) {
      motor.detener(); ui.instruccion('No se pudo iniciar', '⚠️'); ui.mensaje(e.message, 'error');
      ui.botones([['Cerrar', 'pri', () => ui.cerrar()]]);
      return { guardado: false, error: e.message };
    } finally { vector = null; }
    return { guardado: false };
  }
  let loopSig = () => {};

  // ── Flujo: VERIFICAR (segundo factor / acción crítica) ───────────────────
  // → {ok:boolean, cancelado?:boolean}
  async function verificar(opts = {}) {
    const token = opts.token || localStorage.getItem('token') || '';
    const { ui, cerrarBtn } = crearModal(opts.titulo || 'Verificación facial');
    const motor = new Motor(ui.canvas);
    return new Promise(async (resolve) => {
      let hecho = false;
      const salir = (r) => { if (hecho) return; hecho = true; motor.detener(); ui.cerrar(); resolve(r); };
      cerrarBtn.onclick = () => salir({ ok: false, cancelado: true });
      let intentos = 0;
      try {
        await motor.iniciar(t => ui.mensaje(t));
        while (!hecho && intentos < 3) {
          intentos++;
          ui.botones([]); ui.instruccion(opts.motivo || 'Verifica que eres tú', '🔐');
          if (!(await motor.rostroEstable(700, ui, 30000))) { ui.mensaje('No encontré un rostro estable.', 'error'); continue; }
          const vida = await pruebaDeVida(motor, ui, 'completo');
          if (hecho) return;
          if (!vida.ok) { ui.mensaje(`${vida.motivo} (intento ${intentos}/3)`, 'error'); await dormir(1500); continue; }
          const cap = await capturarPlantilla(motor, ui, 4, vida.d0);
          if (hecho) return;
          if (!cap.ok) { ui.mensaje(cap.motivo, 'error'); await dormir(1500); continue; }
          ui.mensaje('Comparando…');
          const r = await fetch(`${API}/verificar/`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Token ${token}` },
            body: JSON.stringify({ vector: cap.vector, liveness_ok: true, origen: opts.origen || 'accion_critica', accion: opts.accion || '' }) })
            .then(x => x.json()).catch(() => ({ estado: 'ERROR', mensaje: 'Sin conexión con el servidor' }));
          if (r.coincide) { ui.instruccion('Identidad confirmada', '✅'); ui.mensaje('', 'ok'); await dormir(600); return salir({ ok: true, score: r.score }); }
          if (r.estado === 'ERROR') { ui.mensaje(r.mensaje || 'Error de verificación', 'error'); if (/404|registrado/.test(r.mensaje || '')) return salir({ ok: false, sinPlantilla: true }); await dormir(1500); continue; }
          ui.mensaje(`El rostro no coincide (intento ${intentos}/3).`, 'error'); await dormir(1500);
        }
        if (!hecho) { ui.instruccion('Verificación fallida', '⛔'); ui.mensaje('No se pudo confirmar tu identidad.', 'error'); await dormir(1800); salir({ ok: false }); }
      } catch (e) {
        ui.instruccion('No se pudo iniciar', '⚠️'); ui.mensaje(e.message, 'error');
        ui.botones([['Cerrar', 'pri', () => salir({ ok: false, error: e.message })]]);
      }
    });
  }

  // ── Llamadas a la API ──────────────────────────────────────────────────
  async function api(ruta, { metodo = 'GET', cuerpo, token } = {}) {
    const t = token === undefined ? (localStorage.getItem('token') || '') : token;
    const r = await fetch(`${API}${ruta}`, { method: metodo,
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Token ${t}` } : {}) },
      body: cuerpo ? JSON.stringify(cuerpo) : undefined });
    return r.json().catch(() => ({ estado: 'ERROR', mensaje: 'Respuesta inválida' }));
  }

  // Guardia para acciones críticas: si el usuario NO tiene rostro registrado, pasa sin pedir nada (es opcional).
  // El SOS/pánico NUNCA debe pasar por aquí.
  async function confirmarAccion(motivo) {
    const e = await api('/estado/');
    if (!e.registrada) return true;
    const r = await verificar({ origen: 'accion_critica', accion: motivo, motivo: motivo || 'Confirma esta acción con tu rostro', titulo: 'Confirmar con tu rostro' });
    return !!r.ok;
  }

  root.CentinelaBio = { Motor, CFG, cargarLibs, pruebaDeVida, capturarPlantilla, registrar, verificar, confirmarAccion, api, API, BASE, crearModal, barajar, cos };
})(window);
