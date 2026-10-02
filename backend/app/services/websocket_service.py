import logging
from typing import List
from fastapi import WebSocket

logger = logging.getLogger("websocket_service")

class ConnectionManager:
    """Real-time WebSocket PubSub Manager for Admin Dashboard clients."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast_event(self, event_type: str, payload: dict):
        """Broadcast event to all connected admin UI clients."""
        if not self.active_connections:
            return

        message = {
            "type": event_type,
            "data": payload
        }
        
        disconnected_clients = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WS client: {str(e)}")
                disconnected_clients.append(connection)

        for client in disconnected_clients:
            self.disconnect(client)

manager = ConnectionManager()
