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

AGENT_ID = "org-c-general-clf-003"

# OASF standard classification (filled into OASF record after A2A→OASF translation)
# Skill IDs: category_uid * 100 + sub_skill_uid
# Reference: https://schema.oasf.outshift.com/1.0.0
OASF_SKILLS = [{"name": "images_computer_vision/image_classification", "id": 203}]
OASF_DOMAINS = [{"name": "technology/software_engineering", "id": 102}]

AGENT_SKILL = AgentSkill(
    id="general_image_classification",
    name="General Image Classification",
    description="Classify general images: objects, scenes, activities",
    tags=["general", "objects", "scenes", "imagenet", "person", "car", "animal"],
    examples=[
        "What's in this image?",
        "Classify this photo",
        "Is this a dog or a cat?",
        "What kind of scene is this?",
    ]
)

AGENT_CARD = AgentCard(
    name='General Image Classifier - Organization C',
    id='org-c-general-clf-003',
    description='An AI agent for general-purpose image classification, covering objects, scenes, activities, and everyday imagery.',
    url='http://localhost:9003',
    version='1.0.0',
    defaultInputModes=["image/jpeg", "image/png", "text"],
    defaultOutputModes=["text", "application/json"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AGENT_SKILL],
    supportsAuthenticatedExtendedCard=_supports_auth_extended,
)
