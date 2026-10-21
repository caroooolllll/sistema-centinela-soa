from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Chat: keyed by user identifier string ("Nombre (Casa)")
        self.active_connections: Dict[str, WebSocket] = {}
        self.active_sockets: Set[WebSocket] = set()
        # Emergencia: keyed by victim_id (str) → set de WebSockets observadores
        self.emergency_watchers: Dict[str, Set[WebSocket]] = {}

    # ── Chat ──────────────────────────────────────────────────────────────────
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.active_sockets.add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        self.active_sockets.discard(websocket)

    async def broadcast(self, message: str):
        dead = []
        for ws in list(self.active_sockets):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_sockets.discard(ws)

    async def broadcast_except(self, message: str, excluded: WebSocket):
        dead = []
        for ws in list(self.active_sockets):
            if ws is excluded:
                continue
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_sockets.discard(ws)

    async def send_personal(self, user_id: str, message: str) -> bool:
        ws = self.active_connections.get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_text(message)
            return True
        except Exception as e:
            print(f"[WS] send_personal({user_id!r}) — conexión muerta, eliminando: {e}")
            self.active_connections.pop(user_id, None)
            self.active_sockets.discard(ws)
            return False

    # ── Emergency channels ────────────────────────────────────────────────────
    async def connect_emergency(self, websocket: WebSocket, victim_id: str):
        await websocket.accept()
        if victim_id not in self.emergency_watchers:
            self.emergency_watchers[victim_id] = set()
        self.emergency_watchers[victim_id].add(websocket)

    def disconnect_emergency(self, websocket: WebSocket, victim_id: str):
        watchers = self.emergency_watchers.get(victim_id, set())
        watchers.discard(websocket)
        if not watchers:
            self.emergency_watchers.pop(victim_id, None)

    async def push_emergencia(self, victim_id: str, message: str):
        watchers = set(self.emergency_watchers.get(victim_id, set()))
        dead = set()
        for ws in watchers:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        living = self.emergency_watchers.get(victim_id, set())
        for ws in dead:
            living.discard(ws)

    def watchers_count(self, victim_id: str) -> int:
        return len(self.emergency_watchers.get(victim_id, set()))


# Instancia global compartida por main.py
manager = ConnectionManager()
