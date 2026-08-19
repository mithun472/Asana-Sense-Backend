from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import connect_to_mongo, close_mongo_connection, get_poses_collection
from app.ml_model import load_model
from app.routers import poses, predict


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    connect_to_mongo()
    await get_poses_collection().create_index("pose_name", unique=True)
    load_model()
    yield
    # Shutdown
    close_mongo_connection()


app = FastAPI(title="Asana-Sense API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this for production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(poses.router)
app.include_router(predict.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
