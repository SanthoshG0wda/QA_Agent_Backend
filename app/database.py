from motor.motor_asyncio import AsyncIOMotorClient
from .config import MONGODB_URI

DB_NAME = "call_qa"
client = None
db = None


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    await client.admin.command("ping")


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return db
