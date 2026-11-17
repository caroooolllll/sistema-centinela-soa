"""Pruebas de biometría. Correr:  python manage.py test biometria"""
import hashlib
import json
from datetime import timedelta
from unittest import mock

import numpy as np
from cryptography.fernet import Fernet
from django.db import connection
from django.test import Client, TestCase
from django.utils import timezone

from auth_app.models import PadronCasas, Sesion, Usuario
from centinela.asistente import feria

from . import consultas
from .models import BitacoraAcceso, PlantillaFacial, VisitaPendiente

KEY = Fernet.generate_key().decode()


def vec(semilla, ruido=0.0, base=None):
    """Vector de 128 valores. Misma `semilla` + poco ruido = 'misma persona'."""
    v = np.random.default_rng(semilla).normal(size=128)
    if base is not None:
        v = base
    if ruido:
        v = v + np.random.default_rng(semilla + 1000).normal(size=128) * ruido
    return v.tolist()


def post(c, url, datos, token=None):
    h = {'HTTP_AUTHORIZATION': f'Token {token}'} if token else {}
    return c.post(url, json.dumps(datos), content_type='application/json', **h)


class Base(TestCase):
    def setUp(self):
        p = mock.patch.dict('os.environ', {'BIOMETRIA_KEY': KEY, 'ASISTENTE_MODO_FERIA': 'false'})
        p.start()
        self.addCleanup(p.stop)
        self.c = Client()
        self.usuarios = {}
        for i, (nombre, email) in enumerate([('Ana Real', 'ana@email.com'), ('Beto Real', 'beto@email.com'),
                                             ('Admin', 'admin@centinela.com'),
                                             ('Dina Demo', 'dina@demo.centinela.local')]):
            casa = PadronCasas.objects.create(numero_casa=f'Casa {30 + i}', ocupada=True)
            u = Usuario.objects.create(nombre_completo=nombre, casa=casa, edad=30, email=email,
                                       password=hashlib.sha256(b'x').hexdigest())
            self.usuarios[email.split('@')[0]] = u

    def token(self, nombre, pendiente=False):
        t = f'tok-{nombre}'
        Sesion.objects.update_or_create(token=t, defaults=dict(
            usuario=self.usuarios[nombre], biometria_pendiente=pendiente, activa=True,
            fecha_expiracion=timezone.now() + timedelta(hours=1)))
        return t

    def registrar(self, nombre, vector, token=None):
        return post(self.c, '/api/biometria/registrar/',
                    {'vector': vector, 'consentimiento': True, 'liveness_ok': True}, token or self.token(nombre))


class Registro(Base):
    def test_requiere_consentimiento_y_prueba_de_vida(self):
        t = self.token('ana')
        r = post(self.c, '/api/biometria/registrar/', {'vector': vec(1), 'liveness_ok': True}, t)
        self.assertEqual(r.status_code, 400)
        r = post(self.c, '/api/biometria/registrar/', {'vector': vec(1), 'consentimiento': True}, t)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(PlantillaFacial.objects.count(), 0)

    def test_rechaza_vectores_invalidos(self):
        t = self.token('ana')
        for malo in ([1, 2, 3], 'hola', ['a'] * 128, [0] * 128):
            r = post(self.c, '/api/biometria/registrar/',
                     {'vector': malo, 'consentimiento': True, 'liveness_ok': True}, t)
            self.assertEqual(r.status_code, 400, str(malo)[:30])

    def test_sin_sesion_no_registra(self):
        r = post(self.c, '/api/biometria/registrar/', {'vector': vec(1), 'consentimiento': True, 'liveness_ok': True})
        self.assertEqual(r.status_code, 401)


class Cifrado(Base):
    def test_en_la_bd_nunca_hay_vector_en_claro(self):
        v = vec(7)
        self.assertEqual(self.registrar('ana', v).status_code, 200)
        with connection.cursor() as cur:
            cur.execute('SELECT vector_cifrado FROM biometria_plantilla')
            crudo = bytes(cur.fetchone()[0])
        normal = (np.asarray(v, dtype=np.float32) / np.linalg.norm(np.asarray(v, dtype=np.float32))).astype(np.float32)
        self.assertNotIn(normal.tobytes()[:32], crudo)           # ni siquiera un fragmento
        self.assertNotIn(np.asarray(v, dtype=np.float32).tobytes()[:32], crudo)
        self.assertTrue(crudo.startswith(b'gAAAA'))               # token Fernet
        self.assertNotIn(b'0.', crudo)

    def test_se_descifra_con_la_llave_correcta_y_no_con_otra(self):
        from .crypto import BiometriaKeyError, descifrar_vector
        v = vec(8)
        self.registrar('ana', v)
        blob = PlantillaFacial.objects.get().vector_cifrado
        self.assertAlmostEqual(float(np.linalg.norm(descifrar_vector(blob))), 1.0, places=4)
        with mock.patch.dict('os.environ', {'BIOMETRIA_KEY': Fernet.generate_key().decode()}):
            with self.assertRaises(BiometriaKeyError):
                descifrar_vector(blob)

    def test_sin_llave_falla_con_mensaje_claro(self):
        import logging
        logging.disable(logging.CRITICAL)      # (Django 5.0 + Python 3.14: el logger de 500 revienta en el cliente de pruebas)
        self.addCleanup(logging.disable, logging.NOTSET)
        t = self.token('ana')
        with mock.patch.dict('os.environ', {'BIOMETRIA_KEY': ''}):
            r = self.registrar('ana', vec(9), t)
        self.assertEqual(r.status_code, 500)
        self.assertIn('BIOMETRIA_KEY', r.json()['mensaje'])
        self.assertEqual(PlantillaFacial.objects.count(), 0)


class Verificacion(Base):
    def setUp(self):
        super().setUp()
        self.registrar('ana', vec(1))

    def test_misma_persona_coincide_y_otra_no(self):
        t = self.token('ana')
        ok = post(self.c, '/api/biometria/verificar/', {'vector': vec(1, 0.03), 'liveness_ok': True, 'origen': 'accion_critica'}, t).json()
        self.assertTrue(ok['coincide'])
        otra = post(self.c, '/api/biometria/verificar/', {'vector': vec(2), 'liveness_ok': True}, t).json()
        self.assertFalse(otra['coincide'])

    def test_sin_prueba_de_vida_se_rechaza_y_queda_en_bitacora(self):
        r = post(self.c, '/api/biometria/verificar/', {'vector': vec(1)}, self.token('ana'))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(BitacoraAcceso.objects.filter(evento='verificacion', resultado='denegado').exists())

    def test_sin_plantilla_404(self):
        r = post(self.c, '/api/biometria/verificar/', {'vector': vec(1), 'liveness_ok': True}, self.token('beto'))
        self.assertEqual(r.status_code, 404)

    def test_segundo_factor_en_login(self):
        """Con rostro registrado la sesión queda pendiente: ni el servicio de verificación la acepta."""
        xml = '<loginRequest><email>ana@email.com</email><password>x</password></loginRequest>'
        r = self.c.post('/auth/login', xml, content_type='application/xml')
        self.assertIn(b'<biometriaPendiente>true</biometriaPendiente>', r.content)
        token = Sesion.objects.filter(usuario=self.usuarios['ana']).latest('id').token
        h = {'HTTP_AUTHORIZATION': f'Token {token}'}
        self.assertEqual(self.c.get('/auth/verificar-token', **h).status_code, 401)   # bloqueada
        # una cara equivocada NO la libera
        post(self.c, '/api/biometria/verificar/', {'vector': vec(5), 'liveness_ok': True, 'origen': 'login'}, token)
        self.assertEqual(self.c.get('/auth/verificar-token', **h).status_code, 401)
        # la correcta sí
        post(self.c, '/api/biometria/verificar/', {'vector': vec(1, 0.02), 'liveness_ok': True, 'origen': 'login'}, token)
        self.assertEqual(self.c.get('/auth/verificar-token', **h).status_code, 200)

    def test_login_sin_rostro_no_cambia(self):
        xml = '<loginRequest><email>beto@email.com</email><password>x</password></loginRequest>'
        r = self.c.post('/auth/login', xml, content_type='application/xml')
        self.assertIn(b'<biometriaPendiente>false</biometriaPendiente>', r.content)


class Identificacion(Base):
    def setUp(self):
        super().setUp()
        self.registrar('ana', vec(1))
        self.registrar('beto', vec(2))
        self.t = self.token('admin')

    def ident(self, v, vida=True):
        return post(self.c, '/api/biometria/identificar/', {'vector': v, 'liveness_ok': vida}, self.t)

    def test_reconoce_y_registra_acceso(self):
        r = self.ident(vec(2, 0.03)).json()
        self.assertTrue(r['reconocido'])
        self.assertEqual((r['nombre'], r['casa']), ('Beto Real', 'Casa 31'))
        b = BitacoraAcceso.objects.get(evento='acceso')
        self.assertEqual((b.resultado, b.origen, b.nombre), ('ok', 'porton', 'Beto Real'))

    def test_visitante_no_registrado_crea_visita_y_no_abre(self):
        r = self.ident(vec(99)).json()
        self.assertFalse(r['reconocido'])
        self.assertIn('Caseta', r['notificados'])
        self.assertEqual(VisitaPendiente.objects.filter(estado='pendiente').count(), 1)
        self.assertTrue(BitacoraAcceso.objects.filter(evento='acceso', resultado='denegado').exists())
        self.assertTrue(BitacoraAcceso.objects.filter(evento='visita', resultado='pendiente').exists())

    def test_sin_prueba_de_vida_nunca_abre(self):
        self.assertEqual(self.ident(vec(2), vida=False).status_code, 403)
        self.assertFalse(BitacoraAcceso.objects.filter(evento='acceso', resultado='ok').exists())

    def test_ambiguo_entre_dos_vecinos_no_abre(self):
        a = np.random.default_rng(1).normal(size=128)
        casi = a + np.random.default_rng(5).normal(size=128) * 0.05     # un "gemelo" casi igual
        PlantillaFacial.objects.all().delete()
        self.registrar('ana', a.tolist())
        self.registrar('beto', casi.tolist())
        self.assertFalse(self.ident(a.tolist()).json()['reconocido'])

    def test_exige_sesion_fuera_de_modo_feria(self):
        r = post(self.c, '/api/biometria/identificar/', {'vector': vec(2), 'liveness_ok': True})
        self.assertEqual(r.status_code, 401)
        with mock.patch.object(feria, 'activo', return_value=True):
            r = post(self.c, '/api/biometria/identificar/', {'vector': vec(2), 'liveness_ok': True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(BitacoraAcceso.objects.filter(evento='acceso', es_demo=True).exists())


class Borrado(Base):
    def test_borrar_elimina_la_plantilla_y_queda_en_bitacora(self):
        t = self.token('ana')
        self.registrar('ana', vec(1), t)
        r = post(self.c, '/api/biometria/borrar/', {}, t).json()
        self.assertTrue(r['borrada'])
        self.assertEqual(PlantillaFacial.objects.count(), 0)
        with connection.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM biometria_plantilla')
            self.assertEqual(cur.fetchone()[0], 0)
        self.assertTrue(BitacoraAcceso.objects.filter(evento='borrado', resultado='ok').exists())
        self.assertFalse(post(self.c, '/api/biometria/borrar/', {}, t).json()['borrada'])
        self.assertFalse(self.c.get('/api/biometria/estado/', HTTP_AUTHORIZATION=f'Token {t}').json()['registrada'])

    def test_no_puedo_borrar_la_de_otro(self):
        self.registrar('ana', vec(1))
        post(self.c, '/api/biometria/borrar/', {}, self.token('beto'))
        self.assertEqual(PlantillaFacial.objects.count(), 1)


class Bitacora(Base):
    def test_cada_evento_deja_rastro(self):
        t = self.token('ana')
        self.registrar('ana', vec(1), t)
        post(self.c, '/api/biometria/verificar/', {'vector': vec(1), 'liveness_ok': True}, t)
        post(self.c, '/api/biometria/verificar/', {'vector': vec(3), 'liveness_ok': True}, t)
        post(self.c, '/api/biometria/borrar/', {}, t)
        eventos = list(BitacoraAcceso.objects.order_by('id').values_list('evento', 'resultado'))
        self.assertEqual(eventos, [('registro', 'ok'), ('verificacion', 'ok'), ('verificacion', 'denegado'),
                                   ('borrado', 'ok')])
        b = BitacoraAcceso.objects.first()
        self.assertTrue(b.fecha and b.nombre == 'Ana Real' and b.origen)

    def test_roles_un_vecino_solo_ve_lo_suyo(self):
        ta, tb, tad = self.token('ana'), self.token('beto'), self.token('admin')
        self.registrar('ana', vec(1), ta)
        self.registrar('beto', vec(2), tb)
        url = '/api/biometria/bitacora/'
        ver = lambda t: {i['nombre'] for i in self.c.get(url, HTTP_AUTHORIZATION=f'Token {t}').json()['items']}
        self.assertEqual(ver(ta), {'Ana Real'})
        self.assertEqual(ver(tad), {'Ana Real', 'Beto Real'})
        self.assertEqual(self.c.get(url).status_code, 401)

    def test_la_bitacora_no_contiene_vectores(self):
        t = self.token('ana')
        self.registrar('ana', vec(1), t)
        txt = self.c.get('/api/biometria/bitacora/', HTTP_AUTHORIZATION=f'Token {t}').content.decode()
        self.assertNotIn('vector', txt)


class ModoFeria(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(feria, 'activo', return_value=True)
        p.start()
        self.addCleanup(p.stop)
        self.dina = self.usuarios['dina']

    def test_registro_demo_exige_consentimiento_y_solo_usuarios_demo(self):
        base = {'usuario_id': self.dina.id, 'vector': vec(4), 'liveness_ok': True}
        self.assertEqual(post(self.c, '/api/biometria/feria/registrar/', base).status_code, 400)
        r = post(self.c, '/api/biometria/feria/registrar/', {**base, 'consentimiento': True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(PlantillaFacial.objects.get().es_demo)
        real = {**base, 'usuario_id': self.usuarios['ana'].id, 'consentimiento': True}
        self.assertEqual(post(self.c, '/api/biometria/feria/registrar/', real).status_code, 404)

    def test_borrar_todo_lo_demo_respeta_lo_real(self):
        self.registrar('ana', vec(1))                                    # real
        post(self.c, '/api/biometria/feria/registrar/',
             {'usuario_id': self.dina.id, 'vector': vec(4), 'consentimiento': True, 'liveness_ok': True})
        post(self.c, '/api/biometria/identificar/', {'vector': vec(77), 'liveness_ok': True})   # visita demo
        r = post(self.c, '/api/biometria/feria/borrar-demo/', {}).json()
        self.assertGreaterEqual(r['borrado']['plantillas'], 1)
        self.assertEqual(PlantillaFacial.objects.filter(es_demo=True).count(), 0)
        self.assertEqual(VisitaPendiente.objects.filter(es_demo=True).count(), 0)
        self.assertEqual(BitacoraAcceso.objects.filter(es_demo=True).count(), 0)
        self.assertEqual(PlantillaFacial.objects.filter(usuario=self.usuarios['ana']).count(), 1)  # lo real sigue

    def test_fuera_de_modo_feria_esta_apagado(self):
        with mock.patch.object(feria, 'activo', return_value=False):
            self.assertEqual(post(self.c, '/api/biometria/feria/borrar-demo/', {}).status_code, 403)
            self.assertEqual(self.c.get('/api/biometria/feria/vecinos/').status_code, 403)

    def test_omitir_libera_sesion_pendiente_solo_en_feria(self):
        t = self.token('ana', pendiente=True)
        self.assertEqual(post(self.c, '/api/biometria/omitir/', {}, t).status_code, 200)
        self.assertFalse(Sesion.objects.get(token=t).biometria_pendiente)


class Asistente(Base):
    """'¿Quién entró hoy?' lee la bitácora respetando el rol."""

    def setUp(self):
        super().setUp()
        BitacoraAcceso.objects.create(usuario=self.usuarios['ana'], nombre='Ana Real', casa='Casa 30',
                                      evento='acceso', resultado='ok', origen='porton')
        VisitaPendiente.objects.create(notificados='Caseta')

    def test_admin_ve_todo(self):
        r = consultas.responder_bitacora('Centinela, ¿quién entró hoy?', self.usuarios['admin'])
        self.assertIn('Ana Real de Casa 30', r)
        r = consultas.responder_bitacora('¿hubo visitantes no registrados?', self.usuarios['admin'])
        self.assertIn('1 visitante', r)

    def test_vecino_solo_lo_suyo_y_no_ve_visitantes(self):
        r = consultas.responder_bitacora('quién entró hoy', self.usuarios['beto'])
        self.assertIn('no tienes accesos', r)
        r = consultas.responder_bitacora('quién entró hoy', self.usuarios['ana'])
        self.assertIn('tuviste 1 acceso', r)
        r = consultas.responder_bitacora('hubo visitantes no registrados', self.usuarios['ana'])
        self.assertIn('solo la ve el administrador', r)

    def test_sin_sesion_pide_iniciar(self):
        self.assertIn('inicies sesión', consultas.responder_bitacora('quién entró hoy', None))

    def test_otras_preguntas_no_se_interceptan(self):
        self.assertIsNone(consultas.responder_bitacora('qué eventos hay esta semana', self.usuarios['admin']))

    def test_por_el_endpoint_del_asistente_sin_llm(self):
        t = self.token('admin')
        with mock.patch('centinela.asistente.proveedores.Cadena', side_effect=AssertionError('no LLM')):
            r = self.c.post('/api/ia/asistente/stream/', json.dumps({'mensaje': 'quién entró hoy'}),
                            content_type='application/json', HTTP_AUTHORIZATION=f'Token {t}')
            cuerpo = b''.join(r.streaming_content).decode()
        self.assertIn('Ana Real', cuerpo)
        self.assertIn('"proveedor": "bitacora"', cuerpo)
