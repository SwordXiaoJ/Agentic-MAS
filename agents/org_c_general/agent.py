# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
General-purpose image classification agent using LangGraph workflow.

Workflow Steps:
1. Preprocess: Download and prepare image
2. Classify: Run LLM Vision inference
3. Postprocess: Rank and format results
"""

import random
import logging
import aiohttp
import os
import base64
from typing import Dict, Any, TypedDict, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage

from shared.schemas import ClassificationResult, TopKPrediction

logger = logging.getLogger(__name__)


class ClassificationState(TypedDict):
    """State maintained throughout the classification workflow"""
    request_id: str
    image_url: str
    prompt: str

    # Intermediate state
    image_data: bytes
    preprocessed: bool

    # Classification result
    label: str
    confidence: float
    top_k: list

    # Workflow messages
    messages: Annotated[list, add_messages]


class GeneralClassifierAgent:
    """
    General-purpose image classification agent using LangGraph workflow.

    Workflow: preprocess → classify → postprocess

    Supports two modes:
    1. Simulated (default): Fast classification for testing
    2. LLM-powered: Uses litellm Vision for intelligent classification

    Set USE_LLM=true in environment to enable LLM mode.
    """

    def __init__(self, agent_id: str = "org-c-general-clf-003"):
        self.agent_id = agent_id
        self.general_labels = [
            "dog", "cat", "person", "car", "food",
            "building", "tree", "animal", "indoor", "outdoor"
        ]

        # Check if LLM mode is enabled
        self.use_llm = os.getenv("USE_LLM", "false").lower() in ("true", "1", "yes")
        self.llm = None

        if self.use_llm:
            try:
                from config.llm_config import create_llm
                self.llm = create_llm()
                logger.info("General Agent initialized with LLM mode + LangGraph workflow")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM, falling back to simulated mode: {e}")
                self.use_llm = False

        # Build the LangGraph workflow
        self.graph = self._build_graph()
        logger.info(f"LangGraph workflow initialized: {self.agent_id}")

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(ClassificationState)

        # Add nodes
        workflow.add_node("preprocess", self._preprocess_node)
        workflow.add_node("classify", self._classify_node)
        workflow.add_node("postprocess", self._postprocess_node)

        # Define edges
        workflow.add_edge(START, "preprocess")
        workflow.add_edge("preprocess", "classify")
        workflow.add_edge("classify", "postprocess")
        workflow.add_edge("postprocess", END)

        return workflow.compile()

    async def _preprocess_node(self, state: ClassificationState) -> ClassificationState:
        """Node 1: Download and prepare image"""
        logger.info(f"[{state['request_id']}] Preprocessing: downloading image...")

        image_data = b""
        image_url = state.get("image_url", "")

        if image_url and not image_url.startswith("simulated://"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        image_data = await response.read()
                        logger.info(f"[{state['request_id']}] Downloaded image: {len(image_data)} bytes")
            except Exception as e:
                logger.error(f"[{state['request_id']}] Failed to download image: {e}")

        state["image_data"] = image_data
        state["preprocessed"] = True
        state["messages"].append(
            AIMessage(content=f"Image preprocessed: {len(image_data)} bytes")
        )

        return state

    async def _classify_node(self, state: ClassificationState) -> ClassificationState:
        """Node 2: Run classification (LLM Vision or simulated)"""
        logger.info(f"[{state['request_id']}] Classifying image...")

        image_data = state.get("image_data", b"")
        prompt = state.get("prompt", "")

        if self.use_llm and self.llm and image_data:
            label, confidence = await self._classify_with_llm(prompt, image_data)
        else:
            label, confidence = self._classify_simulated(prompt)

        state["label"] = label
        state["confidence"] = confidence
        state["messages"].append(
            AIMessage(content=f"Classification: {label} ({confidence:.2f})")
        )

        return state

    async def _postprocess_node(self, state: ClassificationState) -> ClassificationState:
        """Node 3: Generate top-k predictions and format results"""
        logger.info(f"[{state['request_id']}] Postprocessing results...")

        label = state["label"]
        confidence = state["confidence"]

        # Generate top-k predictions
        top_k = [{"label": label, "confidence": confidence, "rank": 1}]

        other_labels = [l for l in self.general_labels if l != label]
        random.shuffle(other_labels)

        remaining_confidence = 1.0 - confidence
        for i, other_label in enumerate(other_labels[:2]):
            conf = remaining_confidence * random.uniform(0.3, 0.7) if i == 0 else remaining_confidence * 0.3
            top_k.append({"label": other_label, "confidence": round(conf, 3), "rank": i + 2})

        state["top_k"] = top_k
        state["messages"].append(
            AIMessage(content=f"Results formatted: {len(top_k)} predictions")
        )

        return state

    def _classify_simulated(self, prompt: str) -> tuple[str, float]:
        """Simulated classification (fast, for testing)"""
        prompt_lower = prompt.lower()
        label = random.choice(self.general_labels)
        confidence = random.uniform(0.70, 0.90)

        for keyword in self.general_labels:
            if keyword in prompt_lower:
                label = keyword
                confidence = random.uniform(0.80, 0.92)
                break

        return label, confidence

    async def _classify_with_llm(self, prompt: str, image_data: bytes) -> tuple[str, float]:
        """LLM Vision classification using litellm"""
        import litellm
        from config.llm_config import LLM_MODEL

        text_instruction = (
            f"You are a general-purpose image classification expert.\n"
            f"Analyze this image and classify what you see.\n"
            f"User request: {prompt}\n\n"
            f"Respond in this exact format (nothing else):\n"
            f"LABEL: <a concise 1-3 word classification label, e.g. 'dog', 'sports car', 'beach sunset'>\n"
            f"CONFIDENCE: <confidence score between 0.0 and 1.0>"
        )

        content = [{"type": "text", "text": text_instruction}]

        if image_data and len(image_data) > 0:
            b64 = base64.b64encode(image_data).decode("utf-8")
            logger.info(f"Sending image to LLM: {len(image_data)} bytes")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        else:
            logger.warning("NO IMAGE DATA - LLM will only see text prompt!")

        try:
            response = await litellm.acompletion(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": content}],
                max_tokens=100,
            )
            llm_output = response.choices[0].message.content.strip()
            logger.info(f"LLM Vision Classification: {llm_output[:100]}")

            # Parse response - free-form label
            label = "unclassified"
            confidence = 0.5

            for line in llm_output.split("\n"):
                if line.upper().startswith("LABEL:"):
                    label = line.split(":", 1)[1].strip().lower()
                elif line.upper().startswith("CONFIDENCE:"):
                    try:
                        confidence = float(line.split(":", 1)[1].strip())
                    except Exception:
                        pass

            return label, confidence
        except Exception as e:
            logger.error(f"LLM vision classification failed: {e}, falling back to simulated")
            return self._classify_simulated(prompt)

    async def classify(self, request: Dict[str, Any]) -> ClassificationResult:
        """Main entry point - runs the LangGraph workflow"""
        request_id = request.get("request_id", f"req-{datetime.utcnow().timestamp()}")

        # Get image URL
        image_data = request.get("image", {})
        image_url = (
            image_data.get("presigned_url") or
            image_data.get("url") or
            "simulated://image.jpg"
        )

        prompt = request.get("prompt", "Classify this image")

        logger.info(f"[{request_id}] Starting LangGraph classification workflow...")

        # Initialize state
        initial_state: ClassificationState = {
            "request_id": request_id,
            "image_url": image_url,
            "prompt": prompt,
            "image_data": b"",
            "preprocessed": False,
            "label": "",
            "confidence": 0.0,
            "top_k": [],
            "messages": [HumanMessage(content=prompt)]
        }

        # Run the workflow
        start_time = datetime.utcnow()
        final_state = await self.graph.ainvoke(initial_state)
        end_time = datetime.utcnow()

        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        # Log workflow steps
        logger.info(f"[{request_id}] Workflow completed in {latency_ms}ms")
        for msg in final_state["messages"]:
            if hasattr(msg, 'content'):
                logger.debug(f"  - {msg.content}")

        # Return ClassificationResult
        return ClassificationResult(
            request_id=request_id,
            agent_id=self.agent_id,
            label=final_state["label"],
            confidence=final_state["confidence"],
            top_k=[TopKPrediction(**pred) for pred in final_state["top_k"]],
            latency_ms=latency_ms,
            timestamp=datetime.utcnow()
        )
