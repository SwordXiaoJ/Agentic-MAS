# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import random
import time
import logging
import aiohttp
import os
from typing import Dict, Any, Optional
from datetime import datetime

from shared.schemas import ClassificationResult, TopKPrediction

logger = logging.getLogger(__name__)


class MedicalClassifierAgent:
    """
    Medical image classification agent (Org A).
    Specializes in X-ray, CT scan, and medical diagnoses.

    Supports three modes:
    1. Simulated (default): Fast, deterministic classification for testing
    2. LLM-powered: Uses litellm for intelligent classification
    3. MCP-enhanced: Uses external tools via MCP protocol (Lungo style)

    Environment variables:
    - USE_LLM=true: Enable LLM classification
    - USE_MCP=true: Enable MCP tools (requires medical_tools_service running)
    - MCP_TOPIC=medical_tools_service: MCP server topic
    """

    def __init__(self, agent_id: str = "org-a-medical-clf-001"):
        self.agent_id = agent_id
        self.medical_labels = [
            "pneumonia",
            "tuberculosis",
            "normal",
            "lung_nodule",
            "fracture",
            "pleural_effusion"
        ]

        # Check if LLM mode is enabled
        self.use_llm = os.getenv("USE_LLM", "false").lower() in ("true", "1", "yes")
        self.llm = None

        if self.use_llm:
            try:
                from config.llm_config import create_llm
                self.llm = create_llm()
                logger.info(f"Medical Agent initialized with LLM mode")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM, falling back to simulated mode: {e}")
                self.use_llm = False

        # Check if MCP mode is enabled (Lungo style via NATS/SLIM)
        self.use_mcp = os.getenv("USE_MCP", "false").lower() in ("true", "1", "yes")
        self.mcp_topic = os.getenv("MCP_TOPIC", "medical_tools_service")
        if self.use_mcp:
            logger.info(f"Medical Agent MCP enabled, topic: {self.mcp_topic}")

    async def classify(self, request: Dict[str, Any]) -> ClassificationResult:
        """
        Classify medical image.

        Args:
            request: Classification request with image and prompt

        Returns:
            ClassificationResult
        """
        start_time = time.time()

        # Download image if needed (for augmentation tests)
        image_data = await self._get_image(request["image"])

        # Optionally enhance with MCP tools (e.g., search medical literature)
        mcp_context = None
        if self.use_mcp:
            mcp_context = await self._enhance_with_mcp(request["prompt"])

        # Choose classification method
        reasoning = None
        if self.use_llm and self.llm:
            label, confidence, reasoning = await self._classify_with_llm(request["prompt"], image_data, mcp_context)
        else:
            label, confidence = self._classify_simulated(request["prompt"])

        # Generate top-k predictions
        top_k = self._generate_top_k(label, confidence)

        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)

        # MCP enhancement adds reasoning to the result
        mcp_enhanced = mcp_context is not None

        return ClassificationResult(
            request_id=request["request_id"],
            agent_id=self.agent_id,
            label=label,
            confidence=confidence,
            top_k=top_k,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow(),
            mcp_enhanced=mcp_enhanced,
            reasoning=reasoning
        )

    def _classify_simulated(self, prompt: str) -> tuple[str, float]:
        """Simulated classification (fast, deterministic)."""
        prompt_lower = prompt.lower()

        if "pneumonia" in prompt_lower:
            return "pneumonia", random.uniform(0.75, 0.95)
        elif "tuberculosis" in prompt_lower or "tb" in prompt_lower:
            return "tuberculosis", random.uniform(0.70, 0.90)
        elif "normal" in prompt_lower:
            return "normal", random.uniform(0.80, 0.95)
        else:
            return random.choice(self.medical_labels), random.uniform(0.65, 0.88)

    async def _enhance_with_mcp(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Use MCP tools to enhance classification with medical literature.
        Uses AGNTCY/Lungo style MCP via NATS/SLIM transport.

        Based on lungo's agents/farms/colombia/agent.py pattern:
        - factory.create_transport() to create transport
        - factory.create_client("MCP", ...) to create MCP client

        Args:
            prompt: User prompt

        Returns:
            Enhanced context with MCP tool results, or None if failed
        """
        from agntcy_app_sdk.factory import AgntcyFactory

        # Extract potential medical terms from prompt
        medical_terms = []
        for label in self.medical_labels:
            if label.lower() in prompt.lower():
                medical_terms.append(label)

        if not medical_terms:
            medical_terms = ["medical image"]

        query = " ".join(medical_terms)

        # Connect to MCP server via NATS/SLIM (Lungo style)
        transport_type = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
        endpoint = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")

        factory = AgntcyFactory("agntcy_network.medical_mcp_client", enable_tracing=False)

        transport = factory.create_transport(
            transport_type,
            endpoint=endpoint,
            name="default/default/medical_mcp_client"
        )

        mcp_client = factory.create_client(
            "MCP",
            agent_topic=self.mcp_topic,
            transport=transport,
            message_timeout=30
        )

        try:
            async with mcp_client as client:
                # List available tools
                response = await client.list_tools()
                available_tools = [tool.name for tool in response.tools]
                logger.info(f"MCP tools available: {available_tools}")

                # Search medical literature
                result = await client.call_tool(
                    name="search_medical_literature",
                    arguments={"query": query, "max_results": 3}
                )

                # Parse result (handle streamed or non-streamed response)
                content = self._parse_mcp_result(result)
                if content:
                    logger.info(f"MCP enhanced with literature search for: {query}")
                    return {"literature_context": content}

                # Try to get reference if search returned empty
                if medical_terms:
                    ref_result = await client.call_tool(
                        name="get_medical_reference",
                        arguments={"condition": medical_terms[0]}
                    )
                    ref_content = self._parse_mcp_result(ref_result)
                    if ref_content:
                        logger.info(f"MCP enhanced with reference for: {medical_terms[0]}")
                        return {"literature_context": ref_content}

        except Exception as e:
            logger.debug(f"MCP enhancement skipped: {e}")

        return None

    def _parse_mcp_result(self, result) -> Optional[str]:
        """Parse MCP tool result (handles both streamed and non-streamed responses)."""
        try:
            if hasattr(result, "content"):
                content_list = result.content
                if isinstance(content_list, list) and len(content_list) > 0:
                    return content_list[0].text
            return str(result) if result else None
        except Exception:
            return None

    async def _classify_with_llm(self, prompt: str, image_data: bytes = None, mcp_context: Dict = None) -> tuple[str, float, Optional[str]]:
        """LLM-powered vision classification using litellm directly."""
        import base64
        import litellm
        from config.llm_config import LLM_MODEL

        has_mcp = mcp_context and mcp_context.get("literature_context")

        # Build instruction - different format when MCP is enabled
        if has_mcp:
            # With MCP: Ask for reasoning based on medical literature
            text_instruction = (
                f"You are a medical image classification expert with access to medical literature.\n"
                f"Analyze this medical image and provide your diagnosis.\n"
                f"User request: {prompt}\n\n"
                f"Medical literature context:\n{mcp_context['literature_context']}\n\n"
                f"Based on the image AND the medical literature above, provide your diagnosis.\n"
                f"Respond in this exact format:\n"
                f"LABEL: <a concise 1-3 word medical diagnosis label, e.g. 'pneumonia', 'bone fracture', 'brain tumor'>\n"
                f"CONFIDENCE: <confidence score between 0.0 and 1.0>\n"
                f"REASONING: <brief explanation citing the literature>"
            )
            max_tokens = 300
        else:
            # Without MCP: Free-form classification
            text_instruction = (
                f"You are a medical image classification expert.\n"
                f"Analyze this medical image and provide your classification.\n"
                f"User request: {prompt}\n\n"
                f"Respond in this exact format (nothing else):\n"
                f"LABEL: <a concise 1-3 word medical diagnosis label, e.g. 'pneumonia', 'bone fracture', 'brain tumor'>\n"
                f"CONFIDENCE: <confidence score between 0.0 and 1.0>"
            )
            max_tokens = 150

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
                max_tokens=max_tokens,
            )
            llm_output = response.choices[0].message.content.strip()
            logger.info(f"LLM Vision Classification: {llm_output[:200]}")

            label = "unclassified"
            confidence = 0.5
            reasoning = None

            for line in llm_output.split("\n"):
                if line.upper().startswith("LABEL:"):
                    label = line.split(":", 1)[1].strip().lower()
                elif line.upper().startswith("CONFIDENCE:"):
                    try:
                        confidence = float(line.split(":", 1)[1].strip())
                    except Exception:
                        pass
                elif line.upper().startswith("REASONING:"):
                    reasoning = line.split(":", 1)[1].strip()

            return label, confidence, reasoning
        except Exception as e:
            logger.error(f"LLM vision classification failed: {e}, falling back to simulated")
            label, confidence = self._classify_simulated(prompt)
            return label, confidence, None

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

        # Add other labels with decreasing confidence
        other_labels = [l for l in self.medical_labels if l != predicted_label]
        random.shuffle(other_labels)

        remaining_confidence = 1.0 - predicted_confidence
        for i, label in enumerate(other_labels[:2]):
            conf = remaining_confidence * random.uniform(0.3, 0.7) if i == 0 else remaining_confidence * 0.3
            top_k.append(TopKPrediction(label=label, confidence=round(conf, 3), rank=i + 2))

        return top_k
