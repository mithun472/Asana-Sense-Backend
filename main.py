"""
ASANA-SENSE FastAPI Backend
- REST endpoints for auth, poses, sessions, AI reports
- WebSocket for real-time pose detection pipeline
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from database import connect_db, close_db, users_collection, sessions_collection
from pose_engine import pose_engine
from reference_poses import load_or_compute_references
from cloudinary_utils import configure_cloudinary
from routes import register_routes

load_dotenv()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("[App] Starting ASANA-SENSE Backend...")
    await connect_db()
    configure_cloudinary()

    # Load TFLite model
    try:
        pose_engine.load_model()
    except Exception as e:
        print(f"[App] WARNING: Could not load TFLite model: {e}")
        print("[App] Pose detection will not be available.")

    # Load reference poses (checks both root and ml directory paths)
    try:
        ref_csv = "../train_landmarks.csv"
        if not os.path.exists(ref_csv) and os.path.exists("../ml/data/train_landmarks.csv"):
            ref_csv = "../ml/data/train_landmarks.csv"
        refs = await load_or_compute_references(ref_csv)
        if refs:
            pose_engine.set_reference_poses(refs)
    except Exception as e:
        print(f"[App] WARNING: Could not load reference poses: {e}")

    # Create DB indexes
    await users_collection().create_index("email", unique=True)
    await sessions_collection().create_index("user_id")

    print("[App] ASANA-SENSE Backend ready.")
    yield

    # Shutdown
    await close_db()
    print("[App] Shutdown complete.")


app = FastAPI(
    title="ASANA-SENSE API",
    description="AI Yoga Posture Correction Backend",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS. FRONTEND_ORIGIN may contain comma-separated local and ngrok origins.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
import time
from live_feed import live_feed, categorize

@app.middleware("http")
async def record_activity(request, call_next):
    start = time.time()
    response = await call_next(request)
    category, label = categorize(request.url.path)
    await live_feed.record({
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": round((time.time() - start) * 1000),
        "time": __import__("datetime").datetime.utcnow().isoformat(),
        "category": category,
        "category_label": label,
        "client": request.client.host if request.client else "",
    })
    return response

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "message": "ASANA-SENSE Backend is running"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ASANA-SENSE FastAPI Backend", "version": "2.0.0"}


# ── Register Modular Routers ──────────────────────────────────────────────────
register_routes(app)


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
