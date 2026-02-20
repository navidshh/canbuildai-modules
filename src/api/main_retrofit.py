from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from ..api_config import settings
from ..routes import auth, tests, retrofit_prediction
from ..redis_client import init_redis, close_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Connecting to Redis...")
    try:
        app.state.redis_client = await init_redis()
        logger.info("Successfully connected to Redis!")
    except Exception as e:
        logger.warning(f"Redis not available, continuing without it: {e}")
        app.state.redis_client = None

    yield

    # Shutdown
    if app.state.redis_client:
        logger.info("Closing Redis connection...")
        await close_redis(app.state.redis_client)

app = FastAPI(
    lifespan=lifespan,
    title="CanBuildAI Retrofit Planner API",
    description="API for Building Retrofit Planning with XGBoost ensemble models",
    version="3.0.0",
    swagger_ui_init_oauth={
        "clientId": settings.COGNITO_APP_PUBLIC_CLIENT_ID,
        "scopes": {"openid"},
        "usePkceWithAuthorizationCodeGrant": True,
    }
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://navidshh.github.io",
        "https://main.d13kp0x3kfwupp.amplifyapp.com",
        "http://localhost:8080",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register retrofit planner routes
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(tests.router, prefix="/tests", tags=["Test"])
app.include_router(retrofit_prediction.router, prefix="/retrofit", tags=["Retrofit Planner"])

@app.get("/health")
async def health_check():
    return JSONResponse(status_code=200, content={
        "status": "ok",
        "service": "retrofit-planner",
        "message": "Retrofit Planner API is healthy"
    })

@app.get("/")
async def root():
    return PlainTextResponse("CanBuildAI Retrofit Planner API v3.0 - Use /docs for API documentation")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api.main_retrofit:app", host="0.0.0.0", port=port)
