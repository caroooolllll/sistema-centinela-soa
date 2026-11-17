/**
 * LOGIN.JS - Inicio de sesión con captura de geolocalización
 */

const runtime = window.CentinelaRuntime;
const API_URL = runtime ? runtime.serviceUrl(9000) : 'http://localhost:9000';

const loginForm = document.getElementById('loginForm');
const btnLogin = document.getElementById('btnLogin');
const mensajeDiv = document.getElementById('mensaje');

// Mostrar mensaje
function mostrarMensaje(texto, tipo = 'info') {
    mensajeDiv.textContent = texto;
    mensajeDiv.className = `mensaje ${tipo} show`;

    setTimeout(() => {
        mensajeDiv.classList.remove('show');
    }, 5000);
}

// Guardar sesión
function guardarSesion(datos) {
    localStorage.setItem('token', datos.token);
    localStorage.setItem('userId', datos.userId);
    localStorage.setItem('nombre', datos.nombre);
    localStorage.setItem('usuarioActual', datos.nombre);
    localStorage.setItem('numeroCasa', datos.numeroCasa);
    localStorage.setItem('rolActual', datos.rol || 'usuario');
    if ((datos.rol || 'usuario') === 'admin') {
        sessionStorage.setItem('centinela_admin', '1');
    } else {
        sessionStorage.removeItem('centinela_admin');
    }
}

// Función para escapar caracteres XML
function escapeXML(unsafe) {
    if (!unsafe) return '';
    return unsafe.replace(/[<>&'"]/g, function (c) {
        switch (c) {
            case '<': return '&lt;';
            case '>': return '&gt;';
            case '&': return '&amp;';
            case '\'': return '&apos;';
            case '"': return '&quot;';
        }
    });
}

// Realizar login
async function realizarLogin(email, password) {
    try {
        btnLogin.disabled = true;
        btnLogin.classList.add('loading');
        btnLogin.textContent = 'Iniciando...';

        // Capturar ubicación actual (no bloquea el login si falla)
        let geoData = null;
        if (window.Geo) {
            geoData = await window.Geo.capturarLogin();
        }

        const xmlData = `
            <loginRequest>
                <email>${escapeXML(email)}</email>
                <password>${escapeXML(password)}</password>
                <latitud>${geoData ? geoData.latitude : ''}</latitud>
                <longitud>${geoData ? geoData.longitude : ''}</longitud>
            </loginRequest>
        `;

        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/xml'
            },
            body: xmlData.trim()
        });

        const responseText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(responseText, 'application/xml');

        const estado = xmlDoc.getElementsByTagName('estado')[0].textContent;
        const mensaje = xmlDoc.getElementsByTagName('mensaje')[0].textContent;

        if (estado === 'OK') {
            const token = xmlDoc.getElementsByTagName('token')[0].textContent;
            const userId = xmlDoc.getElementsByTagName('userId')[0].textContent;
            const nombre = xmlDoc.getElementsByTagName('nombre')[0].textContent;
            const numeroCasa = xmlDoc.getElementsByTagName('numeroCasa')[0].textContent;
            const rolNode = xmlDoc.getElementsByTagName('rol')[0];
            const rol = rolNode ? rolNode.textContent : 'usuario';

            // Segundo factor facial (solo si el vecino registró su rostro)
            const bioNode = xmlDoc.getElementsByTagName('biometriaPendiente')[0];
            if (bioNode && bioNode.textContent === 'true') {
                mostrarMensaje('Verificación facial requerida…', 'exito');
                const ok = await segundoFactorFacial(token);
                if (!ok) { mostrarMensaje('No se pudo verificar tu rostro. Acceso denegado.', 'error'); return; }
            }

            mostrarMensaje(`¡Bienvenido, ${nombre}! ✅`, 'exito');
            guardarSesion({ token, userId, nombre, numeroCasa, rol });

            // Iniciar seguimiento continuo de ubicación
            if (window.Geo) {
                window.Geo.iniciarTracking(token);
            }

            // Redirigir al servicio destino pasando el token en la URL
            // para que los otros servicios puedan guardarlo en su localStorage
            setTimeout(() => {
                // Detectar si vino desde otro servicio (parámetro redirect)
                const params = new URLSearchParams(window.location.search);
                const redirect = params.get('redirect');

                if (redirect === 'incidencias') {
                    window.location.href = runtime ? runtime.serviceUrl(9000, '/api/consultar_incidencias') : 'http://localhost:9000/api/consultar_incidencias';
                } else if (redirect === 'chat') {
                    window.location.href = runtime ? runtime.serviceUrl(9000, '/chat-component') : 'http://localhost:9000/chat-component';
                } else if (rol === 'admin') {
                    const adminUrl = runtime ? runtime.appUrl('admin.html') : 'http://localhost:9300/admin.html';
                    window.location.href = adminUrl;
                } else {
                    const dashboardUrl = runtime ? runtime.appUrl('dashboard.html') : 'http://localhost:9300/dashboard.html';
                    window.location.href = `${dashboardUrl}?token=${encodeURIComponent(token)}&usuario=${encodeURIComponent(nombre)}&casa=${encodeURIComponent(numeroCasa)}`;
                }
            }, 1500);

        } else {
            mostrarMensaje(mensaje, 'error');
        }

    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error de conexión. Verifica que la API esté activa.', 'error');
    } finally {
        btnLogin.disabled = false;
        btnLogin.classList.remove('loading');
        btnLogin.textContent = 'Iniciar sesión';
    }
}

// Manejar envío del formulario
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const email = document.getElementById('email').value.trim().toLowerCase();
    const password = document.getElementById('password').value;

    if (!email || !password) {
        mostrarMensaje('Por favor, completa todos los campos', 'error');
        return;
    }

    await realizarLogin(email, password);
});

// Verificar si ya hay sesión activa
window.addEventListener('DOMContentLoaded', async () => {
    const token = localStorage.getItem('token');

    if (token) {
        try {
            const response = await fetch(`${API_URL}/auth/verificar-token`, {
                headers: { 'Authorization': `Token ${token}` }
            });

            const data = await response.json();

            if (data.valido) {
                const nombre = localStorage.getItem('nombre');
                const rolActual = localStorage.getItem('rolActual') || 'usuario';
                mostrarMensaje(`Ya tienes una sesión activa (${nombre})`, 'info');
                if (window.Geo) {
                    window.Geo.iniciarTracking(token);
                }
                setTimeout(() => {
                    if (rolActual === 'admin') {
                        const adminUrl = runtime ? runtime.appUrl('admin.html') : 'http://localhost:9300/admin.html';
                        window.location.href = adminUrl;
                    } else {
                        const dashboardUrl = runtime ? runtime.appUrl('dashboard.html') : 'http://localhost:9300/dashboard.html';
                        window.location.href = `${dashboardUrl}?token=${encodeURIComponent(token)}&usuario=${encodeURIComponent(nombre)}`;
                    }
                }, 1500);
            } else {
                localStorage.clear();
            }
        } catch (error) {
            console.error('Error al verificar sesión:', error);
            localStorage.clear();
        }
    }
});

// Detener tracking al cerrar sesión o la pestaña
window.addEventListener('beforeunload', () => {
    if (window.Geo) {
        window.Geo.detenerTracking();
    }
});


// ── Segundo factor facial: carga la librería local y verifica con la cámara ──
async function segundoFactorFacial(token) {
    await new Promise((ok, mal) => {
        if (window.CentinelaBio) return ok();
        const sc = document.createElement('script'); sc.src = 'js/biometria-core.js'; sc.onload = ok; sc.onerror = mal; document.head.appendChild(sc);
    });
    const r = await window.CentinelaBio.verificar({ token, origen: 'login', motivo: 'Verifica tu rostro para entrar', titulo: 'Segundo factor' });
    if (r.ok) return true;
    // Modo feria: si la cámara falla en plena demo se permite omitir (queda en la bitácora)
    const cfg = await window.CentinelaBio.api('/config/', { token: '' });
    if (cfg.modo_feria && confirm('Modo feria: ¿omitir la verificación facial y entrar?')) {
        const o = await window.CentinelaBio.api('/omitir/', { metodo: 'POST', cuerpo: {}, token });
        return o.estado === 'OK';
    }
    return false;
}
