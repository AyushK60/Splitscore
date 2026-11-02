"""FastAPI application factory.

Two ways to run it:

* **Development**: ``uvicorn app.main:app --reload --port 8000`` from ``backend/``,
  with the Vite dev server on port 5173 proxying ``/api`` to it.
* **Single command**: after ``npm run build`` in ``frontend/``, this app also serves
  the built assets at ``/``, so ``python -m app.main`` gives a complete local
  application on one port.

CORS is restricted to the documented development origins. It is not ``*``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.deps import get_context
from app.api.error_handlers import register_error_handlers
from app.api.routes_audit import router as audit_router
from app.api.routes_datasets import router as datasets_router
from app.api.routes_reports import router as reports_router
from app.api.routes_research import router as research_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging, get_logger
from app.core.version import APP_NAME, APP_VERSION, AUDIT_SCHEMA_VERSION

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.api.log_level)

    app = FastAPI(
        title=f"{APP_NAME} API",
        version=APP_VERSION,
        description=(
            "Deterministic audit of tabular machine-learning train/test splits for specific, "
            "evidence-supported leakage risks. Local, single-user, no authentication."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.api.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition", "X-SplitScope-Export-Note"],
    )

    register_error_handlers(app)

    app.include_router(datasets_router)
    app.include_router(audit_router)
    app.include_router(reports_router)
    app.include_router(research_router)

    @app.get("/api", include_in_schema=False)
    def api_root() -> JSONResponse:
        return JSONResponse(
            {
                "name": APP_NAME,
                "version": APP_VERSION,
                "audit_schema_version": AUDIT_SCHEMA_VERSION,
                "docs": "/api/docs",
                "health": "/api/health",
            }
        )

    context = get_context()
    logger.info(
        "%s %s starting. Datasets directory: %s. Store limits: %s",
        APP_NAME,
        APP_VERSION,
        settings.upload.as_dict(),
        context.store.stats().limits,
    )

    if FRONTEND_DIST.is_dir():
        # Built frontend present: serve it so one command gives the whole app.
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
        logger.info("Serving built frontend from %s", FRONTEND_DIST)
    else:
        @app.get("/", include_in_schema=False)
        def root_without_frontend() -> JSONResponse:
            return JSONResponse(
                {
                    "message": (
                        "The frontend has not been built yet. Run 'npm install && npm run build' in "
                        "frontend/, or run the Vite dev server on http://localhost:5173."
                    ),
                    "api_docs": "/api/docs",
                    "health": "/api/health",
                },
                status_code=200,
            )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=False,
        log_level=settings.api.log_level.lower(),
    )


if __name__ == "__main__":
    main()
