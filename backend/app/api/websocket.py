from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database import SessionLocal
from app.models.admin import Admin
from app.services.websocket_service import manager
from app.utils.security import decode_access_token

router = APIRouter(tags=["WebSocket"])


def _valid_admin_token(token: str | None) -> bool:
    payload = decode_access_token(token) if token else None
    if not payload or "sub" not in payload:
        return False
    db = SessionLocal()
    try:
        return db.query(Admin).filter(Admin.username == payload["sub"], Admin.is_active == True).first() is not None
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    """Live dashboard feed. Requires the admin JWT as ``?token=``."""
    if not _valid_admin_token(token):
        await websocket.close(code=1008)  # policy violation
        return
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
