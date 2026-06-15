import logging
from motor.motor_asyncio import AsyncIOMotorClient
from .config import MONGODB_URI

logger = logging.getLogger(__name__)

DB_NAME = "call_qa"
client = None
db = None


async def connect_db():
    global client, db
    try:
        client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        await client.admin.command("ping")
        logger.info("MongoDB connected successfully")
    except Exception as e:
        logger.exception("MongoDB connection failed: %s", e)
        raise


async def close_db():
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")


def get_db():
    return db
