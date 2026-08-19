from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client: AsyncIOMotorClient | None = None


def connect_to_mongo():
    global client
    client = AsyncIOMotorClient(settings.mongo_uri)


def close_mongo_connection():
    global client
    if client is not None:
        client.close()


def get_database():
    """Returns the asana_sense database handle."""
    return client[settings.db_name]


def get_poses_collection():
    return get_database()[settings.poses_collection]
