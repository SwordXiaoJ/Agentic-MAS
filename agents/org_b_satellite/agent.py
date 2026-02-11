# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import random
import time
import logging
import aiohttp
import os
from typing import Dict, Any
from datetime import datetime

from shared.schemas import ClassificationResult, TopKPrediction

logger = logging.getLogger(__name__)


class SatelliteClassifierAgent:
    """
    Satellite/geospatial image classification agent (Org B).
    Specializes in landcover, urban planning, agricultural analysis.

    Supports two modes:
    1. Simulated (default): Fast, deterministic classification for testing
    2. LLM-powered: Uses litellm for intelligent classification

    Set USE_LLM=true in environment to enable LLM mode.
    """

    def __init__(self, agent_id: str = "org-b-satellite-clf-002"):
        self.agent_id = agent_id
        self.satellite_labels = [
            "urban",
            "forest",
            "water",
            "desert",
            "agricultural",
            "industrial",
            "residential"
        ]

        # Check if LLM mode is enabled
        self.use_llm = os.getenv("USE_LLM", "false").lower() in ("true", "1", "yes")
        self.llm = None

        if self.use_llm:
            try:
                from config.llm_config import create_llm
                self.llm = create_llm()
                logger.info(f"Satellite Agent initialized with LLM mode")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM, falling back to simulated mode: {e}")
                self.use_llm = False

    async def classify(self, request: Dict[str, Any]) -> ClassificationResult:
        """Classify satellite/aerial image"""
        start_time = time.time()

        # Download image if needed
        image_data = await self._get_image(request["image"])

        # Choose classification method
        if self.use_llm and self.llm:
            label, confidence = await self._classify_with_llm(request["prompt"], image_data)
        else:
            label, confidence = self._classify_simulated(request["prompt"])

        top_k = self._generate_top_k(label, confidence)
        latency_ms = int((time.time() - start_time) * 1000)

        return ClassificationResult(
            request_id=request["request_id"],
            agent_id=self.agent_id,
            label=label,
            confidence=confidence,
            top_k=top_k,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow()
        )

    def _classify_simulated(self, prompt: str) -> tuple[str, float]:
        """Simulated classification (fast, deterministic)."""
        prompt_lower = prompt.lower()

        if "urban" in prompt_lower or "city" in prompt_lower:
            return "urban", random.uniform(0.80, 0.95)
        elif "forest" in prompt_lower or "trees" in prompt_lower:
            return "forest", random.uniform(0.75, 0.92)
        elif "water" in prompt_lower or "ocean" in prompt_lower:
            return "water", random.uniform(0.85, 0.96)
        else:
            return random.choice(self.satellite_labels), random.uniform(0.70, 0.90)

    async def _classify_with_llm(self, prompt: str, image_data: bytes = None) -> tuple[str, float]:
        """LLM-powered vision classification using litellm directly."""
        import base64
        import litellm
        from config.llm_config import LLM_MODEL

        text_instruction = (
            f"You are a satellite and geospatial image classification expert.\n"
            f"Analyze this satellite/aerial image and classify what you see.\n"
            f"User request: {prompt}\n\n"
            f"Respond in this exact format (nothing else):\n"
            f"LABEL: <a concise 1-3 word classification label, e.g. 'urban area', 'farmland', 'forest'>\n"
            f"CONFIDENCE: <confidence score between 0.0 and 1.0>"
        )

        content = [{"type": "text", "text": text_instruction}]
        if image_data:
            b64 = base64.b64encode(image_data).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })

        try:
            response = await litellm.acompletion(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": content}],
                max_tokens=100,
            )
            llm_output = response.choices[0].message.content.strip()
            logger.info(f"LLM Vision Classification: {llm_output[:100]}")

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

    async def _get_image(self, image_source: Dict[str, Any]) -> bytes:
        """Download image from presigned URL, regular URL, or decode base64"""
        # Try presigned_url first, then regular url
        url = image_source.get("presigned_url") or image_source.get("url")
        if url:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.read()
        elif image_source.get("bytes"):
            import base64
            return base64.b64decode(image_source["bytes"])
        return b""

    def _generate_top_k(self, predicted_label: str, predicted_confidence: float) -> list:
        """Generate top-k predictions"""
        top_k = [
            TopKPrediction(label=predicted_label, confidence=predicted_confidence, rank=1)
        ]

        other_labels = [l for l in self.satellite_labels if l != predicted_label]
        random.shuffle(other_labels)

        remaining_confidence = 1.0 - predicted_confidence
        for i, label in enumerate(other_labels[:2]):
            conf = remaining_confidence * random.uniform(0.3, 0.7) if i == 0 else remaining_confidence * 0.3
            top_k.append(TopKPrediction(label=label, confidence=round(conf, 3), rank=i + 2))

        return top_k
