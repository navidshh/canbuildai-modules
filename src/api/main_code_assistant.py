"""FastAPI entrypoint for the Building Energy Code & Standards Assistant service."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .api_config import settings
from .routes import auth, code_assistant
from .services.bedrock_rag import get_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Registry path (mounted into the container at /home/btap_ml/Code-Compliance/knowledge_bases.json).
REGISTRY_PATH = Path(
    os.getenv(
        "CODE_ASSISTANT_REGISTRY",
        "/home/btap_ml/Code-Compliance/knowledge_bases.json",
    )
)


def _load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        logger.warning("Registry not found at %s; using empty list", REGISTRY_PATH)
        return []
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["codes"]
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to parse registry %s: %s", REGISTRY_PATH, e)
        return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Code Assistant service (loading FAISS indexes)...")
    logger.info(
        "Cognito config: region=%r user_pool_id=%r public_client_id=%r issuer=%r",
        settings.COGNITO_REGION,
        settings.COGNITO_USER_POOL_ID,
        settings.COGNITO_APP_PUBLIC_CLIENT_ID,
        settings.COGNITO_ISSUER,
    )
    try:
        get_service().load(_load_registry())
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to initialize Code Assistant: %s", e)
    yield
    logger.info("Code Assistant service shutting down.")


app = FastAPI(
    lifespan=lifespan,
    title="CanBuildAI Building Energy Code & Standards Assistant API",
    description="Conversational RAG assistant grounded in Canadian building energy codes (NECB and related standards).",
    version="1.0.0",
    swagger_ui_init_oauth={
        "clientId": settings.COGNITO_APP_PUBLIC_CLIENT_ID,
        "scopes": {"openid"},
        "usePkceWithAuthorizationCodeGrant": True,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://navidshh.github.io",
        "https://main.d13kp0x3kfwupp.amplifyapp.com",
        "https://main.d2hvpyy9rpvb37.amplifyapp.com",
        "http://localhost:8080",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth shared with the other services
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
# Code assistant routes
app.include_router(code_assistant.router, prefix="/code-assistant", tags=["Code Assistant"])


@app.get("/health")
async def health():
    svc = get_service()
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok" if svc.is_ready() else "loading",
            "service": "code-assistant",
            "loaded_codes": svc.store.available_codes() if svc.store else [],
        },
    )


@app.get("/")
async def root():
    return PlainTextResponse(
        "CanBuildAI Building Energy Code & Standards Assistant API - see /docs"
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api.main_code_assistant:app", host="0.0.0.0", port=port)
