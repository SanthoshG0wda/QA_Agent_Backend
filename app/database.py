from motor.motor_asyncio import AsyncIOMotorClient
from .config import MONGODB_URI

client = None
db = None


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client.get_default_database()
    await client.admin.command("ping")


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return db
