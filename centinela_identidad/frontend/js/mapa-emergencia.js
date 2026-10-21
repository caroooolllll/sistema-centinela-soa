// mapa-emergencia.js — Mapa en tiempo real para contactos de emergencia
(function () {
  const CHAT_WS    = 'ws://localhost:9003';
  const token      = localStorage.getItem('token');
  const params     = new URLSearchParams(window.location.search);
  const victimId   = params.get('victim_id');
  const victimName = params.get('nombre') ? decodeURIComponent(params.get('nombre')) : 'Usuario';

  const statusEl   = document.getElementById('status-bar');
  const lastUpdEl  = document.getElementById('last-update');
  const coordsEl   = document.getElementById('coords');
  const titleEl    = document.getElementById('victim-title');

  if (!token || !victimId) {
    if (statusEl) statusEl.textContent = token ? 'URL inválida: falta victim_id' : 'Inicia sesión para ver este mapa.';
    return;
  }

  if (titleEl) titleEl.textContent = `Emergencia activa — ${victimName}`;

  // ── Leaflet map ───────────────────────────────────────────────────────────
  const map = L.map('mapa', { zoomControl: true }).setView([19.4326, -99.1332], 15);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map);

  const victimIcon = L.divIcon({
    html: `<div style="
      background:#ef4444;
      border:3px solid #fff;
      border-radius:50%;
      width:22px;
      height:22px;
      box-shadow:0 0 14px rgba(239,68,68,0.7);
    "></div>`,
    iconSize:   [22, 22],
    iconAnchor: [11, 11],
    className:  '',
  });

  let marker      = null;
  let trailCoords = [];
  let trailLine   = null;

  function actualizarMapa(lat, lng) {
    const pos = [lat, lng];
    map.setView(pos, 17);

    if (marker) {
      marker.setLatLng(pos);
    } else {
      marker = L.marker(pos, { icon: victimIcon })
        .bindPopup(`<b>${victimName}</b><br>En emergencia`)
        .addTo(map);
    }

    trailCoords.push(pos);
    if (trailCoords.length > 120) trailCoords.shift();

    if (trailLine) {
      trailLine.setLatLngs(trailCoords);
    } else {
      trailLine = L.polyline(trailCoords, {
        color: '#ef4444', weight: 2, opacity: 0.5,
      }).addTo(map);
    }
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────
  function setStatus(text, cls) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className   = `status-bar ${cls}`;
  }

  function connect() {
    setStatus('Conectando...', 'connecting');

    const ws = new WebSocket(
      `${CHAT_WS}/ws/emergencia/${victimId}?token=${encodeURIComponent(token)}`
    );

    ws.onopen = () => setStatus('Conectado — esperando ubicación', 'connected');

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'location_update') {
          actualizarMapa(data.lat, data.lng);
          const ts = new Date(data.timestamp || Date.now()).toLocaleTimeString('es-MX');
          if (lastUpdEl) lastUpdEl.textContent = `Última actualización: ${ts}`;
          if (coordsEl)  coordsEl.textContent  = `${Number(data.lat).toFixed(6)}, ${Number(data.lng).toFixed(6)}`;
          setStatus('En vivo', 'connected live');
        }
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };

    ws.onerror = () => setStatus('Error de conexión', 'error');

    ws.onclose = () => {
      setStatus('Desconectado — reconectando en 5s...', 'disconnected');
      setTimeout(connect, 5000);
    };
  }

  connect();
})();
