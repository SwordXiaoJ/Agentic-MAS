# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class VerificationStatus(str, Enum):
    """Verification status"""
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationTestResult(str, Enum):
    """Individual test result"""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class VerificationTest(BaseModel):
    """Single verification test result"""
    test_name: str
    result: VerificationTestResult
    details: Dict[str, Any] = Field(default_factory=dict)


class DisagreementAnalysis(BaseModel):
    """Analysis of disagreement between agents"""
    agreement_rate: float = Field(..., ge=0, le=1)
    conflicting_labels: List[str]
    vote_distribution: Dict[str, int]


class VerificationRecommendation(str, Enum):
    """Recommended action after verification"""
    ACCEPT = "accept"
    REPLAN_ENSEMBLE = "replan_ensemble"
    REPLAN_DIFFERENT_AGENTS = "replan_different_agents"
    HUMAN_REVIEW = "human_review"
    ABORT = "abort"


class VerificationReport(BaseModel):
    """Verification report for classification results"""
    request_id: str
    status: VerificationStatus
    tests_performed: List[VerificationTest]
    primary_result: Optional[Dict[str, Any]] = None
    ensemble_results: Optional[List[Dict[str, Any]]] = None
    disagreement_analysis: Optional[DisagreementAnalysis] = None
    recommendation: VerificationRecommendation
    notes: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VerificationConfig(BaseModel):
    """Configuration for verification"""
    enable_augmentation_test: bool = True
    enable_ensemble_voting: bool = False
    confidence_threshold: float = Field(0.75, ge=0, le=1)
    augmentation_stability_threshold: float = Field(0.67, ge=0, le=1)
    ensemble_agreement_threshold: float = Field(0.67, ge=0, le=1)
