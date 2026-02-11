# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TopKPrediction(BaseModel):
    """Single prediction in top-K list"""
    label: str
    confidence: float = Field(..., ge=0, le=1)
    rank: int = Field(..., ge=1)


class ClassificationEvidence(BaseModel):
    """Evidence for classification decision"""
    saliency_map_url: Optional[str] = None
    attention_regions: Optional[List[Dict[str, Any]]] = None
    model_version: Optional[str] = None


class ClassificationResult(BaseModel):
    """Result from a single classifier agent"""
    request_id: str
    agent_id: str
    label: str = Field(..., description="Top predicted class")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    top_k: List[TopKPrediction] = Field(..., description="Top-K predictions")
    evidence: Optional[ClassificationEvidence] = None
    latency_ms: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # MCP enhancement fields
    mcp_enhanced: bool = Field(False, description="Whether MCP tools were used")
    reasoning: Optional[str] = Field(None, description="Diagnostic reasoning (with MCP)")

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req-abc123",
                "agent_id": "org-a-medical-clf-001",
                "label": "pneumonia",
                "confidence": 0.89,
                "top_k": [
                    {"label": "pneumonia", "confidence": 0.89, "rank": 1},
                    {"label": "normal", "confidence": 0.08, "rank": 2},
                    {"label": "tuberculosis", "confidence": 0.03, "rank": 3}
                ],
                "latency_ms": 1342
            }
        }


class ClassificationResponse(BaseModel):
    """Final response to user"""
    task_id: str
    status: str = Field(..., description="PROCESSING, COMPLETED, FAILED")
    result: Optional[ClassificationResult] = None
    verification: Optional[Dict[str, Any]] = None
    iterations: int = Field(1, description="Number of planning iterations")
    total_latency_ms: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None
