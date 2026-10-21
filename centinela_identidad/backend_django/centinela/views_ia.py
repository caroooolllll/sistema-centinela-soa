import os
import json
import anthropic
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

def _api_key():
    k = os.getenv("ANTHROPIC_API_KEY", "")
    return k if k and k not in ("tu_api_key_aqui", "your_api_key_here") else None


@csrf_exempt
@require_http_methods(["POST"])
def chat_ia(request):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key or api_key in ("", "tu_api_key_aqui", "your_api_key_here"):
        return JsonResponse(
            {
                "error": "API key de Anthropic no configurada",
                "instrucciones": "Copia .env.example a .env y agrega tu API key",
            },
            status=503,
        )

    try:
        body = json.loads(request.body)
        mensaje = body.get("mensaje", "").strip()
        contexto = body.get("contexto", "")

        if not mensaje:
            return JsonResponse({"error": "El campo 'mensaje' es requerido"}, status=400)

        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = (
            "Eres el asistente inteligente de Centinela, sistema de seguridad vecinal "
            "de Privada La Condesa. Ayuda a vecinos con incidencias, uso del sistema y "
            "preguntas sobre la privada. Si detectas emergencia real responde con "
            "ACTIVAR_SOS al inicio. Responde siempre en español, claro y empático."
        )

        messages = []
        if contexto:
            messages.append({"role": "user", "content": contexto})
            messages.append({"role": "assistant", "content": "Entendido, tengo el contexto."})
        messages.append({"role": "user", "content": mensaje})

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )

        texto = response.content[0].text
        activar_sos = texto.startswith("ACTIVAR_SOS")

        return JsonResponse({"respuesta": texto, "activar_sos": activar_sos})

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido en el cuerpo de la solicitud"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Error interno: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def extraer_reporte_ia(request):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key or api_key in ("", "tu_api_key_aqui", "your_api_key_here"):
        return JsonResponse(
            {
                "error": "API key de Anthropic no configurada",
                "instrucciones": "Copia .env.example a .env y agrega tu ANTHROPIC_API_KEY",
            },
            status=503,
        )

    try:
        body = json.loads(request.body)
        transcripcion = body.get("transcripcion", "").strip()

        if not transcripcion:
            return JsonResponse({"error": "El campo 'transcripcion' es requerido"}, status=400)

        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = (
            "Eres un extractor de reportes para Centinela, sistema vecinal de Privada La Condesa. "
            "Analiza la transcripción de voz y extrae la información del incidente. "
            "Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin bloques markdown, sin ```. "
            "El JSON debe tener exactamente estos campos:\n"
            '- "categoria": clasifica el reporte. Usa EXACTAMENTE uno de: "seguridad", "ambiental"\n'
            '  * "seguridad" = robo, vandalismo, persona sospechosa, accidente, violencia, daños\n'
            '  * "ambiental" = tiradero, fuga de agua, árbol caído, incendio/quema, alumbrado, animal\n'
            '- "tipo": tipo específico del incidente. Según categoria, usa exactamente uno de:\n'
            '  Seguridad: "Robo", "Vandalismo", "Ruido excesivo", "Persona sospechosa", '
            '"Accidente vial", "Daño a propiedad", "Emergencia médica", "Otro"\n'
            '  Ambiental: "Tiradero clandestino", "Fuga de agua", "Árbol caído o dañado", '
            '"Riesgo de incendio o quema", "Alumbrado desperdiciando energía", "Animal en peligro o maltrato"\n'
            '- "prioridad": nivel de urgencia. Usa EXACTAMENTE uno de: "Baja", "Media", "Crítica"\n'
            '  * "Baja" = incidente menor sin urgencia inmediata\n'
            '  * "Media" = requiere atención, no es emergencia activa\n'
            '  * "Crítica" = emergencia activa, peligro inminente, violencia, lesionados\n'
            '- "ubicacion": calle, lugar o zona mencionada, o "" si no se menciona\n'
            '- "descripcion": resumen claro y objetivo del incidente en 1-2 frases, máximo 200 caracteres\n'
            '- "confianza": entero 0-100 indicando claridad del reporte '
            '(100=muy claro y completo, 50=información parcial, 0=incomprensible)\n'
            "Si la transcripción es incomprensible o vacía, devuelve campos vacíos y confianza=0."
        )

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Transcripción del reporte:\n{transcripcion}"}],
        )

        texto = response.content[0].text.strip()

        if texto.startswith("```"):
            lineas = [l for l in texto.split("\n") if not l.strip().startswith("```")]
            texto = "\n".join(lineas).strip()

        datos = json.loads(texto)

        if datos.get("prioridad") not in ("Baja", "Media", "Crítica"):
            datos["prioridad"] = "Baja"

        if datos.get("categoria") not in ("seguridad", "ambiental"):
            datos["categoria"] = "seguridad"

        tipos_validos = {
            "Robo", "Vandalismo", "Ruido excesivo", "Persona sospechosa",
            "Accidente vial", "Daño a propiedad", "Emergencia médica", "Otro",
            "Tiradero clandestino", "Fuga de agua", "Árbol caído o dañado",
            "Riesgo de incendio o quema", "Alumbrado desperdiciando energía", "Animal en peligro o maltrato",
        }
        if datos.get("tipo") not in tipos_validos:
            datos["tipo"] = "Otro" if datos.get("categoria") == "seguridad" else "Tiradero clandestino"

        try:
            confianza = max(0, min(100, int(datos.get("confianza", 50))))
        except (ValueError, TypeError):
            confianza = 50

        return JsonResponse({
            "categoria": datos.get("categoria", "seguridad"),
            "tipo": datos.get("tipo", "Otro"),
            "prioridad": datos["prioridad"],
            "ubicacion": str(datos.get("ubicacion", "")),
            "descripcion": str(datos.get("descripcion", "")),
            "confianza": confianza,
        })

    except json.JSONDecodeError as e:
        return JsonResponse({"error": f"Respuesta de IA no es JSON válido: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Error interno: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def analizar_foto_ia(request):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key or api_key in ("", "tu_api_key_aqui", "your_api_key_here"):
        return JsonResponse(
            {
                "error": "API key de Anthropic no configurada",
                "instrucciones": "Copia .env.example a .env y agrega tu ANTHROPIC_API_KEY",
            },
            status=503,
        )

    try:
        body = json.loads(request.body)
        imagen_base64 = body.get("imagen_base64", "").strip()
        media_type = body.get("media_type", "image/jpeg")

        if not imagen_base64:
            return JsonResponse({"error": "El campo 'imagen_base64' es requerido"}, status=400)

        if "," in imagen_base64:
            imagen_base64 = imagen_base64.split(",", 1)[1]

        if media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
            media_type = "image/jpeg"

        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = (
            "Eres un clasificador de incidencias urbanas y ambientales para Centinela, "
            "sistema vecinal de Privada La Condesa. Analiza la imagen y determina qué tipo "
            "de incidencia o problema muestra. "
            "Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin bloques markdown. "
            "El JSON debe tener exactamente estos campos:\n"
            '- "categoria": "seguridad" o "ambiental"\n'
            '  * "seguridad" = robo, vandalismo, accidente, persona sospechosa, daños, violencia\n'
            '  * "ambiental" = basura/tiradero, fuga de agua, árbol caído, incendio/quema, alumbrado, animal\n'
            '- "tipo": usa EXACTAMENTE uno de:\n'
            '  Seguridad: "Robo", "Vandalismo", "Ruido excesivo", "Persona sospechosa", '
            '"Accidente vial", "Daño a propiedad", "Emergencia médica", "Otro"\n'
            '  Ambiental: "Tiradero clandestino", "Fuga de agua", "Árbol caído o dañado", '
            '"Riesgo de incendio o quema", "Alumbrado desperdiciando energía", "Animal en peligro o maltrato"\n'
            '- "prioridad": "Baja", "Media" o "Crítica"\n'
            '  * "Crítica" = emergencia activa, peligro inminente, lesionados visibles\n'
            '  * "Media" = problema que requiere atención próxima\n'
            '  * "Baja" = sin urgencia inmediata\n'
            '- "descripcion_sugerida": 1-2 frases objetivas sobre lo visible en la imagen, máx 200 chars\n'
            '- "confianza": 0-100 (100=imagen clara y tipo evidente; baja si ambigua o sin incidencia)\n'
            "Si la imagen no muestra una incidencia relevante, usa confianza baja y tipo 'Otro'."
        )

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=512,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": imagen_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Analiza esta imagen y clasifica el tipo de incidencia o problema que muestra.",
                        },
                    ],
                }
            ],
        )

        texto = response.content[0].text.strip()

        if texto.startswith("```"):
            lineas = [l for l in texto.split("\n") if not l.strip().startswith("```")]
            texto = "\n".join(lineas).strip()

        datos = json.loads(texto)

        if datos.get("categoria") not in ("seguridad", "ambiental"):
            datos["categoria"] = "seguridad"

        if datos.get("prioridad") not in ("Baja", "Media", "Crítica"):
            datos["prioridad"] = "Baja"

        tipos_validos = {
            "Robo", "Vandalismo", "Ruido excesivo", "Persona sospechosa",
            "Accidente vial", "Daño a propiedad", "Emergencia médica", "Otro",
            "Tiradero clandestino", "Fuga de agua", "Árbol caído o dañado",
            "Riesgo de incendio o quema", "Alumbrado desperdiciando energía", "Animal en peligro o maltrato",
        }
        if datos.get("tipo") not in tipos_validos:
            datos["tipo"] = "Otro" if datos.get("categoria") == "seguridad" else "Tiradero clandestino"

        try:
            confianza = max(0, min(100, int(datos.get("confianza", 50))))
        except (ValueError, TypeError):
            confianza = 50

        return JsonResponse({
            "categoria": datos.get("categoria", "seguridad"),
            "tipo": datos.get("tipo", "Otro"),
            "prioridad": datos.get("prioridad", "Baja"),
            "descripcion_sugerida": str(datos.get("descripcion_sugerida", ""))[:200],
            "confianza": confianza,
        })

    except json.JSONDecodeError as e:
        return JsonResponse({"error": f"Respuesta de IA no es JSON válido: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Error interno: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def asistente_ia(request):
    """Interpretación de intención + navegación — Asistente Centinela v3."""
    api_key = _api_key()
    if not api_key:
        return JsonResponse({"error": "ANTHROPIC_API_KEY no configurada"}, status=503)

    try:
        from datetime import datetime
        body = json.loads(request.body)
        mensaje = body.get("mensaje", "").strip()

        if not mensaje:
            return JsonResponse({"error": "Campo 'mensaje' requerido"}, status=400)

        client = anthropic.Anthropic(api_key=api_key)
        fecha_hoy = datetime.now().strftime("%Y-%m-%d (%A)")

        system_prompt = (
            "Eres el Asistente Centinela, IA de Privada La Condesa. Interpreta el mensaje del usuario "
            "y devuelve la acción más apropiada como JSON.\n\n"
            "Páginas del sistema:\n"
            "- dashboard.html → inicio, panel, home\n"
            "- chat.html → chat, mensajes, conversar con vecinos\n"
            "- eventos.html → eventos, agenda, actividades comunitarias\n"
            "- noticias.html → noticias del sistema\n"
            "- avisos.html → avisos, comunicados, tablón, incidencias, reportes\n"
            "- encuestas.html → encuestas, votaciones, decisiones\n"
            "- historial.html → historial, reportes anteriores\n"
            "- panico.html → pánico, emergencia, SOS, ayuda urgente\n"
            "- accesibilidad-modo.html → accesibilidad, modo accesible\n"
            "- perfil.html → perfil, mi cuenta\n"
            "- configuracion.html → configuración, ajustes\n"
            "- notificaciones.html → notificaciones, alertas\n"
            "- publicaciones.html → publicaciones, posts, foros\n"
            "- emergencia-contactos.html → contactos de emergencia, directorio\n\n"
            "RESPONDE ÚNICAMENTE con JSON válido sin markdown ni bloques de código:\n"
            "{\n"
            '  "tipo": "navegacion"|"reporte"|"incompleto"|"respuesta"|"emergencia"|"mensaje_vecino"|"nuevo_evento"|"nueva_encuesta"|"nuevo_aviso",\n'
            '  "destino": "pagina.html"|null,\n'
            '  "respuesta": "texto amigable en español máximo 80 palabras",\n'
            '  "reporte_completo": true|false,\n'
            '  "datos_reporte": {"transcripcion":"...","prioridad_usuario":"Baja"|"Media"|"Alta"|"Crítica"|null}|null,\n'
            '  "datos_mensaje": {"destinatario":"nombre del vecino","contenido":"texto exacto del mensaje a enviar"}|null,\n'
            '  "datos_evento": {"titulo":"...","descripcion":"...","fecha":"YYYY-MM-DD o vacío","hora":"HH:MM o vacío","categoria":"Cultural|Deportivo|Comunitario|Seguridad|Educativo"}|null,\n'
            '  "datos_encuesta": {"pregunta":"...","opciones":["op1","op2","op3"]}|null,\n'
            '  "datos_aviso": {"descripcion":"...","categoria":"Seguridad|Mantenimiento|Servicios|Mascotas|Comunidad|General","prioridad":"Baja|Media|Crítica"}|null\n'
            "}\n\n"
            "REGLAS DE CLASIFICACIÓN (en orden de prioridad):\n"
            "1. emergencia: peligro inmediato real, violencia activa.\n"
            "2. mensaje_vecino: 'mándale un mensaje a [nombre]', 'escríbele a [nombre]', 'dile a [nombre]'. "
            "   Extrae destinatario (nombre) y contenido. "
            "   Si NO hay destinatario claro: tipo=incompleto con ejemplo. "
            "   Si hay destinatario pero NO hay contenido: tipo=incompleto con ejemplo '¿Qué mensaje le quieres enviar a [nombre]? Ejemplo: Centinela, mándale un mensaje a [nombre] que diga: tu mensaje aquí'.\n"
            "3. nuevo_evento: 'crea un evento', 'programa una junta/reunión/actividad', 'agenda'. "
            "   Extrae título, descripción, fecha (convierte relativa a YYYY-MM-DD si puedes), hora, categoría apropiada. "
            "   Si no hay título: tipo=incompleto con ejemplo.\n"
            "4. nueva_encuesta: 'haz una encuesta sobre X', 'pregunta a los vecinos si X', 'votación sobre X'. "
            "   Extrae pregunta y opciones (si no se mencionan: ['Sí','No','Me abstengo']). "
            "   Si no hay pregunta clara: tipo=incompleto.\n"
            "5. nuevo_aviso: 'publica un aviso', 'comunica que', 'anuncia', 'avisa que'. "
            "   Extrae descripción, categoría apropiada, prioridad sugerida. "
            "   Si no hay descripción: tipo=incompleto con ejemplo.\n"
            "6. reporte: incidencia de seguridad o ambiental ('robo', 'vandalismo', 'árbol caído', etc.). "
            "   reporte_completo=true si menciona QUÉ ocurrió. "
            "   Extrae prioridad_usuario si la mencionó. destino='avisos.html'.\n"
            "7. incompleto: acción sin suficientes detalles. "
            "   La respuesta DEBE incluir un ejemplo concreto de cómo completar el comando.\n"
            "8. navegacion: solo quiere ir a una sección.\n"
            "9. respuesta: pregunta general o conversación."
        )

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": f"[Fecha actual: {fecha_hoy}]\nMensaje: {mensaje}"}],
        )

        texto = response.content[0].text.strip()
        if texto.startswith("```"):
            lineas = [l for l in texto.split("\n") if not l.strip().startswith("```")]
            texto = "\n".join(lineas).strip()

        datos = json.loads(texto)

        tipos_validos = {
            "navegacion", "reporte", "incompleto", "respuesta", "emergencia",
            "mensaje_vecino", "nuevo_evento", "nueva_encuesta", "nuevo_aviso",
        }
        if datos.get("tipo") not in tipos_validos:
            datos["tipo"] = "respuesta"

        return JsonResponse({
            "tipo": datos.get("tipo", "respuesta"),
            "destino": datos.get("destino"),
            "respuesta": str(datos.get("respuesta", ""))[:400],
            "reporte_completo": bool(datos.get("reporte_completo", False)),
            "datos_reporte": datos.get("datos_reporte"),
            "datos_mensaje": datos.get("datos_mensaje"),
            "datos_evento": datos.get("datos_evento"),
            "datos_encuesta": datos.get("datos_encuesta"),
            "datos_aviso": datos.get("datos_aviso"),
        })

    except json.JSONDecodeError as e:
        return JsonResponse({"error": f"Respuesta IA no es JSON: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Error interno: {str(e)}"}, status=500)
