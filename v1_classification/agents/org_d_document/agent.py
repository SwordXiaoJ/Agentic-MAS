# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Document analysis using PydanticAI structured output.

No OpenTelemetry / Observe here — keep this module free of OTLP hooks.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent

logger = logging.getLogger(__name__)


class DocumentAnalysisOutput(BaseModel):
    """Structured result returned to the A2A executor."""

    document_type: str = Field(
        ...,
        description="One of: receipt, invoice, official_form, handwritten_note, chart, other",
    )
    extracted_text: str = Field(
        ...,
        description="Main visible or implied text content, or a concise summary if text is not literal.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in document_type and extraction.")

    @field_validator("document_type", mode="before")
    @classmethod
    def normalize_type(cls, v: object) -> str:
        if v is None:
            return "other"
        return str(v).strip().lower() or "other"


def _pydantic_ai_model_id() -> str:
    """Map LLM_MODEL like openai/gpt-4o-mini to pydantic-ai openai:gpt-4o-mini."""
    raw = os.getenv("LLM_MODEL", "openai/gpt-4o-mini").strip()
    if "/" in raw:
        provider, name = raw.split("/", 1)
        return f"{provider.strip()}:{name.strip()}"
    return f"openai:{raw}"


_SYSTEM_PROMPT = """You are a document analyst. The user message may include the document image as attached image data (use that for all visual content).
- Infer the most likely document_type among: receipt, invoice, official_form, handwritten_note, chart, other.
- Provide extracted_text: key visible text, fields, or a tight summary.
- Set confidence between 0 and 1 reflecting how sure you are.
Be factual; if the image is unreadable or missing, say so in extracted_text and lower confidence."""


_agent: Any = None


def get_document_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            _pydantic_ai_model_id(),
            output_type=DocumentAnalysisOutput,
            system_prompt=_SYSTEM_PROMPT,
        )
        logger.info("PydanticAI document agent initialized (%s)", _pydantic_ai_model_id())
    return _agent


def _sniff_image_media_type(data: bytes) -> str:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 6 and (data[:6] in (b"GIF87a", b"GIF89a")):
        return "image/gif"
    return "image/png"


async def _fetch_image_for_model(url: str) -> tuple[bytes, str] | None:
    """
    Download image from presigned URL using the document agent's network (MinIO on localhost works here).
    OpenAI cannot fetch localhost URLs from its servers; we must attach bytes via BinaryContent.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.content
        ct = response.headers.get("content-type", "")
        if ct:
            media = ct.split(";")[0].strip().lower()
            if media in ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"):
                if media == "image/jpg":
                    media = "image/jpeg"
                return data, media
        return data, _sniff_image_media_type(data)
    except Exception as e:
        logger.warning("Could not download image for vision input (%s): %s", url[:80], e)
        return None


async def analyze_document(
    user_prompt: str,
    supplemental_context: str = "",
    *,
    image_fetch_url: str | None = None,
) -> DocumentAnalysisOutput:
    """
    Run structured document analysis.

    Args:
        user_prompt: Primary user / planner instructions.
        supplemental_context: Optional extra text (e.g. hints); image bytes are separate when URL fetch succeeds.
        image_fetch_url: If set, download here and send as BinaryContent (required for localhost MinIO URLs).
    """
    text = user_prompt.strip()
    if supplemental_context.strip():
        text = f"{text}\n\n--- Context ---\n{supplemental_context.strip()}"

    user_part: str | list[str | BinaryContent]
    loaded = await _fetch_image_for_model(image_fetch_url) if image_fetch_url else None
    if loaded:
        raw_bytes, media_type = loaded
        user_part = [text, BinaryContent(data=raw_bytes, media_type=media_type)]
        logger.debug("Vision input: %d bytes, %s", len(raw_bytes), media_type)
    elif image_fetch_url:
        text = f"{text}\n\n(Fallback: image download failed; URL was not loaded as pixels.)"
        user_part = text
    else:
        user_part = text

    result = await get_document_agent().run(user_part)
    return result.output
