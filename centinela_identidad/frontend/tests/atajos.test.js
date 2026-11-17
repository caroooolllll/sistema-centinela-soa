// Corre con:  node --test centinela_identidad/frontend/tests
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const fs = require('node:fs');
const A = require('../js/asistente-atajos.js');
const casos = JSON.parse(fs.readFileSync(
  path.join(__dirname, '../../backend_django/centinela/asistente/casos_atajos.json'), 'utf8'));

test('SOS: detecta emergencias (sin red, sin LLM)', () => {
  const fetchOriginal = globalThis.fetch;
  globalThis.fetch = () => { throw new Error('el atajo SOS no debe usar red'); };
  try {
    for (const f of casos.sos) {
      assert.ok(A.esSOS(f), f);
      const r = A.resolver(f);
      assert.strictEqual(r.tipo, 'emergencia', f);
      assert.strictEqual(r.destino, 'panico.html', f);
      assert.strictEqual(r.activar_sos, true, f);
    }
  } finally { globalThis.fetch = fetchOriginal; }
});

test('SOS: sin falsos positivos', () => {
  for (const f of casos.no_sos) assert.ok(!A.esSOS(f), f);
});

test('Navegación por reglas', () => {
  for (const [f, destino] of Object.entries(casos.nav)) {
    const n = A.detectarNavegacion(f);
    assert.ok(n, f);
    assert.strictEqual(n[0], destino, f);
    assert.strictEqual(A.resolver(f).tipo, 'navegacion', f);
  }
});

test('Lo que no es navegación va al LLM', () => {
  for (const f of casos.no_nav) assert.strictEqual(A.resolver(f), null, f);
});

test('SOS por voz sin palabra de activación solo con frases inequívocas', () => {
  assert.ok(A.esSOSSinActivacion('auxilio'));
  assert.ok(A.esSOSSinActivacion('me están robando'));
  assert.ok(!A.esSOSSinActivacion('hay una emergencia en la tele'));
  assert.ok(!A.esSOSSinActivacion('ayuda'));
});
