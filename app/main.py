import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import connect_db, close_db
from .routes.upload import router as upload_router
from .routes.evaluate import router as evaluate_router
from .routes.auth import router as auth_router
from .routes.users import router as users_router
from .routes.analytics import router as analytics_router
from .routes.agents import router as agents_router
from .routes.performance import router as performance_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()

    from .config import DEEPGRAM_API_KEY, GROQ_API_KEY, ENABLE_NIM
    if DEEPGRAM_API_KEY:
        logger.info("Deepgram API key configured")
    else:
        logger.warning("DEEPGRAM_API_KEY not set — transcription will fail")

    if GROQ_API_KEY:
        logger.info("Groq API key configured")
    else:
        logger.warning("GROQ_API_KEY not set — evaluation will use fallback scores")

    if ENABLE_NIM:
        from .config import NVIDIA_API_KEY
        if NVIDIA_API_KEY:
            logger.info("NVIDIA NIM enabled (ENABLE_NIM=true)")
        else:
            logger.warning("ENABLE_NIM=true but NVIDIA_API_KEY not set — NIM will be skipped")
    else:
        logger.info("NVIDIA NIM disabled (ENABLE_NIM=false) — critical errors from Groq only")

    yield
    await close_db()


app = FastAPI(title="EchoPeak API", lifespan=lifespan)

from .config import FRONTEND_URL

origins = [FRONTEND_URL] if FRONTEND_URL else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(evaluate_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(performance_router, prefix="/api")
