"""
Agent Executor for Satellite Classification Agent (A2A SDK)

Based on lungo's farm agent architecture using a2a-sdk.
Exact same pattern as lungo/agents/farms/brazil/agent_executor.py
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

from agents.org_b_satellite.agent import SatelliteClassifierAgent
from agents.org_b_satellite.card import AGENT_CARD, AGENT_ID

logger = logging.getLogger("org_b_satellite.agent_executor")


class SatelliteAgentExecutor(AgentExecutor):
    """
    A2A Agent Executor for Satellite Classification.

    Follows lungo's FarmAgentExecutor pattern exactly.
    """

    def __init__(self):
        self.agent = SatelliteClassifierAgent()
        self.agent_card = AGENT_CARD.model_dump(mode="json", exclude_none=True)
        logger.info(f"Initialized SatelliteAgentExecutor: {AGENT_ID}")

    def _validate_request(self, context: RequestContext) -> JSONRPCResponse | None:
        """Validates the incoming request."""
        if not context or not context.message or not context.message.parts:
            logger.error("Invalid request parameters: %s", context)
            return JSONRPCResponse(error=ContentTypeNotSupportedError())
        return None

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute the agent's logic for a given request context.

        Args:
            context: The request context containing the message, task ID, etc.
            event_queue: The queue to publish events to.
        """
        logger.debug("Received message request: %s", context.message)

        # Validate request
        validation_error = self._validate_request(context)
        if validation_error:
            await event_queue.enqueue_event(validation_error)
            return

        # Extract user input
        prompt = context.get_user_input()

        # Get or create task
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        try:
            # Parse request and execute
            request = self._parse_request(context.message, prompt)
            result = await self.agent.classify(request)

            # Format and enqueue response
            output = self._format_output(result)

            message = Message(
                message_id=str(uuid4()),
                role=Role.agent,
                metadata={"name": self.agent_card["name"]},
                parts=[Part(TextPart(text=output))],
            )

            logger.info("Agent output message: %s", message)
            await event_queue.enqueue_event(message)

        except Exception as e:
            logger.error(f'An error occurred while processing classification: {e}')
            raise ServerError(error=InternalError()) from e

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> None:
        """Cancel this agent's execution for the given request context."""
        raise ServerError(error=UnsupportedOperationError())

    def _parse_request(self, message: Message, prompt: str) -> dict:
        """Parse classification request from A2A message."""
        image_url = "http://example.com/default.jpg"
        if message.metadata and "image_url" in message.metadata:
            image_url = message.metadata["image_url"]

        return {
            "request_id": message.message_id,
            "image": {"url": image_url},
            "prompt": prompt,
            "constraints": {
                "min_confidence": 0.7,
                "max_latency_ms": 5000
            }
        }

    def _format_output(self, result) -> str:
        """Format classification result as text output."""
        output = f"Satellite Classification Result:\n"
        output += f"Label: {result.label}\n"
        output += f"Confidence: {result.confidence:.2f}\n"
        output += f"Latency: {result.latency_ms}ms\n"
        output += f"\nTop-3 Predictions:\n"
        for pred in result.top_k[:3]:
            output += f"  {pred.rank}. {pred.label} ({pred.confidence:.2f})\n"

        return output
