"""
Routes package for ASANA-SENSE API.
Exposes all modular APIRouters and helper to attach them to the FastAPI application.
"""
from fastapi import FastAPI
from .auth import router as auth_router
from .poses import router as poses_router
from .sessions import router as sessions_router
from .reports import router as reports_router
from .websocket import router as websocket_router
from .live_ops import router as live_ops_router

def register_routes(app: FastAPI) -> None:
    """Attach all modular routers to the FastAPI application."""
    app.include_router(auth_router)
    app.include_router(poses_router)
    app.include_router(sessions_router)
    app.include_router(reports_router)
    app.include_router(websocket_router)
    app.include_router(live_ops_router)
