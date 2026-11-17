/* ═══════════════════════════════════════════════════════════════
   ATAJOS LOCALES DEL ASISTENTE (sin LLM, sin red)
   Espejo de backend_django/centinela/asistente/atajos.py — si cambias uno, cambia el otro.
   Ambos se prueban con los mismos casos: centinela/asistente/casos_atajos.json
   ═══════════════════════════════════════════════════════════════ */
(function (root) {
  'use strict';

  const NAV_PAGINAS = {
    'dashboard.html': ['dashboard', 'inicio', 'panel', 'home', 'principal', 'tablero'],
    'chat.html': ['chat', 'mensajes', 'conversaciones', 'chat vecinal'],
    'eventos.html': ['eventos', 'evento', 'agenda', 'actividades', 'calendario'],
    'noticias.html': ['noticias', 'noticia', 'novedades'],
    'avisos.html': ['avisos', 'aviso', 'reportes', 'reporte', 'incidencias', 'incidencia', 'tablon', 'comunicados'],
    'encuestas.html': ['encuestas', 'encuesta', 'votaciones', 'votacion', 'decisiones'],
    'historial.html': ['historial', 'reportes anteriores', 'reportes pasados'],
    'panico.html': ['panico', 'boton de panico'],
    'accesibilidad-modo.html': ['accesibilidad', 'modo accesible', 'modo accesibilidad'],
    'perfil.html': ['perfil', 'mi perfil', 'mi cuenta', 'cuenta'],
    'configuracion.html': ['configuracion', 'ajustes', 'opciones'],
    'notificaciones.html': ['notificaciones', 'notificacion', 'alertas'],
    'publicaciones.html': ['publicaciones', 'publicacion', 'posts', 'foros', 'foro'],
    'emergencia-contactos.html': ['contactos de emergencia', 'contactos', 'directorio', 'directorio de emergencia'],
  };
  const NOMBRES = {
    'dashboard.html': 'el inicio', 'chat.html': 'el chat', 'eventos.html': 'los eventos',
    'noticias.html': 'las noticias', 'avisos.html': 'los reportes y avisos',
    'encuestas.html': 'las encuestas', 'historial.html': 'el historial',
    'panico.html': 'el botón de pánico', 'accesibilidad-modo.html': 'accesibilidad',
    'perfil.html': 'tu perfil', 'configuracion.html': 'la configuración',
    'notificaciones.html': 'las notificaciones', 'publicaciones.html': 'las publicaciones',
    'emergencia-contactos.html': 'los contactos de emergencia',
  };
  const VERBOS_NAV = [
    'abre', 'abrir', 'abreme', 've a', 've al', 'vete a', 'ir a', 'ir al', 'llevame a', 'llevame al',
    'llevame', 'muestrame', 'mostrar', 'quiero ver', 'quiero ir a', 'quiero ir al', 'navega a',
    'navegar a', 'dame', 'entra a', 'entrar a', 'pasa a', 'regresa a', 'vuelve a', 'vamos a', 'enseñame',
  ];
  const RELLENO = new Set(['el', 'la', 'los', 'las', 'un', 'una', 'mi', 'mis', 'de', 'del', 'a', 'al', 'pagina',
    'pantalla', 'seccion', 'modulo', 'ventana', 'por', 'favor', 'porfa', 'ya', 'ahora', 'quiero', 'me', 'puedes',
    'podrias', 'oye', 'en', 'lo', 'que', 'es', 'sea', 'vecinal', 'vecinos']);

  const SOS_PATRONES = [
    /\bauxilio\b/, /\bsocorro\b/, /\bsos\b/,
    /\bme estan (robando|asaltando|atacando|siguiendo|golpeando)\b/,
    /\bme (quieren|intentan) (robar|asaltar|atacar|secuestrar)\b/,
    /\bme (robaron|asaltaron|asaltan|roban)\b/,
    /\bnecesito ayuda\b/,
    /\b(pide|pidan|llama|llamen|llamar)( a)?( la| el)? (ayuda|policia|ambulancia|emergencias|seguridad)\b/,
    /\bhay (un |una )?(ladron|ladrones|intruso|incendio|fuego|herido|heridos|balacera|disparos)\b/,
    /\bentraron (a|en) mi (casa|domicilio)\b/, /\b(disparos|balacera)\b/,
    /\bactiva(r)? (el |la )?(sos|emergencia|panico|alerta)\b/,
    /\b(estoy|esta) en peligro\b/, /\bayuda (urgente|por favor|porfavor)\b/,
    /\bes una emergencia\b/, /\bemergencia\b/,
  ];
  const SOS_EXCLUIR = [/contactos? de emergencia/, /directorio de emergencia/, /\b(como|que) (es|funciona|activo|hago)\b/,
    /\bsimulacro\b/, /\bpara que sirve\b/, /\bconfigur/];
  // Palabras tan inequívocas que disparan SOS por voz aun sin decir "Centinela"
  const SOS_SIN_ACTIVACION = [/\bauxilio\b/, /\bsocorro\b/, /\bme estan (robando|asaltando|atacando)\b/];

  function normalizar(t) {
    return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();
  }
  function quitarActivacion(t) {
    const n = normalizar(t);
    const i = n.indexOf('centinela');
    return i >= 0 ? n.slice(i + 9).trim() : n;
  }
  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function esSOS(texto) {
    const n = quitarActivacion(texto);
    if (!n) return false;
    if (SOS_EXCLUIR.some(r => r.test(n))) return false;
    if (SOS_PATRONES.some(r => r.test(n))) return true;
    const p = n.split(' ');
    return p.length <= 3 && p.includes('ayuda');
  }
  function esSOSSinActivacion(texto) {
    const n = normalizar(texto);
    return !SOS_EXCLUIR.some(r => r.test(n)) && SOS_SIN_ACTIVACION.some(r => r.test(n));
  }

  function detectarNavegacion(texto) {
    const n = quitarActivacion(texto);
    if (!n) return null;
    let resto = null;
    const verbos = VERBOS_NAV.map(normalizar).sort((a, b) => b.length - a.length);
    for (const v of verbos) {
      if (n === v || n.startsWith(v + ' ')) { resto = n.slice(v.length).trim(); break; }
    }
    if (resto === null) return null;
    let mejor = null;
    for (const [destino, sins] of Object.entries(NAV_PAGINAS)) {
      for (const s of sins) {
        if (new RegExp('(^|\\s)' + esc(s) + '(\\s|$)').test(resto)) {
          if (!mejor || s.length > mejor[1].length) mejor = [destino, s];
        }
      }
    }
    if (!mejor) return null;
    const sobrante = resto.replace(new RegExp('(^|\\s)' + esc(mejor[1]) + '(\\s|$)'), ' ').split(' ').filter(Boolean);
    if (sobrante.some(p => !RELLENO.has(p))) return null;
    return [mejor[0], 'Abriendo ' + NOMBRES[mejor[0]] + '.'];
  }

  function resolver(texto) {
    if (esSOS(texto)) {
      return { tipo: 'emergencia', destino: 'panico.html', activar_sos: true,
               respuesta: 'Activando emergencia ahora. Mantén la calma, abro el botón de pánico.' };
    }
    const nav = detectarNavegacion(texto);
    if (nav) return { tipo: 'navegacion', destino: nav[0], respuesta: nav[1] };
    return null;
  }

  const api = { normalizar, quitarActivacion, esSOS, esSOSSinActivacion, detectarNavegacion, resolver };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CentinelaAtajos = api;
})(typeof window !== 'undefined' ? window : globalThis);
