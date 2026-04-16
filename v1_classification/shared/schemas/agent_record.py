# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class AgentSkillSchema(BaseModel):
    """Output schema for agent skill"""
    type: str
    properties: Dict[str, Any]


class AgentSkill(BaseModel):
    """Agent skill definition (OASF-style)"""
    id: str
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    input_modes: List[str] = Field(default_factory=list)
    output_schema: Optional[AgentSkillSchema] = None


class AgentPerformanceMetrics(BaseModel):
    """Performance metrics for agent"""
    avg_latency_ms: float
    p95_latency_ms: float
    success_rate: float = Field(..., ge=0, le=1)
    throughput_rps: float


class AgentConstraints(BaseModel):
    """Agent constraints and capabilities"""
    max_image_size_mb: int = 10
    supported_formats: List[str] = Field(default_factory=lambda: ["jpeg", "png"])
    min_confidence_threshold: float = 0.6


class AgentCapabilities(BaseModel):
    """Agent capabilities"""
    skills: List[AgentSkill]


class AgentRecord(BaseModel):
    """OASF-style agent record for discovery"""
    agent_id: str
    name: str = Field("", description="Agent display name (must match AgentCard.name for NATS topic)")
    description: str = Field("", description="Agent description for LLM-based selection")
    organization: str
    url: str = Field(..., description="Agent endpoint URL")
    capabilities: AgentCapabilities
    performance_metrics: Optional[AgentPerformanceMetrics] = None
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    ttl_seconds: int = 60

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "org-a-medical-xray-clf-001",
                "organization": "hospital-a",
                "url": "http://10.0.1.15:9001",
                "capabilities": {
                    "skills": [
                        {
                            "id": "image_classification",
                            "name": "Medical Image Classification",
                            "description": "Classify medical images",
                            "tags": ["xray", "ct_scan", "pneumonia"],
                            "input_modes": ["image/jpeg", "image/png"]
                        }
                    ]
                },
                "performance_metrics": {
                    "avg_latency_ms": 1200,
                    "p95_latency_ms": 2500,
                    "success_rate": 0.92,
                    "throughput_rps": 50
                }
            }
        }


class DiscoveryQuery(BaseModel):
    """Query for agent discovery"""
    skill_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    min_success_rate: float = Field(0.0, ge=0, le=1)
    max_latency_ms: Optional[int] = None
    limit: int = Field(10, ge=1, le=100)
    organization: Optional[str] = None
