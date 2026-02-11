#!/usr/bin/env python3
# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
LangGraph-based Planner Agent with A2A Integration.

Architecture:
- Planner: LLM-based intent classification, rule-based routing
- Verifier: Result verification (confidence gate, ensemble voting)
- A2A protocol for agent communication
"""

import os
import logging
from typing import Dict, Any, List, TypedDict, Annotated, Literal
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from a2a.types import AgentCard, AgentCapabilities, AgentSkill

from shared.schemas import (
    ClassificationRequest,
    ClassificationResult,
    RouteDecision,
    SelectedAgent,
    ExecutionStrategy,
    AgentRole,
    DiscoveryQuery,
    VerificationStatus,
    VerificationRecommendation,
    AgentRecord
)
from shared.discovery import AgentDiscovery
from services.verifier.main import Verifier
from services.planner.tools import send_message_to_agent, broadcast_message_to_agents, A2AAgentError
from config.llm_config import create_llm, LLM_MODEL

logger = logging.getLogger(__name__)

MAX_REPLANS = 3


# ========== LLM-based Structured Outputs ==========

class AgentSelection(BaseModel):
    """Structured output for LLM-based agent selection using agent descriptions"""
    selected_agent_ids: List[str] = Field(
        description="List of agent_ids selected, ordered by relevance (most relevant first)"
    )
    reasoning: str = Field(description="Brief explanation of why these agents were selected")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")


# RoutingDecision removed - using rule-based logic instead of LLM

class ShouldContinue(BaseModel):
    """Structured output for reflection decision (like Auction Supervisor)"""
    should_continue: bool = Field(description="Whether to continue processing (replan) or end")
    reason: str = Field(description="Reason for the decision")
    mismatch_detected: bool = Field(default=False, description="True if the image content does not match the user's prompt domain (e.g., non-medical image sent with medical prompt)")


# ========== State Schema ==========

class PlannerState(TypedDict):
    """State maintained throughout the planning workflow"""
    # Input
    request: ClassificationRequest
    request_id: str

    # Iteration tracking
    iteration: int
    start_time: float

    # LLM-based analysis
    intent: Dict[str, Any]  # IntentClassification result

    # Discovery results
    discovered_agents: List[AgentRecord]

    # Routing decision
    route_decision: RouteDecision

    # Execution results
    results: List[ClassificationResult]

    # Verification
    verification_status: str  # "PASS", "FAIL", "INCONCLUSIVE"
    verification_report: Dict[str, Any]
    verification_recommendation: str
    mismatch_warning: str  # Prompt-image mismatch warning message

    # Final response
    final_response: Dict[str, Any]

    # Workflow messages for debugging
    messages: Annotated[list, add_messages]

    # Error tracking
    error: str


class LangGraphPlannerAgent:
    """
    LangGraph-based Planner with LLM integration and A2A communication.

    Workflow Nodes:
    1. supervisor_node     - LLM-based intent classification (like Lungo's supervisor)
    2. discover_agents     - Find matching agents based on intent
    3. route_decision      - LLM-based routing strategy decision
    4. execute_tasks       - Execute via A2A protocol
    5. reflection_node     - LLM-based result verification
    6. check_status        - Check if should replan
    7. finalize_response   - Format final response

    Conditional Edges:
    - After route_decision: simple_route vs ensemble_route
    - After check_status: success vs replan vs human_review
    """

    def __init__(self, discovery: AgentDiscovery):
        self.discovery = discovery
        self.verifier = Verifier()

        # Initialize LLM for intelligent routing
        try:
            self.llm = create_llm()
            logger.info(f"LLM initialized: {LLM_MODEL}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            self.llm = None

        # Build the LangGraph workflow
        self.graph = self._build_graph()

        logger.info("LangGraph Planner initialized with LLM + A2A")

    def _build_graph(self) -> StateGraph:
        """Build the planning workflow graph"""

        workflow = StateGraph(PlannerState)

        # Add nodes (following Lungo's Supervisor pattern)
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("discover_agents", self._discover_agents_node)
        workflow.add_node("route_decision", self._route_decision_node)
        workflow.add_node("route_simple", self._route_simple_node)
        workflow.add_node("route_ensemble", self._route_ensemble_node)
        workflow.add_node("execute_tasks", self._execute_tasks_node)
        workflow.add_node("reflection", self._reflection_node)
        workflow.add_node("check_status", self._check_status_node)
        workflow.add_node("finalize_response", self._finalize_response_node)
        workflow.add_node("handle_error", self._handle_error_node)

        # Define edges (similar to Lungo's ExchangeGraph)
        workflow.add_edge(START, "supervisor")
        workflow.add_edge("supervisor", "discover_agents")
        workflow.add_edge("discover_agents", "route_decision")

        # Conditional: simple vs ensemble routing
        workflow.add_conditional_edges(
            "route_decision",
            self._should_use_ensemble,
            {
                "simple": "route_simple",
                "ensemble": "route_ensemble",
                "error": "handle_error"
            }
        )

        workflow.add_edge("route_simple", "execute_tasks")
        workflow.add_edge("route_ensemble", "execute_tasks")
        workflow.add_edge("execute_tasks", "reflection")
        workflow.add_edge("reflection", "check_status")

        # Conditional: success vs replan vs human review
        workflow.add_conditional_edges(
            "check_status",
            self._decide_next_action,
            {
                "success": "finalize_response",
                "replan": "supervisor",  # Loop back for next iteration
                "human_review": "finalize_response",
                "max_replans": "finalize_response",
                "error": "handle_error"
            }
        )

        workflow.add_edge("finalize_response", END)
        workflow.add_edge("handle_error", END)

        return workflow.compile()

    # ========== Node Implementations ==========

    async def _supervisor_node(self, state: PlannerState) -> PlannerState:
        """
        Supervisor node: LLM-based agent selection using agent card descriptions.

        Replaces the old domain classification + tag-based discovery with a single
        LLM call that reads agent descriptions/skills and selects the best match.
        """
        logger.info(f"[{state['request_id']}] Iteration {state['iteration']}: Supervisor selecting agents...")

        request = state["request"]
        prompt = request.prompt

        # Step 1: Get all available agents
        import asyncio
        try:
            all_agents = await asyncio.wait_for(
                self.discovery.discover_all(limit=10), timeout=5.0
            )
        except Exception as e:
            logger.error(f"Failed to discover agents: {e}")
            all_agents = []

        if not all_agents:
            state["error"] = "NO_AGENTS_AVAILABLE"
            state["intent"] = {"domain": "unknown", "confidence": 0.0, "reasoning": "No agents found"}
            state["discovered_agents"] = []
            return state

        # Step 2: Use LLM to select agents based on descriptions
        if self.llm:
            try:
                agent_catalog = self._build_agent_catalog(all_agents)

                selection_llm = create_llm().with_structured_output(
                    AgentSelection, strict=True
                )

                sys_msg = SystemMessage(
                    content=f"""You are an intelligent agent router for the AGNTCY image classification network.

Given a user's image classification request, select the most suitable agent(s) from the available catalog.

Available Agents:
{agent_catalog}

INSTRUCTIONS:
- Select 1-3 agents most relevant to the user's request
- Order them by relevance (most relevant first)
- Consider the agent's description, skills, and tags
- If uncertain, prefer agents with broader capabilities (e.g., general-purpose)
- Return agent_ids exactly as listed above
"""
                )

                user_msg = HumanMessage(content=f"User request: {prompt}")

                result = await selection_llm.ainvoke([sys_msg, user_msg])

                # Filter agents to only the selected ones, maintaining LLM's order
                selected_agents = []
                for agent_id in result.selected_agent_ids:
                    for agent in all_agents:
                        if agent.agent_id == agent_id:
                            selected_agents.append(agent)
                            break

                # Fallback: if LLM returned invalid IDs, use all agents
                if not selected_agents:
                    logger.warning("LLM returned no valid agent_ids, using all agents")
                    selected_agents = all_agents

                state["discovered_agents"] = selected_agents
                state["intent"] = {
                    "domain": "llm_selected",
                    "confidence": result.confidence,
                    "reasoning": result.reasoning
                }

                state["messages"].append(
                    AIMessage(content=f"Selected {len(selected_agents)} agents: {[a.agent_id for a in selected_agents]} - {result.reasoning}")
                )
                logger.info(f"LLM selected agents: {[a.agent_id for a in selected_agents]}")

            except Exception as e:
                logger.error(f"LLM agent selection failed: {e}")
                state["intent"] = self._fallback_intent_classification(prompt)
                state["discovered_agents"] = []
        else:
            state["intent"] = self._fallback_intent_classification(prompt)
            state["discovered_agents"] = []

        return state

    def _build_agent_catalog(self, agents: List[AgentRecord]) -> str:
        """Build a text catalog of available agents for LLM prompting."""
        catalog_lines = []
        for agent in agents:
            line = f"- agent_id: {agent.agent_id}\n"
            line += f"  name: {agent.name}\n"
            line += f"  description: {agent.description}\n"

            for skill in agent.capabilities.skills:
                line += f"  skill: {skill.name}\n"
                line += f"  skill_description: {skill.description}\n"
                line += f"  tags: {', '.join(skill.tags)}\n"

            catalog_lines.append(line)

        return "\n".join(catalog_lines)

    def _fallback_intent_classification(self, prompt: str) -> Dict[str, Any]:
        """Fallback keyword-based intent classification"""
        prompt_lower = prompt.lower()

        if any(kw in prompt_lower for kw in ["xray", "x-ray", "ct", "mri", "medical", "pneumonia", "diagnosis"]):
            return {"domain": "medical", "confidence": 0.7, "reasoning": "Keyword match: medical terms"}
        elif any(kw in prompt_lower for kw in ["satellite", "aerial", "landsat", "urban", "forest"]):
            return {"domain": "satellite", "confidence": 0.7, "reasoning": "Keyword match: satellite terms"}
        else:
            return {"domain": "general", "confidence": 0.5, "reasoning": "Default fallback"}

    async def _discover_agents_node(self, state: PlannerState) -> PlannerState:
        """Discover agents - acts as fallback when LLM selection already populated agents."""

        # If LLM already selected agents in supervisor_node, skip tag-based discovery
        if state.get("discovered_agents"):
            logger.info(f"[{state['request_id']}] Agents already selected by LLM, skipping tag-based discovery")
            return state

        # Fallback: tag-based discovery (for when LLM is unavailable)
        logger.info(f"[{state['request_id']}] Fallback: tag-based discovery for domain: {state['intent']['domain']}...")

        intent = state["intent"]
        request = state["request"]

        domain_to_tags = {
            "medical": ["medical", "xray", "diagnosis"],
            "satellite": ["satellite", "geospatial", "aerial"],
            "general": ["general", "objects", "scenes"]
        }
        tags = domain_to_tags.get(intent["domain"], ["general"])

        if request.constraints.preferred_domains:
            tags.extend(request.constraints.preferred_domains)

        query = DiscoveryQuery(
            skill_id="image_classification",
            tags=tags,
            min_success_rate=0.7,
            max_latency_ms=request.constraints.timeout_ms * 2,
            limit=5
        )

        import asyncio
        try:
            discovered = await asyncio.wait_for(
                self.discovery.discover(query), timeout=5.0
            )
            state["discovered_agents"] = discovered
            state["messages"].append(
                AIMessage(content=f"Fallback: Discovered {len(discovered)} agents for tags: {tags}")
            )
            if not discovered:
                state["error"] = "NO_AGENTS_AVAILABLE"
        except Exception as e:
            logger.error(f"Error discovering agents: {e}")
            state["error"] = str(e)
            state["discovered_agents"] = []

        return state

    def _route_decision_node(self, state: PlannerState) -> PlannerState:
        """
        Rule-based routing strategy decision.

        No LLM needed - simple rules are sufficient:
        - First attempt: use single_best (fast)
        - After failure: use ensemble (more reliable)
        - High confidence requirement: use ensemble
        """
        logger.info(f"[{state['request_id']}] Deciding routing strategy (rule-based)...")

        request = state["request"]
        iteration = state["iteration"]
        agents = state.get("discovered_agents", [])

        # Simple rule-based decision (no LLM call needed)
        # This saves ~4 seconds per request!
        reason = ""
        if iteration > 1:
            reason = "Previous attempt failed, using ensemble for reliability"
        elif request.constraints.min_confidence > 0.85:
            reason = "High confidence required, using ensemble"
        elif len(agents) >= 3:
            reason = "Multiple agents available, single_best is efficient"
        else:
            reason = "First attempt, using single_best for speed"

        state["messages"].append(
            AIMessage(content=f"Routing: rule-based decision - {reason}")
        )

        return state

    def _route_simple_node(self, state: PlannerState) -> PlannerState:
        """Create simple routing decision (single best agent)"""
        logger.info(f"[{state['request_id']}] Creating simple route...")

        agents = state["discovered_agents"]
        request = state["request"]

        selected_agents = []

        if agents:
            primary = agents[0]
            selected_agents.append(SelectedAgent(
                agent_id=primary.agent_id,
                name=primary.name,
                url=primary.url,
                role=AgentRole.PRIMARY,
                selection_score=0.95,
                selection_reason="LLM selected: Highest ranked from discovery"
            ))

        if len(agents) > 1:
            secondary = agents[1]
            selected_agents.append(SelectedAgent(
                agent_id=secondary.agent_id,
                name=secondary.name,
                url=secondary.url,
                role=AgentRole.SECONDARY,
                selection_score=0.85,
                selection_reason="Fallback agent"
            ))

        route_decision = RouteDecision(
            request_id=request.request_id,
            selected_agents=selected_agents,
            strategy=ExecutionStrategy.SINGLE_BEST
        )

        state["route_decision"] = route_decision
        state["messages"].append(
            AIMessage(content=f"Simple route: {len(selected_agents)} agents selected")
        )

        return state

    def _route_ensemble_node(self, state: PlannerState) -> PlannerState:
        """Create ensemble routing decision (multiple agents)"""
        logger.info(f"[{state['request_id']}] Creating ensemble route...")

        agents = state["discovered_agents"]
        request = state["request"]

        selected_agents = []

        for i, agent in enumerate(agents[:3]):
            selected_agents.append(SelectedAgent(
                agent_id=agent.agent_id,
                name=agent.name,
                url=agent.url,
                role=AgentRole.ENSEMBLE,
                selection_score=0.9 - (i * 0.1),
                selection_reason=f"LLM ensemble: Agent {i+1}"
            ))

        route_decision = RouteDecision(
            request_id=request.request_id,
            selected_agents=selected_agents,
            strategy=ExecutionStrategy.PARALLEL_ENSEMBLE
        )

        state["route_decision"] = route_decision
        state["messages"].append(
            AIMessage(content=f"Ensemble route: {len(selected_agents)} agents in parallel")
        )

        return state

    @staticmethod
    def _make_agent_card(name: str, url: str) -> AgentCard:
        """Create a properly-formed AgentCard for A2A communication"""
        return AgentCard(
            name=name,
            url=url,
            version="1.0.0",
            description=f"Agent {name}",
            capabilities=AgentCapabilities(streaming=False),
            skills=[AgentSkill(
                id="image_classification",
                name="Image Classification",
                description=f"Classification by {name}",
                tags=["classification"]
            )],
            defaultInputModes=["text", "image/jpeg"],
            defaultOutputModes=["text", "application/json"],
        )

    async def _execute_tasks_node(self, state: PlannerState) -> PlannerState:
        """Execute tasks via A2A protocol (async)"""
        logger.info(f"[{state['request_id']}] Executing tasks via A2A...")

        request = state["request"]
        route_decision = state["route_decision"]

        task_payload = {
            "request_id": request.request_id,
            "image": request.image.model_dump(),
            "prompt": request.prompt,
            "constraints": request.constraints.model_dump()
        }

        results = []

        try:
            if route_decision.strategy == ExecutionStrategy.SINGLE_BEST:
                # Try primary, fall back to secondary
                primary = route_decision.selected_agents[0]
                agent_card = self._make_agent_card(primary.name or primary.agent_id, primary.url)

                try:
                    result = await send_message_to_agent(
                        agent_card,
                        request.prompt,
                        task_payload
                    )

                    if result.get("status") == "success":
                        results.append(self._parse_classification_result(result, primary.agent_id))

                except A2AAgentError as e:
                    logger.error(f"Primary agent failed: {e}")

                    # Try secondary
                    if len(route_decision.selected_agents) > 1:
                        secondary = route_decision.selected_agents[1]
                        secondary_card = self._make_agent_card(secondary.name or secondary.agent_id, secondary.url)
                        try:
                            result = await send_message_to_agent(
                                secondary_card,
                                request.prompt,
                                task_payload
                            )
                            if result.get("status") == "success":
                                results.append(self._parse_classification_result(result, secondary.agent_id))
                        except A2AAgentError as e2:
                            logger.error(f"Secondary agent failed: {e2}")

            elif route_decision.strategy == ExecutionStrategy.PARALLEL_ENSEMBLE:
                # Execute in parallel using broadcast
                agent_cards = [
                    self._make_agent_card(agent.name or agent.agent_id, agent.url)
                    for agent in route_decision.selected_agents
                ]

                batch_results = await broadcast_message_to_agents(
                    agent_cards,
                    request.prompt,
                    task_payload
                )

                for i, result in enumerate(batch_results):
                    if result.get("status") == "success":
                        agent_id = route_decision.selected_agents[i].agent_id
                        results.append(self._parse_classification_result(result, agent_id))

            state["results"] = results
            state["messages"].append(
                AIMessage(content=f"Execution complete: {len(results)} results via A2A")
            )

            if not results:
                state["error"] = "ALL_AGENTS_FAILED"

        except Exception as e:
            logger.error(f"Error executing tasks: {e}")
            state["error"] = str(e)
            state["results"] = []

        return state

    def _parse_classification_result(self, response: Dict[str, Any], agent_id: str) -> ClassificationResult:
        """Parse A2A response into ClassificationResult"""
        from shared.schemas import TopKPrediction
        try:
            import json
            response_text = response.get("response", "")

            # Try to parse as JSON
            if response_text.startswith("{"):
                data = json.loads(response_text)
                return ClassificationResult(**data)
            else:
                # Parse text response (format: "Label: xxx\nConfidence: 0.xx\n...")
                label = response_text.strip()
                confidence = 0.8

                for line in response_text.split("\n"):
                    if line.startswith("Label:"):
                        label = line.split(":", 1)[1].strip()
                    elif line.startswith("Confidence:"):
                        try:
                            confidence = float(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass

                return ClassificationResult(
                    request_id=str(uuid4()),
                    agent_id=agent_id,
                    label=label,
                    confidence=confidence,
                    top_k=[TopKPrediction(label=label, confidence=confidence, rank=1)],
                    latency_ms=0
                )
        except Exception as e:
            logger.error(f"Error parsing result: {e}")
            return ClassificationResult(
                request_id=str(uuid4()),
                agent_id=agent_id,
                label="parse_error",
                confidence=0.0,
                top_k=[TopKPrediction(label="parse_error", confidence=0.0, rank=1)],
                latency_ms=0
            )

    async def _reflection_node(self, state: PlannerState) -> PlannerState:
        """
        Reflection node: Following Auction Supervisor pattern.

        1. Use Verifier for objective quality checks
        2. Use LLM with structured output to decide if we should continue (replan)
        """
        logger.info(f"[{state['request_id']}] Reflecting on results...")

        results = state.get("results", [])
        request = state["request"]

        if not results:
            state["verification_status"] = "FAIL"
            state["verification_recommendation"] = "replan"
            state["verification_report"] = {}
            state["messages"].append(AIMessage(content="Reflection: No results to verify"))
            return state

        # Step 1: Use Verifier for objective quality checks
        verification_report = None
        try:
            verification_report = await self.verifier.verify(
                results=results,
                request=request
            )
            state["verification_report"] = {
                "results_count": len(results),
                "status": verification_report.status.value,
                "tests": [t.test_name for t in verification_report.tests_performed],
                "notes": verification_report.notes
            }
        except Exception as e:
            logger.error(f"Verifier failed: {e}")
            state["verification_report"] = {"error": str(e)}

        # Step 2: Use LLM with structured output for reflection decision (like Auction Supervisor)
        if self.llm:
            try:
                # Create structured output LLM (streaming=False required)
                reflection_llm = create_llm().with_structured_output(
                    ShouldContinue, strict=True
                )

                # Build concise context (Lungo style - simple and clear)
                results_summary = "\n".join([
                    f"- {r.agent_id}: {r.label} ({r.confidence:.2f})"
                    for r in results
                ])

                verifier_status = verification_report.status.value if verification_report else "N/A"
                verifier_notes = verification_report.notes if verification_report else ""

                # Simplified prompt (Lungo style)
                sys_msg = SystemMessage(
                    content=f"""You are evaluating image classification results.

Request: {request.prompt}
Required confidence: {request.constraints.min_confidence}
Iteration: {state['iteration']}/{MAX_REPLANS}

Results:
{results_summary}

Verifier: {verifier_status} - {verifier_notes}

Decide: should we CONTINUE (retry with different strategy) or STOP (accept current results)?
- STOP (should_continue=false): Results are good enough or max iterations reached
- CONTINUE (should_continue=true): Results are poor and we can retry

IMPORTANT - Mismatch detection:
If agent results indicate the image does NOT belong to the domain requested in the prompt
(e.g., a medical classifier labels the image as "non-medical image", or a satellite classifier
labels a medical image as "unknown"), this is a PROMPT-IMAGE MISMATCH.
In this case: set should_continue=false AND mismatch_detected=true.
Retrying will NOT help because the image content genuinely does not match the prompt.
Include a clear explanation in 'reason' about what the image actually appears to be vs what was requested."""
                )

                response = await reflection_llm.ainvoke([sys_msg])

                if response and hasattr(response, 'should_continue'):
                    if response.mismatch_detected:
                        # Prompt-image mismatch: stop immediately, accept results with warning
                        state["verification_status"] = "PASS"
                        state["verification_recommendation"] = "success"
                        state["mismatch_warning"] = response.reason
                        logger.info(f"Mismatch detected: {response.reason}")
                    elif response.should_continue and state['iteration'] < MAX_REPLANS:
                        state["verification_status"] = "FAIL"
                        state["verification_recommendation"] = "replan"
                    else:
                        state["verification_status"] = "PASS"
                        state["verification_recommendation"] = "success"

                    state["messages"].append(
                        AIMessage(content=f"Reflection: {'Mismatch' if response.mismatch_detected else 'Continue' if response.should_continue else 'Complete'} - {response.reason}")
                    )
                    logger.info(f"Reflection decision: should_continue={response.should_continue}, mismatch={response.mismatch_detected}, reason={response.reason}")
                else:
                    # Fallback if structured output fails
                    self._fallback_reflection(state, results, request, verification_report)

            except Exception as e:
                logger.error(f"LLM reflection failed: {e}")
                self._fallback_reflection(state, results, request, verification_report)
        else:
            self._fallback_reflection(state, results, request, verification_report)

        return state

    def _fallback_reflection(self, state: PlannerState, results: List, request: ClassificationRequest, verification_report):
        """Fallback rule-based reflection when LLM fails"""
        max_confidence = max(r.confidence for r in results) if results else 0
        verifier_passed = verification_report and verification_report.status.value == "PASS" if verification_report else False

        if max_confidence >= request.constraints.min_confidence or verifier_passed:
            state["verification_status"] = "PASS"
            state["verification_recommendation"] = "success"
            state["messages"].append(AIMessage(content=f"Reflection (fallback): PASS - confidence {max_confidence:.2f}"))
        else:
            state["verification_status"] = "FAIL"
            state["verification_recommendation"] = "replan"
            state["messages"].append(AIMessage(content=f"Reflection (fallback): FAIL - confidence {max_confidence:.2f} below threshold"))

    def _check_status_node(self, state: PlannerState) -> PlannerState:
        """Check verification status and decide next action"""
        logger.info(f"[{state['request_id']}] Checking status...")

        status = state.get("verification_status", "FAIL")
        recommendation = state.get("verification_recommendation", "replan")
        iteration = state["iteration"]

        if status == "PASS":
            state["messages"].append(AIMessage(content="Status: SUCCESS"))
        elif recommendation == "human_review":
            state["messages"].append(AIMessage(content="Status: NEEDS_HUMAN_REVIEW"))
        elif iteration >= MAX_REPLANS:
            state["messages"].append(AIMessage(content="Status: MAX_REPLANS_EXCEEDED"))
        else:
            state["messages"].append(AIMessage(content=f"Status: REPLAN (iteration {iteration + 1})"))
            state["iteration"] = iteration + 1

        return state

    def _finalize_response_node(self, state: PlannerState) -> PlannerState:
        """Finalize and format response"""
        logger.info(f"[{state['request_id']}] Finalizing response...")

        status = state.get("verification_status", "FAIL")
        results = state.get("results", [])
        verification_report = state.get("verification_report", {})
        iteration = state["iteration"]
        start_time = state["start_time"]

        total_latency = (datetime.utcnow().timestamp() - start_time) * 1000

        if status == "PASS" and results:
            final_result = results[0] if len(results) == 1 else self.verifier.get_ensemble_result(results)

            response = {
                "status": "COMPLETED",
                "result": final_result.model_dump(),
                "intent": state.get("intent", {}),
                "verification": {
                    "status": status,
                    "tests": [],
                    "notes": "LLM-verified"
                },
                "iterations": iteration,
                "total_latency_ms": int(total_latency),
                "workflow_messages": [msg.content for msg in state["messages"]]
            }

            # Add mismatch warning if detected
            mismatch_warning = state.get("mismatch_warning")
            if mismatch_warning:
                response["mismatch_warning"] = mismatch_warning
                response["status"] = "COMPLETED_WITH_WARNING"
        elif state.get("verification_recommendation") == "human_review":
            response = {
                "status": "NEEDS_REVIEW",
                "result": results[0].model_dump() if results else None,
                "intent": state.get("intent", {}),
                "verification": verification_report,
                "iterations": iteration,
                "message": "LLM reflection: Human review required.",
                "workflow_messages": [msg.content for msg in state["messages"]]
            }
        elif iteration >= MAX_REPLANS:
            response = {
                "status": "INCONCLUSIVE",
                "error": "MAX_REPLANS_EXCEEDED",
                "intent": state.get("intent", {}),
                "message": f"Failed to get verified result after {MAX_REPLANS} attempts",
                "iterations": iteration,
                "workflow_messages": [msg.content for msg in state["messages"]]
            }
        else:
            response = {
                "status": "FAILED",
                "error": state.get("error", "UNKNOWN_ERROR"),
                "intent": state.get("intent", {}),
                "iterations": iteration,
                "workflow_messages": [msg.content for msg in state["messages"]]
            }

        state["final_response"] = response
        state["messages"].append(AIMessage(content=f"Response finalized: {response['status']}"))

        return state

    def _handle_error_node(self, state: PlannerState) -> PlannerState:
        """Handle errors"""
        logger.error(f"[{state['request_id']}] Error: {state.get('error', 'Unknown')}")

        state["final_response"] = {
            "status": "FAILED",
            "error": state.get("error", "UNKNOWN_ERROR"),
            "intent": state.get("intent", {}),
            "iterations": state["iteration"],
            "workflow_messages": [msg.content for msg in state["messages"]]
        }

        return state

    # ========== Conditional Edge Functions ==========

    def _should_use_ensemble(self, state: PlannerState) -> Literal["simple", "ensemble", "error"]:
        """Decide if we should use ensemble or simple routing"""

        if state.get("error"):
            return "error"

        if not state.get("discovered_agents"):
            return "error"

        request = state["request"]
        iteration = state["iteration"]

        # Use ensemble if:
        # - Previous iteration failed (iteration > 1)
        # - High confidence required
        # - Multiple good agents available
        if (iteration > 1 or
            request.constraints.min_confidence > 0.85 or
            len(state["discovered_agents"]) >= 3):
            return "ensemble"

        return "simple"

    def _decide_next_action(self, state: PlannerState) -> Literal["success", "replan", "human_review", "max_replans", "error"]:
        """Decide what to do after verification"""

        if state.get("error"):
            return "error"

        status = state.get("verification_status", "FAIL")
        recommendation = state.get("verification_recommendation", "replan")
        iteration = state["iteration"]

        if status == "PASS":
            return "success"
        elif recommendation == "human_review":
            return "human_review"
        elif iteration >= MAX_REPLANS:
            return "max_replans"
        else:
            return "replan"

    # ========== Public API ==========

    async def plan_and_execute(self, request: ClassificationRequest) -> Dict[str, Any]:
        """
        Main entry point: plan and execute classification request.

        This runs the entire LangGraph workflow with LLM-based routing.
        """
        logger.info(f"Starting LangGraph planning for request {request.request_id}")

        # Initialize state
        initial_state: PlannerState = {
            "request": request,
            "request_id": request.request_id,
            "iteration": 1,
            "start_time": datetime.utcnow().timestamp(),
            "intent": {},
            "discovered_agents": [],
            "route_decision": None,
            "results": [],
            "verification_status": "",
            "verification_report": {},
            "verification_recommendation": "",
            "final_response": {},
            "messages": [HumanMessage(content=request.prompt)],
            "error": ""
        }

        # Run the graph
        try:
            final_state = await self.graph.ainvoke(initial_state)

            # Log workflow
            logger.info(f"Planning completed for {request.request_id}")
            for msg in final_state["messages"]:
                logger.debug(f"  - {msg.content}")

            return final_state["final_response"]

        except Exception as e:
            logger.error(f"Error in LangGraph planning: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "iterations": 1
            }
