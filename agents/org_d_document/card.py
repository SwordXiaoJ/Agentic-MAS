# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

# Import security config for authenticated extended card support
# (with fallback for backward compatibility)
try:
    from config.security_config import get_security_config

    _security_config = get_security_config()
    _supports_auth_extended = _security_config.is_secure
except ImportError:
    _supports_auth_extended = False

AGENT_ID = "org-d-document-clf-004"

# OASF standard classification (filled into OASF record after A2A→OASF translation)
# Skill IDs: category_uid * 100 + sub_skill_uid
# Reference: https://schema.oasf.outshift.com/1.0.0
OASF_SKILLS = [{"name": "nlp_document_processing/document_classification", "id": 1201}]
OASF_DOMAINS = [{"name": "technology/software_engineering", "id": 102}]

AGENT_SKILL = AgentSkill(
    id="document_analysis_classification",
    name="Document Analysis Classification",
    description="Extract text from a document image and classify its type",
    tags=["document", "ocr", "invoice", "form", "handwritten", "chart"],
    examples=[
        "Extract the text from this document and tell me what it is",
        "Is this an invoice or an official form?",
        "Classify this scanned document",
        "Read this handwritten note and categorize it",
    ],
)

AGENT_CARD = AgentCard(
    name="Document Analysis Classifier - Organization D",
    id="org-d-document-clf-004",
    description="An AI agent that extracts text from document images and classifies them as invoice, handwritten note, chart, or official form.",
    url="http://localhost:9004",
    version="1.0.0",
    defaultInputModes=["image/jpeg", "image/png", "text"],
    defaultOutputModes=["text", "application/json"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AGENT_SKILL],
    supportsAuthenticatedExtendedCard=_supports_auth_extended,
)

