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
from .routes.departments import router as departments_router
from .routes.notifications import router as notifications_router
from .routes.jobs import router as jobs_router


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_db()
    except Exception as e:
        logger.error("Database connection failed: %s", e)

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

    try:
        from .database import get_db
        db = get_db()
        if db is not None:
            default_depts = ["Sales", "Customer Support", "Collections", "Renewals", "Inside Sales", "Marketing", "HR"]
            for name in default_depts:
                existing = await db.departments.find_one({"name": name})
                if not existing:
                    from .models.department import create_department_doc
                    await db.departments.insert_one(create_department_doc(name))
                    logger.info("Seeded default department: %s", name)
    except Exception as e:
        logger.warning("Could not seed default departments: %s", e)

    logger.info("EchoPeak backend started successfully")
    yield
    await close_db()
    logger.info("EchoPeak backend shut down")


app = FastAPI(title="EchoPeak API", lifespan=lifespan)

# ── Health Check Endpoint ─────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "EchoPeak API"}


from .config import FRONTEND_URL

origins = [FRONTEND_URL] if FRONTEND_URL else ["*"]
origins.extend(["http://localhost:3000", "http://localhost:5173", "https://echopeak.vercel.app"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://echopeak.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173"
    ],
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
app.include_router(departments_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
