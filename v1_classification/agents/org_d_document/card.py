# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

try:
    from config.security_config import get_security_config
    _security_config = get_security_config()
    _supports_auth_extended = _security_config.is_secure
except ImportError:
    _supports_auth_extended = False

AGENT_ID = "org-d-document-clf-004"

AGENT_SKILL = AgentSkill(
    id="image_classification",
    name="Document Analysis & Classification",
    description=(
        "Analyze document images and prompts: infer document type, summarize extracted "
        "or implied text, and return a confidence score."
    ),
    tags=[
        "document",
        "ocr",
        "receipt",
        "invoice",
        "form",
        "handwritten",
        "chart",
        "classification",
    ],
    examples=[
        "Extract and classify this scanned document image.",
        "Is this image a receipt or an official form?",
        "What type of document is this and what is the main text content?",
    ],
)

AGENT_CARD = AgentCard(
    name="Document Analysis Classifier - Organization D",
    id=AGENT_ID,
    description=(
        "An AI agent for document-oriented images: receipts, forms, notes, and charts — "
        "structured classification and text extraction via PydanticAI."
    ),
    url="http://localhost:9004",
    version="1.0.0",
    defaultInputModes=["image/jpeg", "image/png", "application/pdf", "text"],
    defaultOutputModes=["text", "application/json"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AGENT_SKILL],
    supportsAuthenticatedExtendedCard=_supports_auth_extended,
)
