import os
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
from .services.transcription import load_model as load_whisper_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    load_whisper_model()
    yield
    await close_db()


app = FastAPI(title="Call QA POC", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
