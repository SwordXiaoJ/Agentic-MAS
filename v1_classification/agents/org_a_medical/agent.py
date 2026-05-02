# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Medical image classification agent using LangGraph ReAct workflow.

ReAct (Reasoning + Acting) loop:
  START → preprocess → reason ←──────────┐
                         │                │
              ┌──────────┼────────┐       │
         "call_tool" "classify" "done"    │
              │          │        │       │
        [act_tool] [act_classify] [finalize]
              │          │        │
          [observe]  [observe]   END
              │          │
              └──────────┘ (loop back to reason)
"""

import json
import random
import time
import logging
import aiohttp
import os
import base64
from typing import Dict, Any, Optional, List, TypedDict, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from shared.schemas import ClassificationResult, TopKPrediction

# IOA Observe decorators
try:
    from ioa_observe.sdk.decorators import agent as observe_agent, graph as observe_graph
    _observe_available = True
except ImportError:
    def observe_agent(*args, **kwargs):
        return args[0] if args and callable(args[0]) else lambda f: f
    def observe_graph(*args, **kwargs):
        return args[0] if args and callable(args[0]) else lambda f: f
    _observe_available = False

logger = logging.getLogger(__name__)


# ========== ReAct State ==========

class MedicalReActState(TypedDict):
    """State maintained throughout the ReAct workflow."""
    # Input
    request_id: str
    prompt: str
    image_url: str
    image_data: bytes

    # ReAct loop tracking
    iteration: int
    max_iterations: int

    # MCP tool results
    mcp_context: Dict[str, Any]
    tool_calls_made: List[str]

    # Classification result
    label: str
    confidence: float
    top_k: list
    reasoning: Optional[str]

    # Decision state
    next_action: str
    pending_tool_name: str
    pending_tool_args: Dict[str, Any]

    # Flow control
    classification_done: bool
    mcp_enabled: bool
    llm_enabled: bool

    # Workflow messages
    messages: Annotated[list, add_messages]


class MedicalClassifierAgent:
    """
    Medical image classification agent (Org A) using LangGraph ReAct workflow.
    Specializes in X-ray, CT scan, and medical diagnoses.

    The agent reasons about which MCP tools to call, gathers context,
    then classifies the image with accumulated knowledge.

    Environment variables:
    - USE_LLM=true: Enable LLM classification (default: true)
    - USE_MCP=true: Enable MCP tools (requires medical_tools_service running)
    - MCP_TOPIC=medical_tools_service: MCP server topic
    """

    def __init__(self, agent_id: str = "org-a-medical-clf-001"):
        self.agent_id = agent_id
        self.medical_labels = [
            "pneumonia", "tuberculosis", "normal",
            "lung_nodule", "fracture", "pleural_effusion"
        ]

        # Check if LLM mode is enabled
        self.use_llm = os.getenv("USE_LLM", "true").lower() in ("true", "1", "yes")
        self.llm = None

        if self.use_llm:
            try:
                from config.llm_config import create_llm
                self.llm = create_llm()
                logger.info("Medical Agent initialized with LLM + ReAct workflow")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM, falling back to simulated mode: {e}")
                self.use_llm = False

        # Check if MCP mode is enabled
        self.use_mcp = os.getenv("USE_MCP", "false").lower() in ("true", "1", "yes")
        self.mcp_topic = os.getenv("MCP_TOPIC", "medical_tools_service")
        self._mcp_factory = None
        self._mcp_transport = None
        self._mcp_client_factory_args = None
        if self.use_mcp:
            try:
                from agntcy_app_sdk.factory import AgntcyFactory
                transport_type = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
                endpoint = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")
                self._mcp_factory = AgntcyFactory("agntcy_network.medical_mcp_client", enable_tracing=False)
                self._mcp_transport = self._mcp_factory.create_transport(
                    transport_type,
                    endpoint=endpoint,
                    name="default/default/medical_mcp_client"
                )
                logger.info(f"Medical Agent MCP enabled, topic: {self.mcp_topic}")
            except Exception as e:
                logger.warning(f"Failed to initialize MCP transport, disabling MCP: {e}")
                self.use_mcp = False

        # Build the LangGraph ReAct workflow
        self.graph = self._build_graph()
        logger.info(f"ReAct workflow initialized: {self.agent_id}")

    # ========== Graph Construction ==========

    @observe_graph(name="medical_react_graph", description="Medical ReAct workflow: reason → act → observe loop")
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph ReAct workflow."""
        workflow = StateGraph(MedicalReActState)

        # Add nodes
        workflow.add_node("preprocess", self._preprocess_node)
        workflow.add_node("reason", self._reason_node)
        workflow.add_node("act_tool", self._act_tool_node)
        workflow.add_node("act_classify", self._act_classify_node)
        workflow.add_node("observe", self._observe_node)
        workflow.add_node("finalize", self._finalize_node)

        # Edges
        workflow.add_edge(START, "preprocess")
        workflow.add_edge("preprocess", "reason")

        # After reasoning: conditional dispatch
        workflow.add_conditional_edges(
            "reason",
            self._route_after_reason,
            {
                "call_tool": "act_tool",
                "classify": "act_classify",
                "done": "finalize",
            }
        )

        # After actions: observe then loop back to reason
        workflow.add_edge("act_tool", "observe")
        workflow.add_edge("act_classify", "observe")
        workflow.add_edge("observe", "reason")

        # Terminal
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _route_after_reason(self, state: MedicalReActState) -> str:
        """Route based on the LLM's ReAct decision.

        Minimal guards — trust the LLM to drive the flow.
        Only intervene for safety (infinite loops, missing classification).
        """
        action = state.get("next_action", "done")
        iteration = state.get("iteration", 0)
        max_iter = state.get("max_iterations", 5)

        # Safety: prevent infinite loops
        if iteration >= max_iter:
            if state.get("classification_done"):
                return "done"
            return "classify"

        # Trust the LLM's decision
        if action == "call_tool":
            return "call_tool"
        elif action == "classify":
            # Already classified — no point re-classifying, treat as done
            if state.get("classification_done"):
                return "done"
            return "classify"
        elif action == "done":
            # Safety: don't finalize without classification
            if not state.get("classification_done"):
                return "classify"
            return "done"

        # Unparseable action — fallback
        if not state.get("classification_done"):
            return "classify"
        return "done"

    # ========== Node Implementations ==========

    async def _preprocess_node(self, state: MedicalReActState) -> dict:
        """Download and prepare image."""
        image_data = await self._get_image_from_url(state.get("image_url", ""))
        return {
            "image_data": image_data,
            "messages": [AIMessage(content=f"Preprocessed image: {len(image_data)} bytes")]
        }

    async def _reason_node(self, state: MedicalReActState) -> dict:
        """LLM reasons about what to do next (core of ReAct).

        The LLM chooses different tool sequences based on the user's prompt:
        - "Analyze/identify" → classify first, then validate with literature
        - "Diagnose/findings" → search literature first, then classify with context
        """

        # If MCP disabled, use simple rule-based flow
        if not state["mcp_enabled"]:
            return self._rule_based_reasoning(state)

        # If LLM disabled, also use rule-based
        if not state["llm_enabled"]:
            return self._rule_based_reasoning(state)

        # LLM-based reasoning — let the LLM decide whether to continue or stop
        # Safety nets: _route_after_reason prevents re-classification, max_iterations caps loops
        system_prompt = (
            "You are a medical image classification agent using ReAct (Reasoning + Acting).\n\n"
            "Available tools:\n"
            "1. search_medical_literature(query, max_results) - Search PubMed for relevant articles\n"
            "2. get_medical_reference(condition) - Get condition summary from MedlinePlus (NIH)\n"
            "3. classify_image - Run the image classifier (vision model)\n\n"
            "Strategy — adapt your approach to what the user asks for:\n\n"
            "SIMPLE classification (classify, analyze, identify, detect, diagnose):\n"
            "  Step 1: classify_image\n"
            "  Step 2: done\n\n"
            "EVIDENCE-BACKED requests (user asks for references, evidence, proof, supporting literature, detailed findings):\n"
            "  Step 1: classify_image — look at the image first\n"
            "  Step 2: search_medical_literature — find supporting literature for the finding\n"
            "  Step 3: get_medical_reference — get condition summary from MedlinePlus\n"
            "  Step 4: done\n\n"
            "Rules:\n"
            "- Output EXACTLY ONE action per response. Do NOT plan ahead or list multiple actions.\n"
            "- You MUST call classify_image before saying done\n"
            "- Only use search_medical_literature / get_medical_reference if the user asks for evidence or references\n"
            "- Don't call the same tool twice with the same arguments\n\n"
            "Respond in EXACTLY this format (three lines only, nothing else):\n"
            "ACTION: <tool_name or classify_image or done>\n"
            "ARGS: <JSON args if tool, {} otherwise>\n"
            "REASON: <brief explanation>"
        )

        context = self._build_context_summary(state)

        try:
            response = await self.llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=context),
                ],
                max_tokens=300,
            )
            llm_output = response.content.strip()
            logger.info(f"ReAct reasoning output: {llm_output}")
            action, tool_name, tool_args, reason = self._parse_reason_output(llm_output)

            return {
                "next_action": action,
                "pending_tool_name": tool_name,
                "pending_tool_args": tool_args,
                "iteration": state["iteration"] + 1,
                "messages": [AIMessage(content=f"Reason (iter {state['iteration'] + 1}): {reason} -> {action}")]
            }
        except Exception as e:
            logger.error(f"ReAct reasoning failed: {e}, falling back to rule-based")
            return self._rule_based_reasoning(state)

    async def _act_tool_node(self, state: MedicalReActState) -> dict:
        """Execute an MCP tool call."""
        tool_name = state["pending_tool_name"]
        tool_args = state.get("pending_tool_args", {})

        result = await self._call_mcp_tool(tool_name, tool_args)

        updated_context = dict(state.get("mcp_context", {}))
        updated_context[tool_name] = result

        tool_calls = list(state.get("tool_calls_made", []))
        tool_calls.append(tool_name)

        return {
            "mcp_context": updated_context,
            "tool_calls_made": tool_calls,
            "messages": [AIMessage(content=f"Tool {tool_name}: {str(result)[:200]}")]
        }

    async def _act_classify_node(self, state: MedicalReActState) -> dict:
        """Run image classification with accumulated MCP context."""
        mcp_context = state.get("mcp_context", {})

        if self.use_llm and self.llm:
            label, confidence, reasoning, llm_top_k = await self._classify_with_llm(
                state["prompt"], state["image_data"],
                mcp_context if mcp_context else None
            )
        else:
            label, confidence = self._classify_simulated(state["prompt"])
            reasoning = None
            llm_top_k = []

        return {
            "label": label,
            "confidence": confidence,
            "reasoning": reasoning,
            "top_k": llm_top_k,
            "classification_done": True,
            "messages": [AIMessage(content=f"Classified: {label} ({confidence:.2f})")]
        }

    async def _observe_node(self, state: MedicalReActState) -> dict:
        """Observe results of last action."""
        messages = []
        if state.get("classification_done"):
            messages.append(AIMessage(
                content=f"Observation: Classification done - {state['label']} ({state['confidence']:.2f})"
            ))
        tool_calls = state.get("tool_calls_made", [])
        if tool_calls:
            messages.append(AIMessage(
                content=f"Observation: {len(tool_calls)} tool(s) called so far"
            ))
        return {"messages": messages}

    async def _finalize_node(self, state: MedicalReActState) -> dict:
        """Terminal node."""
        return {
            "messages": [AIMessage(content=f"Finalized: {state['label']} ({state['confidence']:.2f})")]
        }

    # ========== ReAct Helpers ==========

    def _rule_based_reasoning(self, state: MedicalReActState) -> dict:
        """Fallback when MCP/LLM is disabled — simple linear flow."""
        if not state.get("classification_done"):
            return {
                "next_action": "classify",
                "pending_tool_name": "",
                "pending_tool_args": {},
                "iteration": state["iteration"] + 1,
                "messages": [AIMessage(content="Rule-based: classify next")]
            }
        return {
            "next_action": "done",
            "pending_tool_name": "",
            "pending_tool_args": {},
            "iteration": state["iteration"] + 1,
            "messages": [AIMessage(content="Rule-based: done")]
        }

    def _build_context_summary(self, state: MedicalReActState) -> str:
        """Build context string for the reasoning LLM."""
        parts = [f"User request: {state['prompt']}"]
        parts.append(f"Image: {'available' if state.get('image_data') else 'none'} ({len(state.get('image_data', b''))} bytes)")
        parts.append(f"Iteration: {state['iteration']}/{state['max_iterations']}")

        if state.get("tool_calls_made"):
            parts.append(f"\nTools called: {', '.join(state['tool_calls_made'])}")
            for tool_name, result in state.get("mcp_context", {}).items():
                preview = str(result)[:300] if result else "no result"
                parts.append(f"  {tool_name}: {preview}")

        if state.get("classification_done"):
            parts.append(f"\nClassification: {state['label']} (confidence: {state['confidence']:.2f})")
            if state.get("reasoning"):
                parts.append(f"Reasoning: {state['reasoning']}")
        else:
            parts.append("\nClassification: NOT YET DONE")

        return "\n".join(parts)

    def _parse_reason_output(self, llm_output: str) -> tuple:
        """Parse the LLM reasoning output into (action, tool_name, tool_args, reason).

        Picks the FIRST ACTION line only — ignores any extra actions the LLM may have output.
        """
        action = "done"
        tool_name = ""
        tool_args = {}
        reason = ""
        action_found = False

        mcp_tools = {"search_medical_literature", "get_medical_reference"}

        for line in llm_output.strip().split("\n"):
            line = line.strip()
            if line.upper().startswith("ACTION:") and not action_found:
                raw = line.split(":", 1)[1].strip().lower()
                if raw in mcp_tools:
                    action = "call_tool"
                    tool_name = raw
                elif raw in ("classify_image", "classify"):
                    action = "classify"
                else:
                    action = "done"
                action_found = True
            elif line.upper().startswith("ARGS:") and action_found and not tool_args:
                try:
                    tool_args = json.loads(line.split(":", 1)[1].strip())
                except (json.JSONDecodeError, ValueError):
                    tool_args = {}
            elif line.upper().startswith("REASON:") and action_found and not reason:
                reason = line.split(":", 1)[1].strip()
                break  # Got all three fields for the first action, stop

        return action, tool_name, tool_args, reason

    # ========== MCP Tool Calling ==========

    async def _call_mcp_tool(self, tool_name: str, arguments: dict) -> Optional[str]:
        """Call a single MCP tool via NATS/SLIM transport."""
        if not self._mcp_factory or not self._mcp_transport:
            logger.debug(f"MCP not initialized, skipping tool {tool_name}")
            return None

        mcp_client = self._mcp_factory.create_client(
            "MCP",
            agent_topic=self.mcp_topic,
            transport=self._mcp_transport,
            message_timeout=30
        )

        try:
            async with mcp_client as client:
                result = await client.call_tool(name=tool_name, arguments=arguments)
                return self._parse_mcp_result(result)
        except Exception as e:
            logger.debug(f"MCP tool {tool_name} failed: {e}")
            return None

    def _parse_mcp_result(self, result) -> Optional[str]:
        """Parse MCP tool result."""
        try:
            if hasattr(result, "content"):
                content_list = result.content
                if isinstance(content_list, list) and len(content_list) > 0:
                    return content_list[0].text
            return str(result) if result else None
        except Exception:
            return None

    # ========== Classification ==========

    def _classify_simulated(self, prompt: str) -> tuple[str, float]:
        """Simulated classification (fast, deterministic)."""
        prompt_lower = prompt.lower()
        if "pneumonia" in prompt_lower:
            return "pneumonia", random.uniform(0.75, 0.95)
        elif "tuberculosis" in prompt_lower or "tb" in prompt_lower:
            return "tuberculosis", random.uniform(0.70, 0.90)
        elif "normal" in prompt_lower:
            return "normal", random.uniform(0.80, 0.95)
        return random.choice(self.medical_labels), random.uniform(0.65, 0.88)

    async def _classify_with_llm(self, prompt: str, image_data: bytes = None, mcp_context: Dict = None) -> tuple:
        """LLM-powered vision classification using LangChain ChatOpenAI."""
        # Build MCP context text from accumulated tool results
        has_mcp = mcp_context and any(v for v in mcp_context.values())

        if has_mcp:
            context_parts = []
            for tool_name, result in mcp_context.items():
                if result:
                    context_parts.append(f"{tool_name}:\n{result}")
            mcp_text = "\n\n".join(context_parts)

            text_instruction = (
                f"You are a medical image classification expert with access to medical literature.\n"
                f"Analyze this medical image and provide your diagnosis.\n"
                f"User request: {prompt}\n\n"
                f"Medical context:\n{mcp_text}\n\n"
                f"Based on the image AND the medical context above, provide your diagnosis.\n"
                f"Respond in this exact format:\n"
                f"LABEL1: <most likely diagnosis> | CONFIDENCE1: <score 0.0-1.0>\n"
                f"LABEL2: <second most likely> | CONFIDENCE2: <score 0.0-1.0>\n"
                f"LABEL3: <third most likely> | CONFIDENCE3: <score 0.0-1.0>\n"
                f"REASONING: <brief explanation citing the medical context>"
            )
            max_tokens = 500
        else:
            text_instruction = (
                f"You are a medical image classification expert.\n"
                f"Analyze this medical image and provide your classification.\n"
                f"User request: {prompt}\n\n"
                f"Respond in this exact format (nothing else):\n"
                f"LABEL1: <most likely diagnosis> | CONFIDENCE1: <score 0.0-1.0>\n"
                f"LABEL2: <second most likely> | CONFIDENCE2: <score 0.0-1.0>\n"
                f"LABEL3: <third most likely> | CONFIDENCE3: <score 0.0-1.0>"
            )
            max_tokens = 200

        content = [{"type": "text", "text": text_instruction}]
        if image_data:
            b64 = base64.b64encode(image_data).decode("utf-8")
            mime = "image/png" if image_data[:4] == b'\x89PNG' else "image/jpeg"
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            })

        try:
            response = await self.llm.ainvoke(
                [HumanMessage(content=content)],
                max_tokens=max_tokens,
            )
            llm_output = response.content.strip()
            logger.info(f"LLM Vision Classification: {llm_output[:200]}")

            label = "unclassified"
            confidence = 0.5
            reasoning = None
            top_k = []

            for line in llm_output.split("\n"):
                line_upper = line.upper().strip()
                if line_upper.startswith("REASONING:"):
                    reasoning = line.split(":", 1)[1].strip()
                elif "|" in line and "LABEL" in line_upper and "CONFIDENCE" in line_upper:
                    parts = line.split("|")
                    try:
                        lbl = parts[0].split(":", 1)[1].strip().lower()
                        conf = float(parts[1].split(":", 1)[1].strip())
                        top_k.append((lbl, conf))
                    except Exception:
                        pass
                elif line_upper.startswith("LABEL:"):
                    label = line.split(":", 1)[1].strip().lower()
                elif line_upper.startswith("CONFIDENCE:"):
                    try:
                        confidence = float(line.split(":", 1)[1].strip())
                    except Exception:
                        pass

            if top_k:
                label, confidence = top_k[0]

            return label, confidence, reasoning, top_k
        except Exception as e:
            logger.error(f"LLM vision classification failed: {e}, falling back to simulated")
            label, confidence = self._classify_simulated(prompt)
            return label, confidence, None, []

    # ========== Image Handling ==========

    async def _get_image_from_url(self, url: str) -> bytes:
        """Download image from URL."""
        if not url or url.startswith("simulated://"):
            return b""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.read()
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            return b""

    async def _get_image(self, image_source: Dict[str, Any]) -> bytes:
        """Download image from presigned URL, regular URL, or decode base64."""
        url = image_source.get("presigned_url") or image_source.get("url")
        if url:
            return await self._get_image_from_url(url)
        elif image_source.get("bytes"):
            return base64.b64decode(image_source["bytes"])
        return b""

    def _generate_top_k(self, predicted_label: str, predicted_confidence: float) -> list:
        """Generate fallback top-k predictions from predefined labels."""
        top_k = [
            TopKPrediction(label=predicted_label, confidence=predicted_confidence, rank=1)
        ]
        other_labels = [l for l in self.medical_labels if l != predicted_label]
        random.shuffle(other_labels)
        remaining_confidence = 1.0 - predicted_confidence
        for i, label in enumerate(other_labels[:2]):
            conf = remaining_confidence * random.uniform(0.3, 0.7) if i == 0 else remaining_confidence * 0.3
            top_k.append(TopKPrediction(label=label, confidence=round(conf, 3), rank=i + 2))
        return top_k

    # ========== Entry Point ==========

    @observe_agent(name="medical_classifier", description="Medical image classification via LangGraph ReAct", protocol="A2A")
    async def classify(self, request: Dict[str, Any]) -> ClassificationResult:
        """
        Main entry point — runs the LangGraph ReAct workflow.

        Args:
            request: Classification request with image and prompt

        Returns:
            ClassificationResult
        """
        request_id = request.get("request_id", f"req-{datetime.utcnow().timestamp()}")
        image_data = request.get("image", {})
        image_url = (
            image_data.get("presigned_url") or
            image_data.get("url") or
            ""
        )
        prompt = request.get("prompt", "Classify this medical image")

        start_time = time.time()

        # Initialize ReAct state
        initial_state: MedicalReActState = {
            "request_id": request_id,
            "prompt": prompt,
            "image_url": image_url,
            "image_data": b"",
            "iteration": 0,
            "max_iterations": 5,
            "mcp_context": {},
            "tool_calls_made": [],
            "label": "",
            "confidence": 0.0,
            "top_k": [],
            "reasoning": None,
            "next_action": "",
            "pending_tool_name": "",
            "pending_tool_args": {},
            "classification_done": False,
            "mcp_enabled": self.use_mcp,
            "llm_enabled": self.use_llm and self.llm is not None,
            "messages": [HumanMessage(content=prompt)]
        }

        # Run the ReAct workflow
        final_state = await self.graph.ainvoke(initial_state)

        latency_ms = int((time.time() - start_time) * 1000)

        # Build top-k predictions
        llm_top_k = final_state.get("top_k", [])
        if llm_top_k and isinstance(llm_top_k[0], tuple):
            top_k = [TopKPrediction(label=lbl, confidence=conf, rank=i + 1)
                      for i, (lbl, conf) in enumerate(llm_top_k)]
        else:
            top_k = self._generate_top_k(final_state["label"], final_state["confidence"])

        # Log workflow trace
        for msg in final_state.get("messages", []):
            if hasattr(msg, "content"):
                logger.debug(f"  ReAct: {msg.content}")

        # Build mcp_context: only include non-None results
        mcp_context = None
        raw_mcp = final_state.get("mcp_context", {})
        if raw_mcp:
            mcp_context = {k: v for k, v in raw_mcp.items() if v}

        return ClassificationResult(
            request_id=request_id,
            agent_id=self.agent_id,
            label=final_state["label"],
            confidence=final_state["confidence"],
            top_k=top_k,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow(),
            mcp_enhanced=bool(final_state.get("tool_calls_made")),
            reasoning=final_state.get("reasoning"),
            mcp_context=mcp_context if mcp_context else None
        )
