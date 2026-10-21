# Mapa de Puertos — Centinela

## Servicios activos

| Puerto | Servicio | Directorio | Cómo iniciar |
|--------|----------|-----------|--------------|
| **:8000** | Django — Auth + IA + Admin | `centinela_identidad/backend_django/` | `python manage.py runserver 0.0.0.0:8000` |
| **:5001** | Flask — SDRI (Incidencias) | `Servicio de Reporte de Incidencias/` | `python SDRI.PY` |
| **:5002** | Flask — Posts / Tablón | `centinela_app/centinela_app/backend/` | `python app.py` |
| **:5003** | FastAPI — Chat WebSocket | `api/api/` | `uvicorn main:app --port 5003` |
| **:5004** | Flask — Decisiones / Encuestas | `servicio_decisiones/` | `python -m backend.app` |
| **—** | Frontend estático | `centinela_identidad/frontend/` | Abrir `index.html` en navegador, o servirlo desde :5002 |

## Puerto DEPRECATED

| Puerto | Servicio | Estado |
|--------|----------|--------|
| ~~:5000~~ | Flask legacy auth | ❌ Reemplazado por Django :8000 — ver `centinela_identidad/backend/DEPRECATED.md` |

## Endpoints principales por servicio

### :8000 — Django Auth + IA
```
POST /auth/registro
POST /auth/login
POST /auth/logout
POST /auth/solicitar-recuperacion
POST /auth/validar-token-recuperacion
POST /auth/cambiar-password
GET  /auth/verificar-token          ← usado por todos los demás servicios
POST /api/ia/chat/                  ← asistente Claude
POST /api/location/update/
POST /api/location/consent/
GET  /api/admin/usuarios/
```

### :5001 — SDRI Incidencias
```
POST /api/reportar_incidencia
GET  /api/incidencias
POST /api/actualizar_incidencia
```

### :5002 — Posts / Tablón
```
GET  /api/posts
POST /api/posts/crear
POST /api/posts/<id>/like
POST /api/posts/<id>/comentar
GET  /api/events
POST /api/events/crear
```

### :5003 — Chat WebSocket
```
WS   /ws/{sala}?token=<session_token>   ← conexión WebSocket
GET  /historial?sala=general             ← historial REST
GET  /docs                               ← Swagger UI
```

### :5004 — Decisiones / Encuestas
```
GET  /consultas
POST /admin/consultas
POST /votos
```

## Variables de entorno requeridas

Ver `.env.example` en la raíz del proyecto.
La variable crítica para el asistente IA es `ANTHROPIC_API_KEY`.

## Dependencias entre servicios

```
Frontend
  └── :8000  (auth — todos los tokens pasan por aquí)
  └── :5001  (incidencias)
  └── :5002  (posts)
  └── :5003  (chat — verifica tokens contra :8000)
  └── :5004  (decisiones — verifica tokens contra :8000)

:5003 → :8000  (GET /auth/verificar-token)
:5004 → :8000  (GET /auth/verificar-token)
:5002 → :8000  (GET /auth/verificar-token)
```

**Regla:** Django (:8000) debe estar corriendo antes que cualquier otro servicio.
