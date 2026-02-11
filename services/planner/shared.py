# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Shared factory for A2A transport.

Follows Lungo's pattern - single AgntcyFactory instance shared across modules.
"""

from typing import Optional
from agntcy_app_sdk.factory import AgntcyFactory

_factory: Optional[AgntcyFactory] = None


def set_factory(factory: AgntcyFactory):
    """Set the global factory instance"""
    global _factory
    _factory = factory


def get_factory() -> AgntcyFactory:
    """Get or create the global factory instance"""
    if _factory is None:
        return AgntcyFactory("planner.transport", enable_tracing=False)
    return _factory
