from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import json
import os
import sqlite3
import requests
from datetime import datetime
from urllib.parse import unquote

from manager import manager

app = FastAPI(title="Chat API", description="Servicio de mensajería en tiempo real — Centinela")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CENTINELA_URL = os.getenv("CENTINELA_URL", "http://localhost:9000")
DB_PATH = "chat.db"

# ── Base de Datos SQLite ──────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sala         TEXT NOT NULL DEFAULT 'general',
            remitente    TEXT NOT NULL,
            destinatario TEXT,
            contenido    TEXT NOT NULL,
            timestamp    TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    print("[Chat] Base de datos inicializada OK")

def guardar_mensaje(sala: str, remitente: str, contenido: str, destinatario: str = None):
    conn = get_db()
    conn.execute(
        "INSERT INTO mensajes (sala, remitente, destinatario, contenido, timestamp) VALUES (?,?,?,?,?)",
        (sala, remitente, destinatario, contenido, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def obtener_historial(sala: str = "general", limite: int = 50):
    conn = get_db()
    rows = conn.execute(
        """SELECT remitente, contenido, timestamp, destinatario
           FROM mensajes WHERE sala = ? AND destinatario IS NULL
           ORDER BY id DESC LIMIT ?""",
        (sala, limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def obtener_historial_privado(user1: str, user2: str, limite: int = 50):
    conn = get_db()
    rows = conn.execute(
        """SELECT remitente, contenido, timestamp
           FROM mensajes
           WHERE (remitente=? AND destinatario=?) OR (remitente=? AND destinatario=?)
           ORDER BY id DESC LIMIT ?""",
        (user1, user2, user2, user1, limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

# Inicializar BD al arrancar
init_db()

# ── Verificar token con Centinela ─────────────────────────
def verificar_token_centinela(token: str) -> dict | None:
    try:
        print(f"[Chat] Verificando token: {token[:20]}...")
        r = requests.get(
            f"{CENTINELA_URL}/auth/verificar-token",
            headers={"Authorization": f"Token {token}"},
            timeout=5
        )
        datos = r.json()
        print(f"[Chat] Django respondió: {datos}")
        if datos.get("valido"):
            return datos.get("usuario")
        print(f"[Chat] Token rechazado: {datos.get('mensaje', 'sin mensaje')}")
        return None
    except Exception as e:
        print(f"[Chat] Error al verificar token: {e}")
        return None

# ── Modelo REST ───────────────────────────────────────────
class MessagePayload(BaseModel):
    to: Optional[str] = None
    content: str
    from_user: str

# ── WebSocket ─────────────────────────────────────────────
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...)
):
    user_id_clean = unquote(user_id)
    print(f"[WS] ↓ Conexión entrante: user_id={user_id_clean!r} token={token[:20] if token else 'None'}...")

    usuario = verificar_token_centinela(token)
    if not usuario:
        print("[WS] Token inválido/expirado → cerrando con 1008")
        await websocket.accept()
        await websocket.close(code=1008)
        return

    print(f"[WS] Token OK: nombre={usuario.get('nombre')!r} casa={usuario.get('casa')!r}")

    nombre_real = usuario.get("nombre") or user_id_clean
    casa = usuario.get("casa") or ""
    identificador = f"{nombre_real} ({casa})" if casa else nombre_real
    print(f"[WS] identificador={identificador!r}")

    try:
        await manager.connect(websocket, identificador)  # llama websocket.accept() internamente
    except Exception as exc:
        print(f"[WS] ERROR al hacer accept: {type(exc).__name__}: {exc}")
        try:
            await websocket.accept()
            await websocket.close(code=1011)
        except Exception as inner:
            print(f"[WS] No se pudo cerrar limpio: {inner}")
        return

    print(f"[WS] accept OK — identificador: {identificador!r}")

    print("[WS] enviando historial")
    historial = obtener_historial("general", 30)
    await websocket.send_text(json.dumps({
        "type": "historial",
        "mensajes": historial
    }))
    print(f"[WS] historial enviado ({len(historial)} msgs)")

    try:
        await manager.broadcast(json.dumps({
            "type": "system",
            "action": "user_joined",
            "user": identificador
        }))
        print("[WS] esperando mensajes...")

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                content = msg.get("content", "")
                target = msg.get("to", None)
                ts = datetime.now().strftime("%H:%M")

                if target:
                    print(f"[DM] {identificador!r} → {target!r}: '{content[:80]}'")
                    guardar_mensaje("privado", identificador, content, target)
                    entregado = await manager.send_personal(target, json.dumps({
                        "type": "private", "from": identificador,
                        "content": content, "timestamp": ts
                    }))
                    print(f"[DM] entregado en tiempo real: {'SÍ' if entregado else 'NO (offline, guardado en DB)'}")
                    await manager.send_personal(identificador, json.dumps({
                        "type": "private_sent", "to": target, "content": content, "timestamp": ts
                    }))
                else:
                    guardar_mensaje("general", identificador, content)
                    await websocket.send_text(json.dumps({
                        "type": "chat", "from": identificador,
                        "content": content, "timestamp": ts
                    }))
                    await manager.broadcast_except(json.dumps({
                        "type": "chat", "from": identificador,
                        "content": content, "timestamp": ts
                    }), websocket)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, identificador)
        await manager.broadcast(json.dumps({
            "type": "system", "action": "user_left", "user": identificador
        }))

# ── Historial REST ────────────────────────────────────────
@app.get("/historial/{sala}")
async def get_historial(sala: str, limite: int = 50):
    return obtener_historial(sala, limite)

@app.get("/historial-privado")
async def get_historial_privado(user1: str, user2: str, limite: int = 50):
    return obtener_historial_privado(user1, user2, limite)

# ── Send REST ─────────────────────────────────────────────
@app.post("/send")
async def send_message(payload: MessagePayload, token: str = Query(...)):
    usuario = verificar_token_centinela(token)
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if payload.to:
        guardar_mensaje("privado", payload.from_user, payload.content, payload.to)
        await manager.send_personal(payload.to, json.dumps({
            "type": "private", "from": payload.from_user, "content": payload.content
        }))
    else:
        guardar_mensaje("general", payload.from_user, payload.content)
        await manager.broadcast(json.dumps({
            "type": "chat", "from": payload.from_user, "content": payload.content
        }))
    return {"status": "sent"}

# ── Users / Health ────────────────────────────────────────
@app.get("/users")
async def get_connected_users():
    return {"users": list(manager.active_connections.keys())}

@app.get("/health")
async def health():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM mensajes").fetchone()[0]
    conn.close()
    return {"status": "ok", "servicio": "chat", "puerto": 9003, "mensajes_guardados": total}

@app.get("/chat-component", response_class=HTMLResponse)
async def get_chat_component():
    with open("chat_component.html", "r", encoding="utf-8") as f:
        return f.read()


# ── Emergencia — push HTTP ────────────────────────────────────────────────────

class EmergenciaPushPayload(BaseModel):
    victim_id: int
    lat:       float
    lng:       float
    nombre:    str = ""
    timestamp: str = ""


@app.post("/push-emergencia")
async def push_emergencia(payload: EmergenciaPushPayload):
    """
    Endpoint interno — Django lo llama para retransmitir la ubicación GPS
    a todos los WebSockets conectados al canal de emergencia del victim_id.
    """
    msg = json.dumps({
        "type":      "location_update",
        "victim_id": payload.victim_id,
        "nombre":    payload.nombre,
        "lat":       payload.lat,
        "lng":       payload.lng,
        "timestamp": payload.timestamp,
    })
    await manager.push_emergencia(str(payload.victim_id), msg)
    return {
        "status":   "pushed",
        "watchers": manager.watchers_count(str(payload.victim_id)),
    }


@app.websocket("/ws/emergencia/{victim_id}")
async def ws_emergencia(
    websocket: WebSocket,
    victim_id: int,
    token: str = Query(...)
):
    """
    Canal de emergencia en tiempo real.
    Los contactos se conectan aquí para recibir actualizaciones de ubicación de la víctima.
    """
    usuario = verificar_token_centinela(token)
    if not usuario:
        await websocket.accept()
        await websocket.close(code=1008)
        return

    vid = str(victim_id)
    await manager.connect_emergency(websocket, vid)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_emergency(websocket, vid)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("CHAT_HOST", "0.0.0.0"),
        port=int(os.getenv("CHAT_PORT", "9003")),
        reload=os.getenv("CHAT_RELOAD", "false").lower() == "true",
    )
