"""
Agent discovery abstractions.

Usage:
    # For simplified setup (hardcoded agents)
    from shared.discovery import StaticAgentDiscovery
    discovery = StaticAgentDiscovery()

    # For production (dynamic ADS)
    from shared.discovery import ADSAgentDiscovery
    discovery = ADSAgentDiscovery(ads_url="http://localhost:8082")
"""
from shared.discovery.base import AgentDiscovery
from shared.discovery.static_discovery import StaticAgentDiscovery
from shared.discovery.ads_discovery import ADSAgentDiscovery

__all__ = [
    "AgentDiscovery",
    "StaticAgentDiscovery",
    "ADSAgentDiscovery",
]
