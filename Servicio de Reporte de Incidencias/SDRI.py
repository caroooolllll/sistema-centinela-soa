from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import sqlite3
import xml.etree.ElementTree as ET
from datetime import date, timedelta

app = Flask(__name__)
CORS(app)

DB_NAME = 'reporteincidencia.db'


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS incidencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            fecha TEXT,
            hora TEXT,
            prioridad TEXT,
            categoria TEXT DEFAULT 'General',
            latitud TEXT,
            longitud TEXT,
            imagenes TEXT,
            estado TEXT DEFAULT 'Abierto'
        )
        '''
    )
    cursor.execute("PRAGMA table_info(incidencias)")
    columnas = {row[1] for row in cursor.fetchall()}
    if 'categoria' not in columnas:
        cursor.execute("ALTER TABLE incidencias ADD COLUMN categoria TEXT DEFAULT 'General'")
    if 'tipo' not in columnas:
        cursor.execute("ALTER TABLE incidencias ADD COLUMN tipo TEXT DEFAULT 'General'")
        # Migración: mueve valor de categoria antigua a tipo, normaliza categoria a 'seguridad'
        cursor.execute("""
            UPDATE incidencias
            SET tipo = CASE WHEN categoria NOT IN ('seguridad', 'ambiental') THEN categoria ELSE 'General' END,
                categoria = 'seguridad'
            WHERE categoria NOT IN ('seguridad', 'ambiental')
        """)
    conn.commit()
    conn.close()


def xml_response(root_name, estado='OK', mensaje=''):
    response = ET.Element(root_name)
    ET.SubElement(response, 'estado').text = estado
    if mensaje:
        ET.SubElement(response, 'mensaje').text = mensaje
    return response


@app.route('/api/reportar_incidencia', methods=['POST'])
def reportar_incidencia():
    try:
        root = ET.fromstring(request.data)
        usuario = root.findtext('usuario', '')
        descripcion = root.findtext('descripcion', '')
        fecha = root.findtext('fecha', '')
        hora = root.findtext('hora', '')
        prioridad = root.findtext('prioridad', 'Baja')
        categoria = root.findtext('categoria', 'seguridad')
        if categoria not in ('seguridad', 'ambiental'):
            categoria = 'seguridad'
        tipo = root.findtext('tipo', 'General')
        latitud = root.findtext('latitud', '')
        longitud = root.findtext('longitud', '')
        imagenes = root.findtext('imagenes', '[]')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO incidencias (usuario, descripcion, fecha, hora, prioridad, categoria, tipo, latitud, longitud, imagenes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario, descripcion, fecha, hora, prioridad, categoria, tipo, latitud, longitud, imagenes),
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
        conn.close()
        # Bandeja inteligente (Centinela): triage automático. Nunca debe afectar la respuesta del SDRI.
        try:
            import threading, requests
            carga = dict(sdri_id=nuevo_id, usuario=usuario, descripcion=descripcion, prioridad=prioridad,
                         categoria=categoria, tipo=tipo, latitud=latitud, longitud=longitud)
            threading.Thread(target=lambda: requests.post('http://127.0.0.1:9000/api/auto/incidentes/ingresar/',
                                                          json=carga, timeout=3), daemon=True).start()
        except Exception:
            pass
        response = xml_response('reporteResponse', 'OK', f'Incidencia {nuevo_id} creada')
        status_code = 201
    except Exception as e:
        response = xml_response('reporteResponse', 'ERROR', str(e))
        status_code = 500

    return Response(ET.tostring(response), status=status_code, mimetype='application/xml')


@app.route('/api/consultar_incidencias', methods=['GET'])
def consultar_incidencias():
    rol = request.args.get('rol', 'usuario')
    usuario_filtro = request.args.get('usuario', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    if usuario_filtro:
        cursor.execute(
            "SELECT * FROM incidencias WHERE LOWER(usuario) = LOWER(?) AND estado != 'Eliminado' ORDER BY id DESC",
            (usuario_filtro,)
        )
    elif rol == 'admin':
        cursor.execute("SELECT * FROM incidencias ORDER BY id DESC")
    else:
        cursor.execute("SELECT * FROM incidencias WHERE estado != 'Eliminado' ORDER BY id DESC")
    incidencias = cursor.fetchall()
    conn.close()

    root = ET.Element('listaIncidencias')
    for row in incidencias:
        item = ET.SubElement(root, 'incidencia')
        ET.SubElement(item, 'id').text = str(row['id'])
        ET.SubElement(item, 'usuario').text = str(row['usuario'])
        ET.SubElement(item, 'descripcion').text = str(row['descripcion'])
        ET.SubElement(item, 'fecha').text = str(row['fecha'] or '')
        ET.SubElement(item, 'hora').text = str(row['hora'] or '')
        ET.SubElement(item, 'prioridad').text = str(row['prioridad'] or 'Baja')
        ET.SubElement(item, 'categoria').text = str(row['categoria'] or 'seguridad')
        ET.SubElement(item, 'tipo').text = str(row['tipo'] or 'General')
        ET.SubElement(item, 'estado').text = str(row['estado'] or 'Abierto')
        ET.SubElement(item, 'latitud').text = str(row['latitud'] or '')
        ET.SubElement(item, 'longitud').text = str(row['longitud'] or '')
        ET.SubElement(item, 'imagenes').text = str(row['imagenes'] or '[]')

    return Response(ET.tostring(root), status=200, mimetype='application/xml')


@app.route('/api/eliminar_incidencia', methods=['POST', 'DELETE'])
def eliminar_incidencia():
    try:
        root = ET.fromstring(request.data)
        id_incidencia = root.findtext('id', '')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE incidencias SET estado = 'Eliminado' WHERE id = ?", (id_incidencia,))
        conn.commit()
        conn.close()
        response = xml_response('eliminarResponse')
    except Exception:
        response = xml_response('eliminarResponse', 'ERROR')
    return Response(ET.tostring(response), status=200, mimetype='application/xml')


@app.route('/api/reactivar_incidencia', methods=['POST'])
def reactivar_incidencia():
    try:
        root = ET.fromstring(request.data)
        id_incidencia = root.findtext('id', '')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE incidencias SET estado = 'Abierto' WHERE id = ?", (id_incidencia,))
        conn.commit()
        conn.close()
        response = xml_response('reactivarResponse')
    except Exception:
        response = xml_response('reactivarResponse', 'ERROR')
    return Response(ET.tostring(response), status=200, mimetype='application/xml')


@app.route('/api/editar_incidencia', methods=['POST'])
def editar_incidencia():
    try:
        root = ET.fromstring(request.data)
        id_incidencia = root.findtext('id', '')
        descripcion = root.findtext('descripcion', '')
        hora = root.findtext('hora', '')
        prioridad = root.findtext('prioridad', 'Baja')
        categoria = root.findtext('categoria', 'seguridad')
        if categoria not in ('seguridad', 'ambiental'):
            categoria = 'seguridad'
        tipo = root.findtext('tipo', 'General')
        latitud = root.findtext('latitud', '')
        longitud = root.findtext('longitud', '')
        imagenes = root.findtext('imagenes', '[]')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE incidencias
            SET descripcion = ?, hora = ?, prioridad = ?, categoria = ?, tipo = ?, latitud = ?, longitud = ?, imagenes = ?
            WHERE id = ?
            """,
            (descripcion, hora, prioridad, categoria, tipo, latitud, longitud, imagenes, id_incidencia),
        )
        conn.commit()
        conn.close()
        response = xml_response('editarResponse')
    except Exception:
        response = xml_response('editarResponse', 'ERROR')
    return Response(ET.tostring(response), status=200, mimetype='application/xml')


def _normalizar_categorias(conn):
    """Normaliza valores legacy de categoria a 'seguridad' o 'ambiental'."""
    conn.execute("""
        UPDATE incidencias
        SET tipo = CASE WHEN tipo IS NULL OR tipo = '' THEN categoria ELSE tipo END,
            categoria = CASE WHEN LOWER(categoria) = 'ambiental' THEN 'ambiental' ELSE 'seguridad' END
        WHERE categoria NOT IN ('seguridad', 'ambiental')
    """)
    conn.commit()


@app.route('/incidencias/count', methods=['GET'])
def contar_incidencias():
    conn = get_db_connection()
    _normalizar_categorias(conn)
    total = conn.execute(
        "SELECT COUNT(*) AS total FROM incidencias WHERE estado != 'Eliminado'"
    ).fetchone()['total']
    ambiental = conn.execute(
        "SELECT COUNT(*) AS total FROM incidencias WHERE estado != 'Eliminado' AND categoria = 'ambiental'"
    ).fetchone()['total']
    conn.close()
    return jsonify({"total": total, "ambiental": ambiental})


@app.route('/incidencias/por-semana', methods=['GET'])
def incidencias_por_semana():
    try:
        semanas = max(1, min(52, int(request.args.get('semanas', 8))))
    except (ValueError, TypeError):
        semanas = 8

    conn = get_db_connection()
    _normalizar_categorias(conn)

    rows = conn.execute("""
        SELECT
            strftime('%Y-W%W', fecha) AS semana,
            COUNT(*) AS total,
            SUM(CASE WHEN categoria = 'ambiental' THEN 1 ELSE 0 END) AS ambiental,
            SUM(CASE WHEN categoria = 'seguridad' THEN 1 ELSE 0 END) AS seguridad
        FROM incidencias
        WHERE estado != 'Eliminado'
          AND fecha IS NOT NULL AND fecha != ''
          AND length(fecha) >= 8
        GROUP BY strftime('%Y-W%W', fecha)
        ORDER BY semana ASC
    """).fetchall()
    conn.close()

    today = date.today()
    week_keys = [
        (today - timedelta(weeks=i)).strftime('%Y-W%W')
        for i in range(semanas - 1, -1, -1)
    ]

    data_by_week = {r['semana']: r for r in rows}
    result = []
    for wk in week_keys:
        r = data_by_week.get(wk)
        result.append({
            'semana': wk,
            'total': int(r['total']) if r else 0,
            'ambiental': int(r['ambiental']) if r else 0,
            'seguridad': int(r['seguridad']) if r else 0,
        })

    return jsonify(result)


if __name__ == '__main__':
    init_db()
    app.run(debug=False, host="0.0.0.0", port=9001)
