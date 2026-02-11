"""
Static agent discovery with hardcoded agent list.
Similar to lungo coffee trading system approach.
"""
from typing import List
from datetime import datetime, timedelta
from shared.discovery.base import AgentDiscovery
from shared.schemas.agent_record import (
    AgentRecord,
    AgentCapabilities,
    AgentSkill,
    AgentPerformanceMetrics,
    AgentConstraints,
    DiscoveryQuery
)


class StaticAgentDiscovery(AgentDiscovery):
    """
    Hardcoded agent discovery for simplified setup.

    Agents are defined in code, no ADS needed.
    Good for MVP, testing, and development.
    """

    def __init__(self):
        self.agents: List[AgentRecord] = []
        self._initialize_agents()

    def _initialize_agents(self):
        """
        Define hardcoded agent list.

        NOTE: When switching to ADS, this list moves to agent self-registration.
        """
        # Medical Agent (Org A)
        self.agents.append(AgentRecord(
            agent_id="org-a-medical-clf-001",
            name="Medical Image Classifier - Organization A",
            description="An AI agent specialized in classifying medical images including X-rays, CT scans, and MRI images for diagnostic assistance",
            organization="hospital-a",
            url="http://localhost:9001",
            capabilities=AgentCapabilities(
                skills=[AgentSkill(
                    id="image_classification",
                    name="Medical Image Classification",
                    description="Classify medical images (X-ray, CT, MRI) for diagnosis",
                    tags=["medical", "xray", "ct_scan", "pneumonia", "tuberculosis", "diagnosis"],
                    input_modes=["image/jpeg", "image/png", "image/dicom"]
                )]
            ),
            performance_metrics=AgentPerformanceMetrics(
                avg_latency_ms=1200,
                p95_latency_ms=2500,
                success_rate=0.92,
                throughput_rps=50
            ),
            last_heartbeat=datetime.utcnow(),
            ttl_seconds=3600  # Static agents don't expire
        ))

        # Satellite Agent (Org B)
        self.agents.append(AgentRecord(
            agent_id="org-b-satellite-clf-001",
            name="Satellite Image Classifier - Organization B",
            description="An AI agent specialized in classifying satellite and aerial imagery for landcover analysis, urban planning, and geospatial applications",
            organization="geo-analytics-b",
            url="http://localhost:9002",
            capabilities=AgentCapabilities(
                skills=[AgentSkill(
                    id="image_classification",
                    name="Satellite Image Classification",
                    description="Classify satellite and aerial imagery for landcover analysis",
                    tags=["satellite", "geospatial", "landcover", "urban", "forest", "water"],
                    input_modes=["image/jpeg", "image/png", "image/tiff"]
                )]
            ),
            performance_metrics=AgentPerformanceMetrics(
                avg_latency_ms=1500,
                p95_latency_ms=3000,
                success_rate=0.88,
                throughput_rps=30
            ),
            last_heartbeat=datetime.utcnow(),
            ttl_seconds=3600
        ))

        # General Agent (Org C)
        self.agents.append(AgentRecord(
            agent_id="org-c-general-clf-001",
            name="General Image Classifier - Organization C",
            description="An AI agent for general-purpose image classification, covering objects, scenes, activities, and everyday imagery",
            organization="ai-services-c",
            url="http://localhost:9003",
            capabilities=AgentCapabilities(
                skills=[AgentSkill(
                    id="image_classification",
                    name="General Image Classification",
                    description="Classify general images: objects, scenes, activities",
                    tags=["general", "objects", "scenes", "imagenet"],
                    input_modes=["image/jpeg", "image/png"]
                )]
            ),
            performance_metrics=AgentPerformanceMetrics(
                avg_latency_ms=1000,
                p95_latency_ms=2000,
                success_rate=0.85,
                throughput_rps=100
            ),
            last_heartbeat=datetime.utcnow(),
            ttl_seconds=3600
        ))

        # LangGraph Agent (Org D)
        self.agents.append(AgentRecord(
            agent_id="org-d-langgraph-clf-001",
            name="LangGraph Classifier - Organization D",
            description="LangGraph-based multi-step workflow for general image classification including animals, vehicles, food, and objects",
            organization="ai-research-d",
            url="http://localhost:9004",
            capabilities=AgentCapabilities(
                skills=[AgentSkill(
                    id="image_classification",
                    name="LangGraph Image Classification",
                    description="LangGraph-based multi-step workflow for image classification",
                    tags=["langgraph", "stateful", "workflow", "general", "animals", "vehicles", "food", "objects"],
                    input_modes=["image/jpeg", "image/png"]
                )]
            ),
            performance_metrics=AgentPerformanceMetrics(
                avg_latency_ms=1800,
                p95_latency_ms=3500,
                success_rate=0.90,
                throughput_rps=40
            ),
            last_heartbeat=datetime.utcnow(),
            ttl_seconds=3600
        ))

    async def discover(self, query: DiscoveryQuery) -> List[AgentRecord]:
        """
        Discover agents by matching tags.

        Args:
            query: Discovery query with tags to match

        Returns:
            Ranked list of agents (by tag match score + performance)
        """
        candidates = []

        for agent in self.agents:
            # Extract agent tags
            agent_tags = set()
            for skill in agent.capabilities.skills:
                if skill.id == query.skill_id:
                    agent_tags.update(skill.tags)

            # Calculate tag match score
            query_tags = set(query.tags) if query.tags else set()
            if not query_tags:
                # No tags specified, return all agents
                tag_match_score = 1.0
            else:
                matching_tags = agent_tags.intersection(query_tags)
                tag_match_score = len(matching_tags) / len(query_tags) if query_tags else 0

            # Skip if no match
            if tag_match_score == 0 and query_tags:
                continue

            # Calculate overall score (tag_match * success_rate / latency_penalty)
            success_rate = agent.performance_metrics.success_rate if agent.performance_metrics else 0.5
            avg_latency = agent.performance_metrics.avg_latency_ms if agent.performance_metrics else 1000
            latency_penalty = avg_latency / 1000  # Normalize to seconds

            score = tag_match_score * success_rate / max(latency_penalty, 0.1)

            candidates.append((score, agent))

        # Sort by score (descending) and return top N
        candidates.sort(key=lambda x: x[0], reverse=True)
        ranked_agents = [agent for _, agent in candidates[:query.limit]]

        return ranked_agents

    async def connect(self):
        """No connection needed for static discovery"""
        pass

    async def close(self):
        """No cleanup needed for static discovery"""
        pass
