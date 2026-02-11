"""
Base interface for agent discovery.
Allows switching between static (hardcoded) and dynamic (ADS) discovery.
"""
from abc import ABC, abstractmethod
from typing import List
from shared.schemas.agent_record import AgentRecord, DiscoveryQuery


class AgentDiscovery(ABC):
    """
    Abstract interface for agent discovery.

    Implementations:
    - StaticAgentDiscovery: Hardcoded agent list (for MVP/testing)
    - ADSAgentDiscovery: Dynamic discovery via ADS (for production)
    """

    @abstractmethod
    async def discover(self, query: DiscoveryQuery) -> List[AgentRecord]:
        """
        Discover agents matching the query.

        Args:
            query: Discovery query with skill_id, tags, filters

        Returns:
            List of AgentRecords ranked by relevance/performance
        """
        pass

    @abstractmethod
    async def connect(self):
        """Initialize connection/resources (if needed)"""
        pass

    @abstractmethod
    async def close(self):
        """Cleanup resources"""
        pass

    async def discover_all(self, limit: int = 20) -> List[AgentRecord]:
        """Discover all available agents without tag filtering (for LLM-based selection)."""
        query = DiscoveryQuery(tags=[], limit=limit)
        return await self.discover(query)
