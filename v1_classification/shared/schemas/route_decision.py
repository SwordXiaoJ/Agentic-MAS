# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class AgentRole(str, Enum):
    """Role of agent in execution"""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ENSEMBLE = "ensemble"


class SelectedAgent(BaseModel):
    """Agent selected for task execution"""
    agent_id: str
    name: str = Field("", description="Agent display name for A2A topic routing")
    url: str
    role: AgentRole
    selection_score: float
    selection_reason: str


class ExecutionStrategy(str, Enum):
    """Strategy for task execution"""
    SINGLE_BEST = "single_best"
    PARALLEL_ENSEMBLE = "parallel_ensemble"
    SEQUENTIAL_FALLBACK = "sequential_fallback"


class FallbackAction(str, Enum):
    """Action to take on failure"""
    REPLAN_ENSEMBLE = "replan_ensemble"
    TRY_SECONDARY = "try_secondary"
    HUMAN_REVIEW = "human_review"
    ABORT = "abort"
    VOTE = "vote"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    EXPERT_TIEBREAK = "expert_tiebreak"


class FallbackPolicy(BaseModel):
    """Policy for handling failures"""
    on_low_confidence: FallbackAction = FallbackAction.REPLAN_ENSEMBLE
    on_agent_failure: FallbackAction = FallbackAction.TRY_SECONDARY
    on_disagreement: FallbackAction = FallbackAction.VOTE


class RouteDecision(BaseModel):
    """Plan for routing classification task"""
    request_id: str
    selected_agents: List[SelectedAgent]
    strategy: ExecutionStrategy
    fallback_policy: FallbackPolicy = Field(default_factory=FallbackPolicy)
    verification_config: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req-abc123",
                "selected_agents": [
                    {
                        "agent_id": "org-a-medical-clf-001",
                        "url": "http://10.0.1.15:9001",
                        "role": "primary",
                        "selection_score": 0.94,
                        "selection_reason": "Highest tag match for medical+xray"
                    }
                ],
                "strategy": "single_best",
                "fallback_policy": {
                    "on_low_confidence": "replan_ensemble",
                    "on_agent_failure": "try_secondary"
                }
            }
        }
