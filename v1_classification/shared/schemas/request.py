# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ImageSource(BaseModel):
    """Image source - can be bytes, URL, or object store reference"""
    bytes: Optional[str] = Field(None, description="Base64-encoded image bytes")
    format: Optional[str] = Field(None, description="Image format (jpeg, png, dicom)")
    url: Optional[str] = Field(None, description="URL to download image from")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers for URL download")
    ref: Optional[str] = Field(None, description="Object store reference (e.g., s3://bucket/key)")
    presigned_url: Optional[str] = Field(None, description="Presigned URL for object store access")


class ClassificationConstraints(BaseModel):
    """Constraints for classification task"""
    timeout_ms: int = Field(5000, description="Task timeout in milliseconds")
    min_confidence: float = Field(0.75, ge=0, le=1, description="Minimum confidence threshold")
    return_top_k: int = Field(3, ge=1, description="Number of top predictions to return")
    require_verification: bool = Field(True, description="Whether to verify results")
    allowed_orgs: Optional[List[str]] = Field(None, description="Allowed organization IDs")
    preferred_domains: Optional[List[str]] = Field(None, description="Preferred skill domains")


class ClassificationMetadata(BaseModel):
    """Metadata for classification request"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Optional[List[str]] = None


class ClassificationRequest(BaseModel):
    """Complete classification request"""
    request_id: str = Field(..., description="Unique request identifier")
    image: ImageSource
    prompt: str = Field(..., description="Classification task description")
    constraints: ClassificationConstraints = Field(default_factory=ClassificationConstraints)
    metadata: Optional[ClassificationMetadata] = None

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req-20260202-103045-abc",
                "image": {
                    "ref": "s3://classify-bucket/uploads/img-123.jpg",
                    "presigned_url": "https://minio:9000/..."
                },
                "prompt": "Classify this chest X-ray: pneumonia, tuberculosis, or normal",
                "constraints": {
                    "timeout_ms": 5000,
                    "min_confidence": 0.8,
                    "return_top_k": 3
                }
            }
        }
