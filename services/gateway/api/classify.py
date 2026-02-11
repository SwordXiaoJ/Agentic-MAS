# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
import aiohttp

from shared.schemas import (
    ClassificationRequest,
    ImageSource,
    ClassificationConstraints,
    ClassificationResponse
)
from services.gateway.storage.minio_client import MinIOClient

router = APIRouter(prefix="/v1", tags=["classification"])

# Global state for tasks
task_results: Dict[str, Dict[str, Any]] = {}

# Suggested prompts for different classification domains
SUGGESTED_PROMPTS = [
    {
        "id": "medical-xray",
        "prompt": "Analyze this chest X-ray image and identify any abnormalities or signs of disease",
        "description": "Medical X-ray analysis",
        "domain": "medical"
    },
    {
        "id": "medical-diagnosis",
        "prompt": "Diagnose this medical image and provide potential findings",
        "description": "Medical diagnosis",
        "domain": "medical"
    },
    {
        "id": "satellite-landuse",
        "prompt": "Identify the land use categories in this satellite image (urban, forest, water, agriculture)",
        "description": "Satellite land use classification",
        "domain": "satellite"
    },
    {
        "id": "satellite-urban",
        "prompt": "Analyze this aerial image and identify urban development patterns",
        "description": "Urban planning analysis",
        "domain": "satellite"
    },
    {
        "id": "general-object",
        "prompt": "Classify this image and identify the main objects it contains",
        "description": "General object classification",
        "domain": "general"
    },
    {
        "id": "general-scene",
        "prompt": "Identify the scene type and describe what this image shows",
        "description": "Scene recognition",
        "domain": "general"
    },
    {
        "id": "general-animal",
        "prompt": "Identify the animal species in this image",
        "description": "Animal species identification",
        "domain": "general"
    }
]


def create_classify_api(minio_client: MinIOClient, planner_url: str) -> APIRouter:
    """Create classification API with dependencies"""

    @router.get("/suggested-prompts")
    async def get_suggested_prompts(domain: str = None):
        """
        Get suggested prompts for image classification.

        Args:
            domain: Optional filter by domain (medical, satellite, general)

        Returns:
            List of suggested prompts with id, prompt, description, and domain
        """
        if domain:
            return [p for p in SUGGESTED_PROMPTS if p["domain"] == domain.lower()]
        return SUGGESTED_PROMPTS

    @router.post("/classify")
    async def submit_classification(
        image: UploadFile = File(...),
        prompt: str = Form(...),
        min_confidence: float = Form(0.75),
        timeout_ms: int = Form(5000),
        return_top_k: int = Form(3)
    ):
        """
        Submit image classification request.

        Returns:
            Task ID and polling URLs
        """
        # Generate unique task ID
        task_id = f"req-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Read image file
        image_data = await image.read()

        # Upload to MinIO
        object_name = f"{task_id}/input.{image.filename.split('.')[-1]}"
        try:
            image_ref = minio_client.upload_image(
                image_data,
                object_name,
                content_type=image.content_type
            )
            presigned_url = minio_client.get_presigned_url(object_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload image: {e}")

        # Create classification request
        request = ClassificationRequest(
            request_id=task_id,
            image=ImageSource(
                ref=image_ref,
                presigned_url=presigned_url,
                format=image.filename.split('.')[-1]
            ),
            prompt=prompt,
            constraints=ClassificationConstraints(
                min_confidence=min_confidence,
                timeout_ms=timeout_ms,
                return_top_k=return_top_k
            )
        )

        # Initialize task status
        task_results[task_id] = {
            "status": "PROCESSING",
            "created_at": datetime.utcnow().isoformat()
        }

        # Forward to planner (async, don't wait)
        asyncio.create_task(_send_to_planner(task_id, request, planner_url))

        return {
            "task_id": task_id,
            "status": "PROCESSING",
            "poll_url": f"/v1/classify/{task_id}",
            "stream_url": f"/v1/classify/{task_id}/stream"
        }

    @router.get("/classify/{task_id}")
    async def get_classification_result(task_id: str):
        """Poll for classification result"""
        if task_id not in task_results:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return task_results[task_id]

    @router.get("/classify/{task_id}/stream")
    async def stream_classification_result(task_id: str):
        """Stream classification result (SSE)"""
        if task_id not in task_results:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        async def event_generator():
            """Generate SSE events"""
            while True:
                result = task_results.get(task_id, {})
                yield f"data: {result}\n\n"

                if result.get("status") in ["COMPLETED", "COMPLETED_WITH_WARNING", "FAILED"]:
                    break

                await asyncio.sleep(1)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )

    return router


async def _send_to_planner(task_id: str, request: ClassificationRequest, planner_url: str):
    """Send classification request to planner"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{planner_url}/plan",
                json=request.model_dump(mode="json"),
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                response.raise_for_status()
                result = await response.json()

                # Update task result - propagate planner status
                planner_status = result.get("status", "COMPLETED")
                task_results[task_id] = {
                    "status": planner_status,
                    "result": result,
                    "completed_at": datetime.utcnow().isoformat()
                }

    except Exception as e:
        task_results[task_id] = {
            "status": "FAILED",
            "error": str(e),
            "failed_at": datetime.utcnow().isoformat()
        }
