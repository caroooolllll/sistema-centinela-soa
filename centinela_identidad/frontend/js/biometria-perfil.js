/* "Mi perfil": estado del rostro registrado, registro (con consentimiento) y borrado definitivo. */
(function () {
  'use strict';
  const s = document.createElement('script');
  s.src = 'js/biometria-core.js';
  s.onload = iniciar;
  document.head.appendChild(s);

  function iniciar() {
    const B = window.CentinelaBio;
    const host = document.querySelector('main') || document.body;
    const card = document.createElement('section');
    card.id = 'bio-card';
    card.style.cssText = 'margin:16px;padding:18px;border:1px solid #1E3330;border-radius:16px;background:#0D1C19;color:#d0ece8;font-family:inherit;max-width:760px';
    card.innerHTML = `
      <h3 style="margin:0 0 6px;color:#0DF2CC;font-size:17px">🔐 Reconocimiento facial (opcional)</h3>
      <p id="bio-estado" style="margin:0 0 10px;font-size:14px">Consultando…</p>
      <label style="display:flex;gap:8px;font-size:12.5px;line-height:1.45;margin-bottom:10px;color:#9fc5be">
        <input type="checkbox" id="bio-consent" style="margin-top:3px">
        <span>Acepto el aviso de privacidad: se calculará un vector numérico de mi rostro, se guardará <b>cifrado</b> y
        solo servirá para verificar mi identidad. <b>Nunca se guarda ni se envía mi foto.</b> Puedo borrarlo cuando quiera.</span>
      </label>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button id="bio-reg" style="padding:9px 16px;border-radius:10px;border:none;background:#0DF2CC;color:#0D1C19;font-weight:700;cursor:pointer">Registrar mi rostro</button>
        <button id="bio-del" style="padding:9px 16px;border-radius:10px;border:1px solid #ff6b6b;background:none;color:#ff6b6b;font-weight:700;cursor:pointer;display:none">Borrar mi biometría</button>
      </div><p id="bio-msg" style="font-size:13px;margin:10px 0 0;min-height:18px"></p>`;
    host.insertBefore(card, host.firstChild);
    const q = (id) => card.querySelector(id);
    const msg = (t, c) => { q('#bio-msg').textContent = t; q('#bio-msg').style.color = c || '#9fc5be'; };

    async function refrescar() {
      const e = await B.api('/estado/');
      if (e.estado === 'ERROR') { q('#bio-estado').textContent = 'No se pudo consultar (inicia sesión de nuevo).'; return; }
      q('#bio-estado').textContent = e.registrada
        ? `✅ Rostro registrado el ${new Date(e.creado).toLocaleString('es-MX')}${e.es_demo ? ' (demo)' : ''}. Se te pedirá al iniciar sesión.`
        : 'No tienes rostro registrado. Es opcional: añade una capa extra de seguridad a tu cuenta.';
      q('#bio-reg').textContent = e.registrada ? 'Volver a registrar' : 'Registrar mi rostro';
      q('#bio-del').style.display = e.registrada ? '' : 'none';
    }

    q('#bio-reg').onclick = async () => {
      if (!q('#bio-consent').checked) { msg('Marca la casilla de consentimiento para continuar.', '#FFD84D'); return; }
      msg('');
      const r = await B.registrar({
        guardar: async (vector) => {
          const x = await B.api('/registrar/', { metodo: 'POST', cuerpo: { vector, consentimiento: true, liveness_ok: true } });
          return { ok: x.estado === 'OK', mensaje: x.mensaje };
        },
      });
      msg(r.guardado ? 'Rostro registrado.' : 'No se guardó nada.', r.guardado ? '#7CFFB2' : '#9fc5be');
      refrescar();
    };
    q('#bio-del').onclick = async () => {
      if (!confirm('¿Borrar de forma definitiva tu plantilla facial?')) return;
      const x = await B.api('/borrar/', { metodo: 'POST', cuerpo: {} });
      msg(x.borrada ? 'Tu biometría fue borrada de forma definitiva.' : 'No había nada que borrar.', '#7CFFB2');
      refrescar();
    };
    refrescar();
  }
})();
