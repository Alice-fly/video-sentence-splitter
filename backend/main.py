import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, checkpoint_database, engine
from config import SUBTITLES_DIR, OUTPUTS_DIR
from routers.settings import router as settings_router
from routers.categories import router as categories_router
from routers.videos import router as videos_router
from routers.imports import router as imports_router
from routers.subtitles import router as subtitles_router
from routers.segmentation import router as segmentation_router
from routers.translation import router as translation_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(SUBTITLES_DIR, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    await init_db()
    yield
    # Graceful shutdown: flush WAL and close connections
    logger.info("Shutting down: checkpointing database...")
    await checkpoint_database()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(title="Video Sentence Splitter", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings_router)
app.include_router(categories_router)
app.include_router(videos_router)
app.include_router(imports_router)
app.include_router(subtitles_router)
app.include_router(segmentation_router)
app.include_router(translation_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
