# Reconocimiento facial en Centinela

## Qué hace
- **Mi perfil → 🔐 Reconocimiento facial (opcional):** registrar / borrar el rostro (con casilla de consentimiento).
- **Login:** si el vecino registró su rostro, tras la contraseña se pide verificación facial (sesión bloqueada en TODOS los servicios hasta verificar).
- **Acciones críticas:** eliminar un reporte y eliminar un evento piden el rostro (solo si lo registraste). El SOS/pánico **nunca** pasa por la cara.
- **Portón inteligente** (`porton.html`): parpadeo → identifica 1:N → abre / "Visitante no registrado" + visita pendiente + bitácora.
- **Asistente:** "Centinela, ¿quién entró hoy?" / "¿hubo visitantes no registrados?" (solo lectura; el vecino ve lo suyo, el admin todo).

## Privacidad y seguridad
- Nunca se guarda ni se envía una foto: solo un vector de 128 números, promedio de varios cuadros.
- El vector se cifra con Fernet (`BIOMETRIA_KEY`, distinta de `SECRET_KEY`). **Respalda esa llave**: sin ella no se descifran las plantillas.
- Bitácora (`biometria_bitacora`): fecha, usuario, resultado, origen y similitud de cada registro/verificación/acceso/borrado.
- Límite: la prueba de vida corre en el navegador. Frena fotos y videos grabados (parpadeo, mirada y giro aleatorios), pero NO un atacante que llame directo a la API ni un deepfake en vivo. Para un portón real habría que firmar el cliente o hacer parte de la prueba en servidor.

## Umbral
`BIOMETRIA_UMBRAL` = similitud coseno mínima (default **0.90**, margen 1:N `BIOMETRIA_MARGEN=0.03`).
**Es provisional**: viene del punto de operación típico del modelo (dlib/face-api, distancia euclídea ~0.6 ≈ coseno 0.82–0.85 en LFW) subido a 0.90 para priorizar no dejar entrar a desconocidos. **No está medido con tus vecinos.** Para calibrarlo (5 min):
1. Abre `http://localhost:9300/calibracion-biometria.html`, captura 8 cuadros de ≥3 personas, descarga `capturas.json`.
2. `python tools/calibrar_umbral.py capturas.json` → imprime FAR/FRR, EER y el umbral recomendado.
3. Ponlo en `.env` (`BIOMETRIA_UMBRAL=...`) y reinicia Django.

## Modelos locales (funciona sin internet)
`frontend/vendor/`: MediaPipe tasks-vision 1.2.3 (Apache-2.0) + `face_landmarker.task`, y @vladmandic/face-api 1.7.15 (MIT) con modelos tiny_face_detector, face_landmark_68 y face_recognition.

## Cámara y HTTPS
La cámara solo funciona en contexto seguro: `http://localhost:9300` en la laptop funciona tal cual. Desde otro dispositivo por IP hace falta HTTPS:
1. `choco install mkcert` (o `scoop install mkcert`), luego `mkcert -install`.
2. `mkcert 192.168.X.X localhost` (tu IP) → genera `.pem` y `-key.pem`.
3. Sirve el frontend con HTTPS (p. ej. `npx http-server centinela_identidad/frontend -p 9300 -S -C cert.pem -K key.pem`).
4. Django (:9000) sigue en HTTP: el navegador bloqueará esa llamada mezclada. Sirve también Django con TLS (`pip install django-extensions werkzeug pyOpenSSL`, `python manage.py runserver_plus --cert-file cert.pem 0.0.0.0:9000`) e instala la CA de mkcert en el otro dispositivo.

## Modo feria (`ASISTENTE_MODO_FERIA=true`)
- `python manage.py seed_feria` crea 3 vecinos ficticios (contraseña `demo1234`), sin biometría: se registran en vivo desde el Portón (con aviso de privacidad + consentimiento).
- Todo lo registrado se marca **demo**. Botón "Borrar TODOS los datos demo" en el Portón; también `python manage.py borrar_demo`, y al cerrar Django con Ctrl+C (no si se mata el proceso a la fuerza).
- Si la cámara falla en el login, el modo feria permite "omitir" (queda en la bitácora).

## Prueba manual guiada (en Chrome, `http://localhost:9300`)
Preparación: Django arriba con `ASISTENTE_MODO_FERIA=true`, `python manage.py seed_feria`, buena luz de frente, una sola persona.
1. **Registro en vivo:** `porton.html` → elige "Ana Torres (demo)", marca consentimiento, "Registrar rostro". Verás malla verde, pupilas amarillas y su flecha de mirada. Sigue las 3 pruebas (orden aleatorio): parpadear 2 veces; seguir el punto rojo SOLO con los ojos; girar un poco la cabeza hacia el lado indicado. Luego "Guardar".
2. **Portón, vecino:** "Iniciar cámara", mira de frente, parpadea una vez → "Acceso concedido: Ana Torres, Casa 21", portón se abre, sonido, aparece en el panel.
3. **Portón, desconocido:** que otra persona parpadee frente a la cámara → "Visitante no registrado", NO abre, panel con "Visita pendiente".
4. **Engañar con foto:** muestra en el celular una foto de Ana a la cámara: no hay parpadeo → "Prueba de vida no superada". Repite con un VIDEO de Ana en el celular: el parpadeo podría coincidir en el portón (solo pide 1), pero en el registro/segundo factor fallará el punto de mirada o el giro aleatorio. Anota si alguna pasa.
5. **Rechazos:** tapa la cámara a medias (poca luz), ponte muy lejos/cerca, o entren dos personas: debe avisar en español.
6. **Segundo factor:** en `perfil.html` (sesión de Ana) registra tu rostro; cierra sesión y entra de nuevo: tras la contraseña pide la cara.
7. **Asistente:** `Centinela, ¿quién entró hoy?` y `¿hubo visitantes no registrados?` (con sesión de admin).
8. **Borrado:** Perfil → "Borrar mi biometría"; y en el Portón "Borrar TODOS los datos demo".
Si algo falla, los umbrales de la prueba están en `CFG` al inicio de `js/biometria-core.js` (`miradaDelta`, `giroCabeza`, `ojoCerrado`).
