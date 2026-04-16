# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill
)

# Import security config for authenticated extended card support
# (with fallback for backward compatibility)
try:
    from config.security_config import get_security_config
    _security_config = get_security_config()
    _supports_auth_extended = _security_config.is_secure
except ImportError:
    _supports_auth_extended = False

AGENT_ID = "org-a-medical-clf-001"  # Agent identifier (not part of AgentCard schema)

# OASF standard classification (filled into OASF record after A2A→OASF translation)
# Skill IDs: category_uid * 100 + sub_skill_uid
# Reference: https://schema.oasf.outshift.com/1.0.0
OASF_SKILLS = [{"name": "images_computer_vision/image_classification", "id": 203}]
OASF_DOMAINS = [{"name": "healthcare/medical_technology", "id": 901}]

AGENT_SKILL = AgentSkill(
    id="medical_image_classification",
    name="Medical Image Classification",
    description="Classify medical images (X-ray, CT, MRI) for diagnosis assistance",
    tags=["medical", "xray", "ct_scan", "mri", "pneumonia", "tuberculosis", "diagnosis", "healthcare"],
    examples=[
        "Classify this X-ray image for pneumonia detection",
        "Analyze this CT scan for abnormalities",
        "Is there evidence of tuberculosis in this chest X-ray?",
        "Classify this medical image",
    ]
)

AGENT_CARD = AgentCard(
    name='Medical Image Classifier - Organization A',
    id='org-a-medical-clf-001',
    description='An AI agent specialized in classifying medical images including X-rays, CT scans, and MRI images for diagnostic assistance.',
    url='http://localhost:9001',
    version='1.0.0',
    defaultInputModes=["image/jpeg", "image/png", "image/dicom", "text"],
    defaultOutputModes=["text", "application/json"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AGENT_SKILL],
    supportsAuthenticatedExtendedCard=_supports_auth_extended,
)
