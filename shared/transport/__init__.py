# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Transport layer for agent communication.

Simplified to follow Lungo's pattern - using AgntcyFactory directly.
"""

from shared.transport.agntcy_transport import AgntcyTransport, create_agntcy_transport

__all__ = [
    "AgntcyTransport",
    "create_agntcy_transport",
]
