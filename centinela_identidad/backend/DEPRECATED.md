# DEPRECATED — Backend Flask Legacy

Este directorio contiene la versión original del Servicio de Identidad
escrita en Flask. **Ya no está en uso.**

## Reemplazado por

`centinela_identidad/backend_django/` — misma funcionalidad reescrita
en Django 5.0 con las siguientes mejoras:

| Característica | Flask legacy (:5000) | Django actual (:9000) |
|---|---|---|
| Auth (registro/login) | ✅ | ✅ |
| Recuperación de contraseña | ✅ | ✅ |
| Geolocalización en login | ❌ | ✅ |
| Auditoría de accesos | ❌ | ✅ |
| Asistente IA (Claude) | ❌ | ✅ |
| Verificación inter-servicios | ✅ | ✅ |
| Migraciones de DB | manual | `manage.py migrate` |

## Por qué se mantuvo el directorio

Para referencia durante la migración. Una vez confirmado que todos los
servicios apuntan a `:9000`, este directorio puede eliminarse de forma segura.

## Cómo eliminar

```bash
rm -rf centinela_identidad/backend/
```

Antes de hacerlo, asegúrate de que ningún servicio apunte a `localhost:5000`.
Consulta `PUERTOS.md` en la raíz del proyecto para el mapa actual de puertos.
