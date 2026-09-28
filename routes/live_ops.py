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
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from live_feed import live_feed

router = APIRouter(tags=["Ops Dashboard"])

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend project root


@router.get("/ops")
async def ops_dashboard():
    """Serve the live ops dashboard page."""
    return FileResponse(os.path.join(DASHBOARD_DIR, "dashboard.html"))


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """WebSocket feed the dashboard connects to for live events."""
    await live_feed.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # dashboard doesn't send anything meaningful; just keep alive
    except WebSocketDisconnect:
        await live_feed.disconnect(websocket)
