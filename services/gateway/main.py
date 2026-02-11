#!/usr/bin/env python3
# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.utils.logging import setup_logger
from services.gateway.storage.minio_client import MinIOClient
from services.gateway.api.classify import create_classify_api

logger = setup_logger("gateway", level="INFO")

# Create FastAPI app
app = FastAPI(
    title="Classification Gateway",
    description="Image classification request gateway with MinIO storage",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MinIO client
minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")

minio_client = MinIOClient(
    endpoint=minio_endpoint,
    access_key=minio_access_key,
    secret_key=minio_secret_key,
    secure=False
)

# Planner URL
planner_url = os.getenv("PLANNER_URL", "http://localhost:8083")

# Include classification API
classify_router = create_classify_api(minio_client, planner_url)
app.include_router(classify_router)

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "../../frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/ui")
async def serve_frontend():
    """Serve frontend UI"""
    index_path = os.path.join(os.path.dirname(__file__), "../../frontend/index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Frontend not found"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Classification Gateway",
        "version": "1.0.0",
        "endpoints": {
            "classify": "POST /v1/classify (multipart/form-data)",
            "get_result": "GET /v1/classify/{task_id}",
            "stream_result": "GET /v1/classify/{task_id}/stream",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.getenv("GATEWAY_PORT", "8080"))
    logger.info(f"Starting Classification Gateway on port {port}")
    logger.info(f"MinIO endpoint: {minio_endpoint}")
    logger.info(f"Planner URL: {planner_url}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
