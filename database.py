"""
MongoDB Atlas async connection via Motor.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "asana_sense"

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> AsyncIOMotorDatabase:
    """Initialize and return the database connection."""
    global _client, _db
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URI)
        _db = _client[DB_NAME]
        # Verify connection
        await _client.admin.command("ping")
        print(f"[DB] Connected to MongoDB Atlas — database: {DB_NAME}")
    return _db


async def close_db():
    """Close the database connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        print("[DB] MongoDB connection closed.")


def get_db() -> AsyncIOMotorDatabase:
    """Get the current database instance (must call connect_db first)."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return _db


# Collection accessors
def users_collection():
    return get_db()["users"]


def poses_collection():
    return get_db()["poses"]


def sessions_collection():
    return get_db()["sessions"]


def reference_poses_collection():
    return get_db()["reference_poses"]
