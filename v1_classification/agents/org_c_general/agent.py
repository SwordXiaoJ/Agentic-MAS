# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
General-purpose image classification agent using LlamaIndex Workflow.

Workflow Steps:
1. Preprocess: Download and prepare image
2. Classify: Run LLM Vision inference
3. Postprocess: Rank and format results

LlamaIndex Workflow: https://docs.llamaindex.ai/en/stable/module_guides/workflow/
"""

import random
import logging
import aiohttp
import os
import base64
from typing import Dict, Any
from datetime import datetime

from llama_index.core.workflow import (
    Workflow,
    Event,
    StartEvent,
    StopEvent,
    step,
    Context,
)

from shared.schemas import ClassificationResult, TopKPrediction

# IOA Observe decorators
try:
    from ioa_observe.sdk.decorators import agent as observe_agent
    _observe_available = True
except ImportError:
    def observe_agent(*args, **kwargs):
        return args[0] if args and callable(args[0]) else lambda f: f
    _observe_available = False

logger = logging.getLogger(__name__)


# ============================================================================
# Workflow Events
# ============================================================================

class PreprocessDoneEvent(Event):
    """Emitted after image download and preprocessing."""
    request_id: str
    prompt: str
    image_data: bytes = b""


class ClassifyDoneEvent(Event):
    """Emitted after classification (LLM or simulated)."""
    request_id: str
    label: str
    confidence: float
    llm_top_k: list = []


# ============================================================================
# LlamaIndex Classification Workflow
# ============================================================================

class ClassificationWorkflow(Workflow):
    """
    Sequential classification workflow: preprocess → classify → postprocess.

    Uses LlamaIndex Workflow's event-driven step pattern where each step
    receives an event and emits the next event in the chain.
    """

    def __init__(self, agent_ref, **kwargs):
        super().__init__(**kwargs)
        self.agent_ref = agent_ref

    @step
    async def preprocess(self, ctx: Context, ev: StartEvent) -> PreprocessDoneEvent:
        """Step 1: Download and prepare image."""
        request_id = ev.request_id
        image_url = ev.image_url
        prompt = ev.prompt

        logger.info(f"[{request_id}] Preprocessing: downloading image...")

        image_data = b""
        if image_url and not image_url.startswith("simulated://"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        image_data = await response.read()
                        logger.info(f"[{request_id}] Downloaded image: {len(image_data)} bytes")
            except Exception as e:
                logger.error(f"[{request_id}] Failed to download image: {e}")

        logger.info(f"[{request_id}] Image preprocessed: {len(image_data)} bytes")

        return PreprocessDoneEvent(
            request_id=request_id,
            prompt=prompt,
            image_data=image_data,
        )

    @step
    async def classify(self, ctx: Context, ev: PreprocessDoneEvent) -> ClassifyDoneEvent:
        """Step 2: Run classification (LLM Vision or simulated)."""
        logger.info(f"[{ev.request_id}] Classifying image...")

        llm_top_k = []
        if self.agent_ref.use_llm and self.agent_ref.llm and ev.image_data:
            label, confidence, llm_top_k = await self.agent_ref._classify_with_llm(ev.prompt, ev.image_data)
        else:
            label, confidence = self.agent_ref._classify_simulated(ev.prompt)

        logger.info(f"[{ev.request_id}] Classification: {label} ({confidence:.2f})")

        return ClassifyDoneEvent(
            request_id=ev.request_id,
            label=label,
            confidence=confidence,
            llm_top_k=llm_top_k,
        )

    @step
    async def postprocess(self, ctx: Context, ev: ClassifyDoneEvent) -> StopEvent:
        """Step 3: Generate top-k predictions and format results."""
        logger.info(f"[{ev.request_id}] Postprocessing results...")

        label = ev.label
        confidence = ev.confidence

        # Use LLM top-k if available, otherwise generate fallback predictions
        if ev.llm_top_k:
            top_k = [{"label": lbl, "confidence": conf, "rank": i + 1}
                     for i, (lbl, conf) in enumerate(ev.llm_top_k)]
        else:
            top_k = [{"label": label, "confidence": confidence, "rank": 1}]
            other_labels = [l for l in self.agent_ref.general_labels if l != label]
            random.shuffle(other_labels)
            remaining_confidence = 1.0 - confidence
            for i, other_label in enumerate(other_labels[:2]):
                conf = remaining_confidence * random.uniform(0.3, 0.7) if i == 0 else remaining_confidence * 0.3
                top_k.append({"label": other_label, "confidence": round(conf, 3), "rank": i + 2})

        logger.info(f"[{ev.request_id}] Results formatted: {len(top_k)} predictions")

        return StopEvent(result={
            "label": label,
            "confidence": confidence,
            "top_k": top_k,
        })


# ============================================================================
# Agent Class
# ============================================================================

class GeneralClassifierAgent:
    """
    General-purpose image classification agent using LlamaIndex Workflow.

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
        self.use_llm = os.getenv("USE_LLM", "true").lower() in ("true", "1", "yes")
        self.llm = None

        if self.use_llm:
            try:
                from config.llm_config import create_llm
                self.llm = create_llm()
                logger.info("General Agent initialized with LLM mode + LlamaIndex Workflow")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM, falling back to simulated mode: {e}")
                self.use_llm = False

        # Build the LlamaIndex Workflow
        self.workflow = ClassificationWorkflow(agent_ref=self)
        logger.info(f"LlamaIndex Workflow initialized: {self.agent_id}")

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

    async def _classify_with_llm(self, prompt: str, image_data: bytes) -> tuple[str, float, list]:
        """LLM Vision classification using litellm"""
        import litellm
        from config.llm_config import LLM_MODEL

        text_instruction = (
            f"You are a general-purpose image classification expert.\n"
            f"Analyze this image and classify what you see.\n"
            f"User request: {prompt}\n\n"
            f"Respond in this exact format (nothing else):\n"
            f"LABEL1: <most likely classification> | CONFIDENCE1: <score 0.0-1.0>\n"
            f"LABEL2: <second most likely> | CONFIDENCE2: <score 0.0-1.0>\n"
            f"LABEL3: <third most likely> | CONFIDENCE3: <score 0.0-1.0>"
        )

        content = [{"type": "text", "text": text_instruction}]

        if image_data and len(image_data) > 0:
            b64 = base64.b64encode(image_data).decode("utf-8")
            mime = "image/png" if image_data[:4] == b'\x89PNG' else "image/jpeg"
            logger.info(f"Sending image to LLM: {len(image_data)} bytes")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
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

            # Parse response - free-form label with top-k
            label = "unclassified"
            confidence = 0.5
            top_k = []

            for line in llm_output.split("\n"):
                line_upper = line.upper().strip()
                if "|" in line and "LABEL" in line_upper and "CONFIDENCE" in line_upper:
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

            return label, confidence, top_k
        except Exception as e:
            logger.error(f"LLM vision classification failed: {e}, falling back to simulated")
            label, confidence = self._classify_simulated(prompt)
            return label, confidence, []

    @observe_agent(name="general_classifier", description="General image classification via LlamaIndex Workflow", protocol="A2A")
    async def classify(self, request: Dict[str, Any]) -> ClassificationResult:
        """Main entry point - runs the LlamaIndex Workflow."""
        request_id = request.get("request_id", f"req-{datetime.utcnow().timestamp()}")

        # Get image URL
        image_data = request.get("image", {})
        image_url = (
            image_data.get("presigned_url") or
            image_data.get("url") or
            "simulated://image.jpg"
        )

        prompt = request.get("prompt", "Classify this image")

        logger.info(f"[{request_id}] Starting LlamaIndex classification workflow...")

        start_time = datetime.utcnow()

        # Run the LlamaIndex Workflow
        result = await self.workflow.run(
            request_id=request_id,
            image_url=image_url,
            prompt=prompt,
        )

        end_time = datetime.utcnow()
        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.info(f"[{request_id}] Workflow completed in {latency_ms}ms")

        # Return ClassificationResult
        return ClassificationResult(
            request_id=request_id,
            agent_id=self.agent_id,
            label=result["label"],
            confidence=result["confidence"],
            top_k=[TopKPrediction(**pred) for pred in result["top_k"]],
            latency_ms=latency_ms,
            timestamp=datetime.utcnow()
        )
