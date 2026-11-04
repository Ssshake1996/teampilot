import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str, accepted: bool = False):
        if not accepted:
            await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info(f"User {user_id} connected. Total connections: {self._total()}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"User {user_id} disconnected. Total connections: {self._total()}")

    async def send_to_user(self, user_id: str, data: dict):
        for ws in list(self.active_connections.get(user_id, set())):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(ws, user_id)

    async def broadcast(self, data: dict):
        project_id = data.get("data", {}).get("project_id")
        if project_id and self.active_connections:
            import uuid
            from app.database import async_session
            from app.models.user import User
            from app.services.project_access_service import get_visible_project_ids
            async with async_session() as db:
                for user_id in list(self.active_connections):
                    user = await db.get(User, uuid.UUID(user_id))
                    if user and user.is_active and uuid.UUID(str(project_id)) in await get_visible_project_ids(db, user):
                        await self.send_to_user(user_id, data)
            return
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, data)

    def _total(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())


manager = ConnectionManager()
