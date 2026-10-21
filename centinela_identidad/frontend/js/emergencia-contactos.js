// emergencia-contactos.js — CRUD de contactos de emergencia
(function () {
  const DJANGO = 'http://localhost:9000';
  const token  = localStorage.getItem('token');

  if (!token) {
    alert('Debes iniciar sesión para gestionar tus contactos.');
    window.location.href = 'login.html';
    return;
  }

  // ── API helpers ───────────────────────────────────────────────────────────
  async function apiCall(method, path, body) {
    const opts = {
      method,
      headers: { 'Authorization': `Token ${token}` },
    };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(`${DJANGO}${path}`, opts);
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(data.error || `Error HTTP ${r.status}`);
    }
    return r.json();
  }

  // ── State ─────────────────────────────────────────────────────────────────
  let contactos  = [];
  let editandoId = null;

  // ── DOM refs ──────────────────────────────────────────────────────────────
  const listaEl   = document.getElementById('lista-contactos');
  const emptyEl   = document.getElementById('empty-state');
  const formEl    = document.getElementById('form-contacto');
  const formTitle = document.getElementById('form-title');
  const inpNombre = document.getElementById('inp-nombre');
  const inpTel    = document.getElementById('inp-tel');
  const selRel    = document.getElementById('sel-relacion');
  const errorEl   = document.getElementById('form-error');
  const btnGuardar = document.getElementById('btn-guardar');

  // ── Helpers ───────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderLista() {
    if (contactos.length === 0) {
      listaEl.innerHTML = '';
      emptyEl.style.display = 'flex';
      return;
    }
    emptyEl.style.display = 'none';
    listaEl.innerHTML = contactos.map(c => `
      <div class="contact-card" data-id="${c.id}">
        <div class="contact-info">
          <div class="contact-nombre">${esc(c.nombre_contacto)}</div>
          <div class="contact-meta">
            <span class="rel-badge rel-${esc(c.relacion)}">${esc(c.relacion_display)}</span>
            ${c.numero_telefono
              ? `<a href="tel:${esc(c.numero_telefono)}" class="contact-tel">${esc(c.numero_telefono)}</a>`
              : '<span class="contact-tel no-tel">Sin teléfono</span>'}
          </div>
        </div>
        <div class="contact-actions">
          <button class="btn-action btn-edit" onclick="window.EC.editar(${c.id})">Editar</button>
          <button class="btn-action btn-delete" onclick="window.EC.eliminar(${c.id})">Eliminar</button>
        </div>
      </div>
    `).join('');
  }

  function abrirForm(titulo, nombre, tel, rel, id) {
    formTitle.textContent    = titulo;
    inpNombre.value          = nombre || '';
    inpTel.value             = tel    || '';
    selRel.value             = rel    || 'otro';
    errorEl.textContent      = '';
    editandoId               = id || null;
    btnGuardar.textContent   = id ? 'Guardar cambios' : 'Agregar contacto';
    formEl.style.display     = 'block';
    inpNombre.focus();
  }

  function cerrarForm() {
    formEl.style.display = 'none';
    editandoId = null;
  }

  // ── Global handlers (usados desde onclick del HTML) ───────────────────────
  window.EC = {
    editar(id) {
      const c = contactos.find(x => x.id === id);
      if (c) abrirForm('Editar contacto', c.nombre_contacto, c.numero_telefono, c.relacion, id);
    },
    async eliminar(id) {
      const c = contactos.find(x => x.id === id);
      if (!c || !confirm(`¿Eliminar a "${c.nombre_contacto}"?`)) return;
      try {
        await apiCall('DELETE', `/api/contactos-emergencia/${id}/`);
        contactos = contactos.filter(x => x.id !== id);
        renderLista();
      } catch (e) {
        alert('Error al eliminar: ' + e.message);
      }
    },
  };

  // ── Event listeners ───────────────────────────────────────────────────────
  document.getElementById('btn-nuevo').addEventListener('click', () => {
    abrirForm('Nuevo contacto de emergencia');
  });

  document.getElementById('btn-cancelar').addEventListener('click', cerrarForm);

  btnGuardar.addEventListener('click', async () => {
    errorEl.textContent = '';
    const body = {
      nombre_contacto: inpNombre.value.trim(),
      numero_telefono: inpTel.value.trim(),
      relacion:        selRel.value,
    };

    if (!body.nombre_contacto) {
      errorEl.textContent = 'El nombre es requerido.';
      inpNombre.focus();
      return;
    }

    try {
      if (editandoId) {
        const actualizado = await apiCall('PUT', `/api/contactos-emergencia/${editandoId}/`, body);
        contactos = contactos.map(c => c.id === editandoId ? actualizado : c);
      } else {
        const nuevo = await apiCall('POST', '/api/contactos-emergencia/', body);
        contactos.push(nuevo);
      }
      renderLista();
      cerrarForm();
    } catch (e) {
      errorEl.textContent = 'Error: ' + e.message;
    }
  });

  // ── Load ──────────────────────────────────────────────────────────────────
  apiCall('GET', '/api/contactos-emergencia/')
    .then(data => { contactos = data; renderLista(); })
    .catch(() => {
      listaEl.innerHTML = '<p class="load-error">Error al cargar contactos. Verifica que el servidor Django (:9000) esté activo.</p>';
    });
})();
