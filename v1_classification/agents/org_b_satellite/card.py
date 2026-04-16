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

AGENT_ID = "org-b-satellite-clf-002"  # Agent identifier (not part of AgentCard schema)

# OASF standard classification (filled into OASF record after A2A→OASF translation)
# Skill IDs: category_uid * 100 + sub_skill_uid
# Reference: https://schema.oasf.outshift.com/1.0.0
OASF_SKILLS = [{"name": "images_computer_vision/image_classification", "id": 203}]
OASF_DOMAINS = [{"name": "environmental_science/environmental_monitoring", "id": 1704}]

AGENT_SKILL = AgentSkill(
    id="satellite_image_classification",
    name="Satellite Image Classification",
    description="Classify satellite and aerial imagery for landcover analysis",
    tags=["satellite", "geospatial", "landcover", "urban", "forest", "water", "aerial"],
    examples=[
        "Classify this satellite image for urban planning",
        "What type of landcover is in this aerial image?",
        "Is this area forest or agricultural land?",
        "Analyze this Landsat image",
    ]
)

AGENT_CARD = AgentCard(
    name='Satellite Image Classifier - Organization B',
    id='org-b-satellite-clf-002',
    description='An AI agent specialized in classifying satellite and aerial imagery for landcover analysis, urban planning, and geospatial applications.',
    url='http://localhost:9002',
    version='1.0.0',
    defaultInputModes=["image/jpeg", "image/png", "image/tiff", "text"],
    defaultOutputModes=["text", "application/json"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AGENT_SKILL],
    supportsAuthenticatedExtendedCard=_supports_auth_extended,
)
