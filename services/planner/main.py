#!/usr/bin/env python3
# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.utils.logging import setup_logger
from shared.schemas import ClassificationRequest
from shared.discovery import AgentDiscovery, StaticAgentDiscovery, ADSAgentDiscovery

# Import LangGraph planner
from services.planner.agent_langgraph import LangGraphPlannerAgent

logger = setup_logger("planner", level="INFO")

# Global planner agent
planner = None
discovery: AgentDiscovery = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global planner, discovery

    logger.info("Starting Planner Agent...")

    # Initialize agent discovery
    # Set DISCOVERY_MODE=ads to use ADS, otherwise defaults to static
    discovery_mode = os.getenv("DISCOVERY_MODE", "static").lower()

    if discovery_mode == "ads":
        ads_address = os.getenv("ADS_SERVER_ADDRESS", "localhost:8888")
        discovery = ADSAgentDiscovery(server_address=ads_address)
        logger.info(f"Using ADS discovery (address: {ads_address})")
    else:
        discovery = StaticAgentDiscovery()
        logger.info("Using static discovery (hardcoded agents)")

    await discovery.connect()

    # Initialize planner (LangGraph with LLM + A2A)
    # A2A transport is handled by tools.py (Lungo style)
    planner = LangGraphPlannerAgent(discovery=discovery)
    logger.info("Planner initialized (LangGraph + LLM + A2A)")

    yield

    # Shutdown
    logger.info("Shutting down Planner Agent...")
    if discovery:
        await discovery.close()



# Create FastAPI app
app = FastAPI(
    title="Classification Planner",
    description="Intelligent routing and verification for image classification",
    version="1.0.0",
    lifespan=lifespan
)


@app.post("/plan")
async def plan_classification(request: ClassificationRequest):
    """
    Plan and execute classification request.

    Returns:
        Classification result with verification info
    """
    if not planner:
        raise HTTPException(status_code=503, detail="Planner not initialized")

    try:
        result = await planner.plan_and_execute(request)
        return result

    except Exception as e:
        logger.error(f"Error planning classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "planner": "initialized" if planner else "not_initialized"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Classification Planner",
        "version": "1.0.0",
        "endpoints": {
            "plan": "POST /plan",
            "health": "GET /health"
        }
    }


if __name__ == "__main__":
    port = int(os.getenv("PLANNER_PORT", "8083"))
    logger.info(f"Starting Planner on port {port}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
