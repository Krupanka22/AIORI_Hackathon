"""
AIORI - Privacy-Aware IPv6 Security Monitoring System
Main FastAPI application entry point.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import settings
from database.db import init_db, shutdown_db
from api.devices import router as devices_router
from api.network import router as network_router
from api.ipv6 import router as ipv6_router
from api.ai import router as ai_router
from api.alerts import router as alerts_router
from api.blockchain import router as blockchain_router
from api.experiments import router as experiments_router
from api.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown hooks."""
    logger.info("AIORI starting up...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("AIORI shutting down...")
    await shutdown_db()


app = FastAPI(
    title="AIORI - IPv6 IoT Security Monitor",
    description=(
        "Privacy-Aware IPv6 Security Monitoring System for IoT Devices "
        "under Address Rotation. Behavioral fingerprinting, identity resolution, "
        "anomaly detection, and blockchain audit."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(devices_router, prefix="/api/devices", tags=["Devices"])
app.include_router(network_router, prefix="/api/network", tags=["Network"])
app.include_router(ipv6_router, prefix="/api/ipv6", tags=["IPv6"])
app.include_router(ai_router, prefix="/api/ai", tags=["AI"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(blockchain_router, prefix="/api/blockchain", tags=["Blockchain"])
app.include_router(experiments_router, prefix="/api/experiments", tags=["Experiments"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "0.1.0",
        "environment": settings.app_env,
    }


@app.get("/api/status")
async def system_status():
    """Return overall system status including component availability."""
    return {
        "app": settings.app_name,
        "components": {
            "database": "active",
            "mininet": "pending_validation",
            "zeek": "pending_validation",
            "ai_engine": "pending_training",
            "blockchain": "disabled" if not settings.blockchain_enabled else "pending",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
    )
