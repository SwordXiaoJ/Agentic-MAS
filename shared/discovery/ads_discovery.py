# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
ADS-based agent discovery using AGNTCY dir_sdk.

Queries the Agent Directory Service (ADS) for registered agents.
Agents are published via scripts/publish_agent_records.sh.
"""
import os
import logging
from typing import List, Optional
from datetime import datetime

from shared.discovery.base import AgentDiscovery
from shared.schemas.agent_record import (
    AgentRecord,
    AgentCapabilities,
    AgentSkill,
    AgentPerformanceMetrics,
    DiscoveryQuery
)

logger = logging.getLogger(__name__)

# Check for AGNTCY SDK
try:
    from agntcy.dir_sdk.client import Client, Config
    HAS_DIR_SDK = True
except ImportError:
    HAS_DIR_SDK = False
    logger.warning("agntcy-dir SDK not installed. ADS discovery will be limited.")


class ADSAgentDiscovery(AgentDiscovery):
    """
    Dynamic agent discovery via AGNTCY Agent Directory Service (ADS).

    Uses the official agntcy-dir SDK to query published agent records.

    Environment Variables:
        ADS_SERVER_ADDRESS: ADS gRPC address (default: localhost:8888)

    Usage:
        discovery = ADSAgentDiscovery()
        await discovery.connect()
        agents = await discovery.discover(query)
        await discovery.close()
    """

    def __init__(self, server_address: Optional[str] = None):
        """
        Args:
            server_address: ADS gRPC address (default from env or localhost:8888)
        """
        self.server_address = server_address or os.getenv(
            "ADS_SERVER_ADDRESS", "localhost:8888"
        )
        self.client: Optional[Client] = None
        self._connected = False

    async def connect(self):
        """Initialize connection to ADS"""
        if not HAS_DIR_SDK:
            logger.warning("agntcy-dir SDK not available, using fallback mode")
            self._connected = False
            return

        try:
            config = Config(server_address=self.server_address)
            self.client = Client(config)
            self._connected = True
            logger.info(f"Connected to ADS at {self.server_address}")
        except Exception as e:
            logger.error(f"Failed to connect to ADS: {e}")
            self._connected = False

    async def close(self):
        """Close connection"""
        self.client = None
        self._connected = False

    async def discover(self, query: DiscoveryQuery) -> List[AgentRecord]:
        """
        Discover agents by querying ADS.

        Args:
            query: Discovery query with skill_id, tags, filters

        Returns:
            List of AgentRecords matching the query
        """
        if not self._connected or not self.client:
            logger.warning("ADS not connected, returning empty list")
            return []

        try:
            # Build search query based on tags
            search_tags = query.tags or []

            # Search ADS for matching agents
            search_results = self._search_agents(search_tags, query.limit)

            # Convert ADS records to AgentRecord format
            agents = []
            for record in search_results:
                agent = self._convert_to_agent_record(record)
                if agent:
                    agents.append(agent)

            logger.info(f"ADS discovered {len(agents)} agents for tags: {search_tags}")
            return agents

        except Exception as e:
            logger.error(f"ADS discovery failed: {e}")
            return []

    def _search_agents(self, tags: List[str], limit: int) -> List[dict]:
        """
        Search ADS for agents matching tags.

        Returns list of raw record dictionaries.
        """
        if not self.client:
            return []

        try:
            from agntcy.dir_sdk.models import search_v1
            from google.protobuf.json_format import MessageToDict

            results = []

            # Use search_records API to get all published records
            search_req = search_v1.SearchRecordsRequest(limit=limit * 2)
            search_responses = self.client.search_records(search_req)

            if not search_responses:
                logger.info("No records found in ADS")
                return []

            # Convert and filter records
            for resp in search_responses:
                if resp.record and resp.record.data:
                    # Convert protobuf Struct to dict
                    record_dict = MessageToDict(resp.record.data)

                    # Filter by tags if specified
                    if tags:
                        record_tags = self._extract_tags(record_dict)
                        if any(tag.lower() in [t.lower() for t in record_tags] for tag in tags):
                            results.append(record_dict)
                    else:
                        results.append(record_dict)

                    if len(results) >= limit:
                        break

            return results

        except Exception as e:
            logger.error(f"ADS search failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _get_card_data(self, record: dict) -> dict:
        """Extract A2A card_data from OASF record structure"""
        # Try to get card_data from modules (OASF structure)
        modules = record.get("modules", [])
        for module in modules:
            if module.get("name") == "integration/a2a":
                data = module.get("data", {})
                return data.get("card_data", {})
        return {}

    def _extract_tags(self, record: dict) -> List[str]:
        """Extract tags from OASF record"""
        tags = []

        # Get card_data which contains the real skills
        card_data = self._get_card_data(record)

        # Extract tags from card_data skills
        card_skills = card_data.get("skills", [])
        for skill in card_skills:
            skill_tags = skill.get("tags", [])
            tags.extend(skill_tags)

        # Also check top-level skills (OASF format - different structure)
        oasf_skills = record.get("skills", [])
        for skill in oasf_skills:
            if isinstance(skill, dict) and "tags" in skill:
                tags.extend(skill.get("tags", []))

        return tags

    def _convert_to_agent_record(self, oasf_record: dict) -> Optional[AgentRecord]:
        """
        Convert OASF record to internal AgentRecord format.

        OASF record has nested structure:
        - annotations["a2a.url"] contains URL
        - modules[0].data.card_data contains A2A AgentCard data
        """
        try:
            # Extract basic info
            name = oasf_record.get("name", "Unknown Agent")
            description = oasf_record.get("description", "")

            # Get URL from annotations or card_data
            annotations = oasf_record.get("annotations", {})
            url = annotations.get("a2a.url", "")

            # If not in annotations, try card_data
            if not url:
                card_data = self._get_card_data(oasf_record)
                url = card_data.get("url", "")

            if not url:
                logger.warning(f"Agent {name} has no URL, skipping")
                return None

            # Generate agent_id from name
            agent_id = name.replace(" ", "-").replace("_", "-").lower()

            # Extract skills from card_data
            card_data = self._get_card_data(oasf_record)
            skills = []
            card_skills = card_data.get("skills", [])
            for card_skill in card_skills:
                skill = AgentSkill(
                    id=card_skill.get("id", "unknown"),
                    name=card_skill.get("name", "Unknown Skill"),
                    description=card_skill.get("description", ""),
                    tags=card_skill.get("tags", []),
                    input_modes=card_data.get("defaultInputModes", ["text"])
                )
                skills.append(skill)

            # Create AgentRecord
            return AgentRecord(
                agent_id=agent_id,
                name=name,
                description=description,
                organization="unknown",
                url=url,
                capabilities=AgentCapabilities(skills=skills),
                performance_metrics=AgentPerformanceMetrics(
                    avg_latency_ms=1000,  # Default metrics
                    p95_latency_ms=2000,
                    success_rate=0.85,
                    throughput_rps=50
                ),
                last_heartbeat=datetime.utcnow(),
                ttl_seconds=3600
            )

        except Exception as e:
            logger.error(f"Failed to convert OASF record: {e}")
            return None
