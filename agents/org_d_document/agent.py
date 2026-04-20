# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Document analysis agent (Org D) implemented with CrewAI.

Creates a single CrewAI Agent + Task that:
- Accepts a base64 image (raw base64 or data URL) or an image URL
- Sends it to LiteLLM using Gemini Flash Vision
- Extracts text (OCR-style) and classifies document type

Valid document types:
  - invoice
  - handwritten_note
  - chart
  - official_form
"""

import base64
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import aiohttp

from shared.schemas import ClassificationResult, TopKPrediction

logger = logging.getLogger(__name__)

_ALLOWED_LABELS = {"invoice", "handwritten_note", "chart", "official_form"}


def _looks_like_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _strip_data_url_prefix(s: str) -> str:
    # data:<mime>;base64,<payload>
    if s.startswith("data:") and ";base64," in s:
        return s.split(";base64,", 1)[1]
    return s


async def _fetch_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


def _to_image_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _normalize_image_input(image_input: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (image_url, data_url) where exactly one is non-None when possible.
    """
    image_input = (image_input or "").strip()
    if not image_input:
        return None, None

    if _looks_like_url(image_input):
        return image_input, None

    # Assume base64 (raw) or data URL
    b64 = _strip_data_url_prefix(image_input)
    # Very light validation: base64 chars and reasonable length
    if len(b64) < 32:
        return None, None
    return None, f"data:image/jpeg;base64,{b64}"


def _safe_json_loads(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_json_object(text: str) -> Optional[dict]:
    """
    Try to pull a JSON object from a messy LLM response.
    """
    text = (text or "").strip()
    if not text:
        return None

    direct = _safe_json_loads(text)
    if isinstance(direct, dict):
        return direct

    # Extract first {...} block
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    return _safe_json_loads(m.group(0))


def _coerce_label(label: Any) -> str:
    if not isinstance(label, str):
        return "official_form"
    label = label.strip().lower()
    # Common variations
    label = label.replace("handwritten note", "handwritten_note").replace("handwritten-note", "handwritten_note")
    label = label.replace("official form", "official_form").replace("official-form", "official_form")
    if label not in _ALLOWED_LABELS:
        return "official_form"
    return label


def _coerce_confidence(x: Any) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.6
    return max(0.0, min(1.0, v))


def _build_top_k(label: str, confidence: float) -> list[TopKPrediction]:
    # Deterministic top-k: chosen label first, remaining labels with small priors
    remaining = [l for l in sorted(_ALLOWED_LABELS) if l != label]
    rest_conf = max(0.0, 1.0 - confidence)
    second = rest_conf * 0.6
    third = rest_conf * 0.3
    fourth = rest_conf * 0.1
    confs = [second, third, fourth]
    top = [TopKPrediction(label=label, confidence=confidence, rank=1)]
    for i, (lbl, conf) in enumerate(zip(remaining, confs), start=2):
        top.append(TopKPrediction(label=lbl, confidence=round(conf, 3), rank=i))
    return top


class DocumentAnalysisAgent:
    def __init__(self, agent_id: str = "org-d-document-clf-004"):
        self.agent_id = agent_id

        # CrewAI is required by the user request; keep import local so module loads
        # even if dependency isn't installed yet.
        from crewai import Agent, Crew, Process, Task
        from crewai.tools import tool

        @tool("extract_text_and_classify_document")
        async def extract_text_and_classify_document(image_input: str) -> str:
            """
            Use Gemini Flash Vision to extract text and classify document type.
            Input: URL or base64 string (raw or data URL).
            Output: strict JSON with keys:
              - extracted_text (string)
              - document_type (invoice|handwritten_note|chart|official_form)
              - confidence (0..1)
            """
            import litellm

            image_url, data_url = _normalize_image_input(image_input)
            if not image_url and not data_url:
                return json.dumps(
                    {
                        "extracted_text": "",
                        "document_type": "official_form",
                        "confidence": 0.2,
                    }
                )

            instruction = (
                "You are an expert at document understanding.\n"
                "Given a document image, do OCR-like text extraction and then classify the document.\n"
                "Allowed document_type values:\n"
                "- invoice\n"
                "- handwritten_note\n"
                "- chart\n"
                "- official_form\n\n"
                "Return ONLY valid JSON with exactly these keys:\n"
                '{"extracted_text":"...","document_type":"...","confidence":0.0}\n'
                "Rules:\n"
                "- extracted_text: include the most salient readable text; preserve line breaks when helpful\n"
                "- document_type: must be one of the allowed values\n"
                "- confidence: number between 0 and 1\n"
            )

            content: list[dict] = [{"type": "text", "text": instruction}]
            if image_url:
                content.append({"type": "image_url", "image_url": {"url": image_url}})
            else:
                content.append({"type": "image_url", "image_url": {"url": data_url}})

            response = await litellm.acompletion(
                model="gemini/gemini-flash-latest",
                messages=[{"role": "user", "content": content}],
                max_tokens=800,
            )
            return (response.choices[0].message.content or "").strip()

        self._tool = extract_text_and_classify_document

        self._agent = Agent(
            role="Document Analyst",
            goal="Extract text from a document image and classify its type.",
            backstory=(
                "You specialize in OCR-style extraction and document-type classification. "
                "You always use the provided tool and you always return strict JSON."
            ),
            tools=[extract_text_and_classify_document],
            allow_delegation=False,
            verbose=False,
            llm="gemini/gemini-flash-latest",
        )

        self._task = Task(
            description=(
                "You are given a document image input as `{image_input}` (a URL or base64).\n"
                "Call the tool `extract_text_and_classify_document` with `{image_input}` and return the tool output unchanged."
            ),
            expected_output='{"extracted_text":"...","document_type":"invoice|handwritten_note|chart|official_form","confidence":0.0}',
            agent=self._agent,
        )

        self._crew = Crew(
            agents=[self._agent],
            tasks=[self._task],
            process=Process.sequential,
            verbose=False,
        )

    async def classify(self, request: Dict[str, Any]) -> ClassificationResult:
        start_time = time.time()
        request_id = request.get("request_id", f"req-{datetime.utcnow().timestamp()}")

        image = request.get("image") or {}
        _prompt = (request.get("prompt") or "").strip()

        # Accept url/presigned_url/bytes for compatibility with other agents.
        image_input = (
            image.get("presigned_url")
            or image.get("url")
            or image.get("base64")
            or image.get("b64")
            or image.get("bytes")
            or ""
        )

        if isinstance(image_input, dict):
            # Unexpected shape; attempt common patterns
            image_input = image_input.get("url") or image_input.get("base64") or ""

        if isinstance(image_input, bytes):
            image_input = _to_image_data_url(image_input)

        if isinstance(image_input, str) and image_input and not _looks_like_url(image_input):
            # if raw base64, normalize into data URL for the tool
            b64 = _strip_data_url_prefix(image_input)
            image_input = f"data:image/jpeg;base64,{b64}"

        # CrewAI is sync today; run it in a thread to keep async API.
        import asyncio

        result_text = await asyncio.to_thread(self._crew.kickoff, inputs={"image_input": image_input})
        result_str = str(result_text).strip()
        parsed = _extract_json_object(result_str) or {}

        extracted_text = parsed.get("extracted_text")
        if not isinstance(extracted_text, str):
            extracted_text = ""

        label = _coerce_label(parsed.get("document_type") or parsed.get("label"))
        confidence = _coerce_confidence(parsed.get("confidence"))

        latency_ms = int((time.time() - start_time) * 1000)

        # Encode the extracted text into the response label? Keep label strict; return extracted text via top_k notes?
        # shared.schemas doesn't expose a field for extracted text, so include it in a structured top-k label variant.
        # Keep top_k consistent with other agents, and surface extracted text in the main message formatting layer.
        top_k = _build_top_k(label, confidence)

        return ClassificationResult(
            request_id=request_id,
            agent_id=self.agent_id,
            label=label,
            confidence=confidence,
            top_k=top_k,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow(),
        )

    async def extract_text(self, image_input: str) -> dict:
        """
        Optional helper for callers that want extracted text + classification JSON.
        """
        import asyncio

        out = await asyncio.to_thread(self._crew.kickoff, inputs={"image_input": image_input})
        parsed = _extract_json_object(str(out)) or {}
        parsed["document_type"] = _coerce_label(parsed.get("document_type"))
        parsed["confidence"] = _coerce_confidence(parsed.get("confidence"))
        if not isinstance(parsed.get("extracted_text"), str):
            parsed["extracted_text"] = ""
        return parsed