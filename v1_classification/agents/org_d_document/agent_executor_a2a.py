# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
A2A executor: NATS-delivered messages -> PydanticAI -> A2A text response.
"""

import json
import logging
from typing import Any
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    ContentTypeNotSupportedError,
    InternalError,
    JSONRPCResponse,
    Message,
    Part,
    Role,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_task
from a2a.utils.errors import ServerError

from agents.org_d_document.agent import analyze_document
from agents.org_d_document.card import AGENT_CARD, AGENT_ID

logger = logging.getLogger("org_d_document.agent_executor")

_TASK_MARKER = "\n\nTask: "


class DocumentAgentExecutor(AgentExecutor):
    """A2A Agent Executor for Organization D document analysis."""

    def __init__(self):
        self.agent_card = AGENT_CARD.model_dump(mode="json", exclude_none=True)
        logger.info("Initialized DocumentAgentExecutor: %s", AGENT_ID)

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

        raw_input = context.get_user_input()
        prompt, task_payload = self._split_prompt_and_task(raw_input)
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        try:
            image_url = self._resolve_image_url(context.message, task_payload)
            if not image_url:
                logger.warning(
                    "Document agent: no image URL in metadata or Task payload; analysis will be text-only"
                )
            output = await analyze_document(prompt, "", image_fetch_url=image_url)
            text = self._format_output(output)

            message = Message(
                message_id=str(uuid4()),
                role=Role.agent,
                metadata={"name": self.agent_card["name"]},
                parts=[Part(TextPart(text=text))],
            )
            logger.info("Agent output message: %s", message)
            await event_queue.enqueue_event(message)

        except Exception as e:
            logger.exception("Document analysis failed: %s", e)
            raise ServerError(error=InternalError()) from e

    async def cancel(self, request: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())

    def _split_prompt_and_task(self, raw: str) -> tuple[str, dict[str, Any] | None]:
        """Strip planner-appended Task JSON so the LLM sees only the user prompt."""
        if _TASK_MARKER not in raw:
            return raw.strip(), None
        head, tail = raw.split(_TASK_MARKER, 1)
        try:
            payload = json.loads(tail.strip())
            if isinstance(payload, dict):
                return head.strip(), payload
        except json.JSONDecodeError:
            logger.warning("Could not parse Task JSON from message tail")
        return raw.strip(), None

    def _resolve_image_url(self, message: Message, task_payload: dict[str, Any] | None) -> str | None:
        """Metadata first; fallback to Task body (metadata may be dropped on NATS)."""
        meta = message.metadata
        if isinstance(meta, dict):
            url = meta.get("image_url")
            if url:
                return str(url)
        if task_payload:
            img = task_payload.get("image")
            if isinstance(img, dict):
                return img.get("presigned_url") or img.get("url") or None
        return None

    def _format_output(self, output) -> str:
        payload = output.model_dump()
        pretty = json.dumps(payload, indent=2)
        return (
            "Document Analysis Result (structured):\n"
            f"document_type: {output.document_type}\n"
            f"confidence: {output.confidence:.2f}\n\n"
            f"extracted_text:\n{output.extracted_text}\n\n"
            f"JSON:\n{pretty}\n"
        )
