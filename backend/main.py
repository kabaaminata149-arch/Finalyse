"""
main.py — Finalyse Backend v1.0
FastAPI entry point — all routes registered here.
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import UPLOAD_DIR, EXPORT_DIR
from database.db import init
from routes import auth, factures, dossiers, dashboard, export, chatbot, backup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("finalyse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init()
    # Vérifier quelle version du processor est chargée
    try:
        from services.processor import process_invoice
        import inspect
        src = inspect.getsource(process_invoice)
        if "_extract_regex" in src:
            log.info("  Processor v3-REGEX charge OK")
        else:
            log.warning("  ATTENTION: ancien processor (mock) charge !")
    except Exception as e:
        log.error("  Erreur chargement processor: %s", e)

    log.info("=" * 55)
    log.info("  Finalyse API v1.0 — Demarree")
    log.info("  Docs : http://localhost:8000/docs")
    log.info("=" * 55)
    yield


app = FastAPI(
    title="Finalyse API",
    description="Plateforme d'analyse de factures par IA — FCFA currency",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Routes
app.include_router(auth.router)
app.include_router(factures.router)
app.include_router(dossiers.router)
app.include_router(dashboard.router)
app.include_router(export.router)
app.include_router(chatbot.router)
app.include_router(backup.router)


@app.get("/")
def root():
    return {
        "app":     "Finalyse API",
        "version": "1.0.0",
        "currency": "FCFA",
        "docs":    "/docs",
        "status":  "running",
    }


@app.get("/health")
def health():
    from datetime import datetime
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
