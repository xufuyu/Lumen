"""Real-time sync: broadcast data changes to all clients sharing the same user_id.

Clients connect via WebSocket /api/ws/sync?user_id=xxx.
When any data mutation occurs, the server sends {"type":"refresh"} to all
connected clients with the same user_id, prompting them to reload their data.
"""

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ws", tags=["sync"])

# user_id → set of connected WebSockets
_connections: dict[str, set[WebSocket]] = defaultdict(set)


@router.websocket("/sync")
async def sync_websocket(ws: WebSocket, user_id: str = Query(default="default")):
    """WebSocket endpoint for real-time data sync notifications.

    Clients connect with their user_id. When a mutation happens on the same
    user_id, the server broadcasts a refresh signal.
    """
    await ws.accept()
    uid = user_id.strip() or "default"
    _connections[uid].add(ws)
    logger.info(f"[sync] {uid} connected ({len(_connections[uid])} clients)")

    try:
        # Keep connection alive, handle incoming pings
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=120)
                if data == "ping":
                    await ws.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive
                try:
                    await ws.send_text(json.dumps({"type": "keepalive"}))
                except Exception:
                    break
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _connections[uid].discard(ws)
        if not _connections[uid]:
            del _connections[uid]
        logger.info(f"[sync] {uid} disconnected ({len(_connections.get(uid, set()))} clients)")


async def notify_user(user_id: str, event: str = "refresh"):
    """Send a notification to all connected clients with the given user_id.

    Call this after any data mutation (create/update/delete record, task, event, etc.)
    """
    clients = _connections.get(user_id, set())
    if not clients:
        return
    msg = json.dumps({"type": event})
    dead = []
    for ws in clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)
