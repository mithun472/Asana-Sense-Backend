"""
routes/live_ops.py

Serves the ops dashboard page and its WebSocket feed.
Add this file to your routes/ folder and register it in routes/__init__.py
the same way the other routers are registered:

    from .live_ops import router as live_ops_router
    app.include_router(live_ops_router)

Then place dashboard.html and asana_sense_logo.png next to wherever
DASHBOARD_DIR below points (defaults to backend project root).
"""

import os
import secrets
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from live_feed import live_feed

router = APIRouter(tags=["Ops Dashboard"])

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend project root

# Set OPS_KEY in .env. Open the dashboard as  /ops?key=<OPS_KEY>
# If OPS_KEY is unset the dashboard and feed are DISABLED (fail closed).
OPS_KEY = os.getenv("OPS_KEY", "")


def _key_ok(key: str) -> bool:
    return bool(OPS_KEY) and secrets.compare_digest(key or "", OPS_KEY)


@router.get("/ops")
async def ops_dashboard(key: str = Query("")):
    """Serve the live ops dashboard page."""
    if not _key_ok(key):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(os.path.join(DASHBOARD_DIR, "dashboard.html"))


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, key: str = Query("")):
    """WebSocket feed the dashboard connects to for live events."""
    if not _key_ok(key):
        await websocket.close(code=1008)
        return
    await live_feed.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # dashboard doesn't send anything meaningful; just keep alive
    except WebSocketDisconnect:
        await live_feed.disconnect(websocket)
