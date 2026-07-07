from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers are mounted as modules ship (docs/ARCHITECTURE.md §2).
    from app.marketdata.router import router as marketdata_router
    from app.scanner.router import router as scanner_router

    app.include_router(marketdata_router, prefix="/marketdata", tags=["marketdata"])
    app.include_router(scanner_router, prefix="/scans", tags=["scanner"])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
