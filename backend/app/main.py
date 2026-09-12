from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.observability import RequestContextMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="PlantGPT Backend", version="0.0.1-phase0")

    settings = get_settings()
    # Wide-open in dev so Flutter web (a different origin) can reach this
    # API. Phase 5 (deployment) tightens this to the real client origin(s)
    # once one exists - never ship allow_origins=["*"] to production.
    if settings.dev_mode:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(RequestContextMiddleware)

    app.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
    app.include_router(chat_router, prefix="/v1", tags=["chat"])

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
