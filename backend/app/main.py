from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes.health import router as health_router
from .api.routes.library import router as library_router
from .api.routes.wires import router as wires_router


def create_app() -> FastAPI:
    app = FastAPI(title="Electrical Drawing VLM Extractor", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(wires_router)
    app.include_router(library_router)

    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    frontend_dist_dir = frontend_dir / "dist"
    frontend_public_dir = frontend_dir / "public"
    if frontend_public_dir.is_dir():
        app.mount("/library", StaticFiles(directory=frontend_public_dir / "library", check_dir=False), name="library")

    if frontend_dist_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend_dist_dir / "assets"), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(frontend_dist_dir / "index.html")

        @app.get("/{route:path}")
        async def spa_fallback(route: str) -> FileResponse:
            if route.startswith("api/"):
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Not found")
            return FileResponse(frontend_dist_dir / "index.html")

    return app


app = create_app()
