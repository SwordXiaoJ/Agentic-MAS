"""
Agent Executor for Document Analysis Agent (A2A SDK)

Follows the same A2A executor pattern used by other agents in this repo.
"""

import logging
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    UnsupportedOperationError,
    JSONRPCResponse,
    ContentTypeNotSupportedError,
    InternalError,
    Message,
    Role,
    Part,
    TextPart,
)
from a2a.utils import new_task
from a2a.utils.errors import ServerError

from agents.org_d_document.agent import DocumentAnalysisAgent
from agents.org_d_document.card import AGENT_CARD, AGENT_ID

logger = logging.getLogger("org_d_document.agent_executor")


class DocumentAgentExecutor(AgentExecutor):
    """A2A Agent Executor for Document Analysis (OCR + classification)."""

    def __init__(self):
        self.agent = DocumentAnalysisAgent()
        self.agent_card = AGENT_CARD.model_dump(mode="json", exclude_none=True)
        logger.info(f"Initialized DocumentAgentExecutor: {AGENT_ID}")

    def _validate_request(self, context: RequestContext) -> JSONRPCResponse | None:
        if not context or not context.message or not context.message.parts:
            logger.error("Invalid request parameters: %s", context)
            return JSONRPCResponse(error=ContentTypeNotSupportedError())
        return None

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.debug("Received message request: %s", context.message)

        validation_error = self._validate_request(context)
        if validation_error:
            await event_queue.enqueue_event(validation_error)
            return

        prompt = context.get_user_input()

        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        try:
            request = self._parse_request(context.message, prompt)

            extracted = await self.agent.extract_text(
                request["image"].get("url") or request["image"].get("base64") or ""
            )
            result = await self.agent.classify(request)

            output = self._format_output(result, extracted.get("extracted_text", ""))

            message = Message(
                message_id=str(uuid4()),
                role=Role.agent,
                metadata={"name": self.agent_card["name"]},
                parts=[Part(TextPart(text=output))],
            )
            logger.info("Agent output message: %s", message)
            await event_queue.enqueue_event(message)

        except Exception as e:
            logger.error(f"An error occurred while processing document analysis: {e}")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, request: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())

    def _parse_request(self, message: Message, prompt: str) -> dict:
        md = message.metadata or {}
        image_url = md.get("image_url") or md.get("url") or ""
        image_base64 = md.get("image_base64") or md.get("image_b64") or md.get("base64") or ""

        image = {}
        if image_url:
            image["url"] = image_url
        elif image_base64:
            image["base64"] = image_base64
        else:
            image["url"] = "http://example.com/default.jpg"

        return {
            "request_id": message.message_id,
            "image": image,
            "prompt": prompt,
            "constraints": {"min_confidence": 0.7, "max_latency_ms": 15000},
        }

    def _format_output(self, result, extracted_text: str) -> str:
        output = "Document Analysis Result:\n"
        output += f"Type: {result.label}\n"
        output += f"Confidence: {result.confidence:.2f}\n"
        output += f"Latency: {result.latency_ms}ms\n"
        if extracted_text:
            output += "\nExtracted text (truncated):\n"
            output += extracted_text[:2000].rstrip() + ("\n" if not extracted_text.endswith("\n") else "")
        output += "\nTop Predictions:\n"
        for pred in result.top_k[:4]:
            output += f"  {pred.rank}. {pred.label} ({pred.confidence:.2f})\n"
        return output

