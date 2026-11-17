"""Pruebas del pipeline del asistente. Correr:  python manage.py test centinela.asistente"""
import json
from unittest import mock

from django.test import SimpleTestCase, Client

from . import atajos, config, proveedores
from .parser import ParserStream, MARCA
from .proveedores import Cadena, ProveedorError, clasificar_429

_red = None


def setUpModule():
    """Las pruebas no dependen de que la máquina tenga internet."""
    global _red
    _red = mock.patch("centinela.asistente.red.hay_internet", return_value=True)
    _red.start()


def tearDownModule():
    _red.stop()


class AtajoSOS(SimpleTestCase):
    FRASES = ["auxilio", "Centinela, emergencia", "me están robando", "ayuda", "necesito ayuda",
              "Centinela, socorro", "hay un incendio en la casa 12", "activa el SOS", "llama a la policía",
              "es una emergencia", "me quieren asaltar", "SOS"]
    NO_SOS = ["ayúdame a crear un reporte", "abre contactos de emergencia", "cómo activo el SOS",
              "dime los eventos de hoy", "abre reportes", "ayuda con mi perfil por favor ver"]

    def test_detecta_sos(self):
        for f in self.FRASES:
            self.assertTrue(atajos.es_sos(f), f)

    def test_no_falsos_positivos(self):
        for f in self.NO_SOS:
            self.assertFalse(atajos.es_sos(f), f)

    def test_sos_sin_internet_ni_llm(self):
        """El atajo SOS es una función pura: con red y proveedores bloqueados sigue funcionando."""
        with mock.patch("httpx.stream", side_effect=AssertionError("no debe usar red")), \
             mock.patch("httpx.post", side_effect=AssertionError("no debe usar red")), \
             mock.patch("httpx.get", side_effect=AssertionError("no debe usar red")):
            a = atajos.resolver_atajo("Centinela, auxilio, me están robando")
        self.assertEqual(a["tipo"], "emergencia")
        self.assertEqual(a["destino"], "panico.html")
        self.assertTrue(a["activar_sos"])

    def test_endpoint_sos_responde_sin_llm(self):
        with mock.patch.dict(proveedores.PROVEEDORES, {k: mock.Mock(side_effect=AssertionError("LLM")) for k in
                                                       ("groq", "gemini", "claude", "local")}):
            r = Client().post("/api/ia/asistente/stream/", json.dumps({"mensaje": "auxilio"}),
                              content_type="application/json")
            cuerpo = b"".join(r.streaming_content).decode()
        self.assertIn("event: accion", cuerpo)
        self.assertIn('"activar_sos": true', cuerpo)
        self.assertIn('"proveedor": "atajo"', cuerpo)


class CasosCompartidos(SimpleTestCase):
    """Los mismos casos que prueba el espejo JS (frontend/tests/atajos.test.js)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import pathlib
        cls.casos = json.loads((pathlib.Path(__file__).parent / "casos_atajos.json").read_text(encoding="utf-8"))

    def test_sos(self):
        for f in self.casos["sos"]:
            self.assertTrue(atajos.es_sos(f), f)
        for f in self.casos["no_sos"]:
            self.assertFalse(atajos.es_sos(f), f)

    def test_nav(self):
        for f, destino in self.casos["nav"].items():
            self.assertEqual((atajos.detectar_navegacion(f) or [None])[0], destino, f)
        for f in self.casos["no_nav"]:
            self.assertIsNone(atajos.resolver_atajo(f), f)

    def test_paridad_con_javascript(self):
        import os, shutil, subprocess, pathlib
        win = "C:/Program Files/nodejs/node.exe"
        node = shutil.which("node") or (win if os.path.exists(win) else None)
        if not node:
            self.skipTest("node no instalado")
        carpeta = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "tests" / "atajos.test.js"
        r = subprocess.run([node, "--test", str(carpeta)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-500:])


class AtajoNavegacion(SimpleTestCase):
    CASOS = {
        "abre reportes": "avisos.html", "ve a eventos": "eventos.html", "llévame al dashboard": "dashboard.html",
        "Centinela, abre el chat": "chat.html", "ir al inicio": "dashboard.html", "abre mi perfil": "perfil.html",
        "muéstrame las encuestas": "encuestas.html", "abre el historial": "historial.html",
        "llévame a la configuración por favor": "configuracion.html",
        "abre contactos de emergencia": "emergencia-contactos.html", "abre notificaciones": "notificaciones.html",
    }

    def test_navegacion(self):
        for frase, destino in self.CASOS.items():
            n = atajos.detectar_navegacion(frase)
            self.assertIsNotNone(n, frase)
            self.assertEqual(n[0], destino, frase)

    def test_no_es_navegacion(self):
        for f in ["crea un evento de reunión el viernes", "abre un reporte de que hay un árbol caído",
                  "qué pasó hoy en la privada", "mándale un mensaje a Sofia", "haz una encuesta sobre el portón"]:
            self.assertIsNone(atajos.detectar_navegacion(f), f)


class Parser(SimpleTestCase):
    def test_primera_oracion_sale_antes_de_terminar(self):
        p = ParserStream()
        self.assertEqual(p.feed("Claro, te llevo a los eventos. "), ["Claro, te llevo a los eventos."])
        self.assertEqual(p.feed("Allá verás la agenda"), [])
        self.assertEqual(p.feed(".\n" + MARCA[:5]), ["Allá verás la agenda."])
        p.feed(MARCA[5:] + '\n{"tipo":"navegacion",')
        p.feed('"destino":"eventos.html"}')
        resto, accion = p.finish()
        self.assertEqual(resto, [])
        self.assertEqual(accion["destino"], "eventos.html")

    def test_marca_partida_en_chunks(self):
        p = ParserStream()
        salida = []
        for ch in ["Listo, aviso publicado hoy.", "\n<<<AC", "CION>>", ">\n{\"tipo\":\"respuesta\"}"]:
            salida += p.feed(ch)
        resto, accion = p.finish()
        self.assertEqual(salida + resto, ["Listo, aviso publicado hoy."])
        self.assertEqual(accion["tipo"], "respuesta")

    def test_activar_sos_se_detecta_y_no_se_lee(self):
        p = ParserStream()
        out = p.feed("ACTIVAR_SOS Tranquila, activo la emergencia ahora mismo.\n" + MARCA + '\n{"tipo":"emergencia"}')
        resto, accion = p.finish()
        self.assertTrue(p.activar_sos)
        self.assertNotIn("ACTIVAR_SOS", " ".join(out + resto))

    def test_json_con_markdown_y_sin_accion(self):
        p = ParserStream()
        p.feed("Hola vecino, ¿en qué te ayudo hoy?\n" + MARCA + '\n```json\n{"tipo":"respuesta"}\n```')
        self.assertEqual(p.finish()[1]["tipo"], "respuesta")
        p2 = ParserStream()
        p2.feed("Solo texto sin acción alguna.")
        resto, accion = p2.finish()
        self.assertEqual(resto, ["Solo texto sin acción alguna."])
        self.assertIsNone(accion)


class Failover(SimpleTestCase):
    def _cadena(self, **provs):
        return mock.patch.dict(proveedores.PROVEEDORES, provs)

    def test_clasifica_429(self):
        self.assertEqual(clasificar_429("Rate limit reached ... on tokens per minute (TPM)", 2), "minuto")
        self.assertEqual(clasificar_429("Rate limit reached ... on tokens per day (TPD)", 2), "diario")
        self.assertEqual(clasificar_429("Quota exceeded: GenerateRequestsPerDayPerProjectPerModel"), "diario")
        self.assertEqual(clasificar_429("slow down", 90), "diario")  # esperar 90 s no vale la pena

    def test_429_por_minuto_espera_y_reintenta(self):
        llamadas = {"n": 0}

        def groq(system, msgs, mt):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise ProveedorError("minuto", "429", 1.5)
            yield "hola"

        esperas = []
        with self._cadena(groq=groq, gemini=mock.Mock(side_effect=AssertionError("no debe saltar"))):
            c = Cadena(["groq", "gemini"], sleep=esperas.append)
            self.assertEqual("".join(c.stream("s", [{"role": "user", "content": "x"}])), "hola")
        self.assertEqual(esperas, [1.5])
        self.assertEqual(c.proveedor, "groq")

    def test_429_diario_salta_de_inmediato(self):
        def groq(system, msgs, mt):
            raise ProveedorError("diario", "TPD")
            yield

        def gemini(system, msgs, mt):
            yield "desde gemini"

        esperas = []
        with self._cadena(groq=groq, gemini=gemini):
            c = Cadena(["groq", "gemini"], sleep=esperas.append)
            self.assertEqual("".join(c.stream("s", [{"role": "user", "content": "x"}])), "desde gemini")
        self.assertEqual(esperas, [])  # sin esperar nada
        self.assertEqual(c.proveedor, "gemini")

    def test_cadena_completa_hasta_local(self):
        def falla(system, msgs, mt):
            raise ProveedorError("otro", "caído")
            yield

        with self._cadena(groq=falla, gemini=falla, claude=falla):
            c = Cadena(["groq", "gemini", "claude", "local"], sleep=lambda s: None)
            texto = "".join(c.stream("s", [{"role": "user", "content": "hola"}]))
        self.assertEqual(c.proveedor, "local")
        self.assertIn(MARCA, texto)

    def test_429_minuto_dos_veces_pasa_al_siguiente(self):
        def groq(system, msgs, mt):
            raise ProveedorError("minuto", "429", 1)
            yield

        def gemini(system, msgs, mt):
            yield "ok"

        with self._cadena(groq=groq, gemini=gemini):
            c = Cadena(["groq", "gemini"], sleep=lambda s: None)
            self.assertEqual("".join(c.stream("s", [{"role": "user", "content": "x"}])), "ok")


class ContratoFrontend(SimpleTestCase):
    """El evento 'accion' mantiene las llaves que asistente.js ya entiende."""

    def _stream(self, texto_llm, mensaje="qué eventos hay"):
        def groq(system, msgs, mt):
            yield texto_llm
        with mock.patch.dict(proveedores.PROVEEDORES, {"groq": groq}), \
             mock.patch.object(config, "cadena", return_value=["groq"]), \
             mock.patch("centinela.asistente.contexto.avisos_recientes", return_value=""):
            r = Client().post("/api/ia/asistente/stream/", json.dumps({"mensaje": mensaje}),
                              content_type="application/json")
            cuerpo = b"".join(r.streaming_content).decode()
        eventos = {}
        for bloque in cuerpo.strip().split("\n\n"):
            nombre, datos = bloque.split("\n", 1)
            eventos.setdefault(nombre[7:], []).append(json.loads(datos[6:]))
        return eventos

    def test_llaves_y_borradores(self):
        ev = self._stream("Listo, preparo tu evento para el viernes.\n" + MARCA + "\n" + json.dumps(
            {"tipo": "nuevo_evento", "destino": "eventos.html",
             "datos_evento": {"titulo": "Junta", "descripcion": "", "fecha": "2026-11-20", "hora": "18:00",
                              "categoria": "Comunitario"}}))
        a = ev["accion"][0]
        for k in ("tipo", "destino", "respuesta", "reporte_completo", "datos_reporte", "datos_mensaje",
                  "datos_evento", "datos_encuesta", "datos_aviso", "activar_sos"):
            self.assertIn(k, a)
        self.assertEqual(a["datos_evento"]["titulo"], "Junta")
        self.assertEqual(ev["frase"][0]["texto"], "Listo, preparo tu evento para el viernes.")
        self.assertEqual(ev["fin"][0]["proveedor"], "groq")

    def test_emergencia_del_llm_activa_sos(self):
        ev = self._stream("Activo la emergencia ya.\n" + MARCA + '\n{"tipo":"emergencia"}', "siento que alguien me sigue")
        self.assertTrue(ev["accion"][0]["activar_sos"])
        self.assertEqual(ev["accion"][0]["destino"], "panico.html")

    def test_tipo_invalido_cae_a_respuesta(self):
        ev = self._stream("Hola.\n" + MARCA + '\n{"tipo":"inventado"}', "cuéntame un chiste")
        self.assertEqual(ev["accion"][0]["tipo"], "respuesta")


class SinInternet(SimpleTestCase):
    """Modo feria / red caída: atajos y respuestas locales siguen funcionando, sin esperar timeouts."""

    def setUp(self):
        self.p = mock.patch("centinela.asistente.red.hay_internet", return_value=False)
        self.p.start()
        self.addCleanup(self.p.stop)

    def _post(self, mensaje):
        r = Client().post("/api/ia/asistente/stream/", json.dumps({"mensaje": mensaje}),
                          content_type="application/json")
        return b"".join(r.streaming_content).decode()

    def test_sos_y_navegacion_sin_internet(self):
        with mock.patch("httpx.stream", side_effect=AssertionError("red")),              mock.patch("httpx.post", side_effect=AssertionError("red")):
            self.assertIn('"activar_sos": true', self._post("auxilio"))
            self.assertIn('"destino": "eventos.html"', self._post("abre eventos"))

    def test_pregunta_libre_cae_a_respuesta_local_sin_llamar_proveedores(self):
        boom = mock.Mock(side_effect=AssertionError("no debe llamar proveedores remotos"))
        with mock.patch.dict(proveedores.PROVEEDORES, {"groq": boom, "gemini": boom, "claude": boom}):
            cuerpo = self._post("cuéntame un chiste")
        self.assertIn('"proveedor": "local"', cuerpo)
        self.assertIn('"sin_internet": true', cuerpo)
        self.assertIn("event: frase", cuerpo)

    def test_voz_y_whisper_avisan_sin_internet(self):
        from django.test import RequestFactory
        from . import views
        r = views.tts(RequestFactory().post("/api/ia/tts/", json.dumps({"texto": "hola"}),
                                            content_type="application/json"))
        self.assertEqual(r.status_code, 502)   # el navegador usa su propia voz al instante
        from . import voz
        with mock.patch.object(config, "key", return_value="x"):
            with self.assertRaises(ProveedorError):
                voz.transcribir(b"0" * 3000)   # el endpoint lo traduce a 502 -> el navegador usa su reconocimiento
