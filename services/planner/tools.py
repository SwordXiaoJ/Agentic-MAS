# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
A2A Communication Tools for Planner.

Follows Lungo's pattern - using AgntcyFactory directly for A2A messaging.
"""

import os
import logging
from typing import Dict, Any, Optional
from uuid import uuid4

from a2a.types import (
    AgentCard,
    SendMessageRequest,
    MessageSendParams,
    Message,
    Part,
    TextPart,
    Role,
)
from agntcy_app_sdk.semantic.a2a.protocol import A2AProtocol

from services.planner.shared import get_factory

logger = logging.getLogger("planner.tools")

# Configuration (following Lungo's config pattern)
DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
TRANSPORT_SERVER_ENDPOINT = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")

# Global factory and transport instances (Lungo style)
factory = get_factory()
transport = factory.create_transport(
    DEFAULT_MESSAGE_TRANSPORT,
    endpoint=TRANSPORT_SERVER_ENDPOINT,
    name="default/default/planner_graph"
)


class A2AAgentError(Exception):
    """Custom exception for errors related to A2A agent communication."""
    pass


async def send_message_to_agent(
    agent_card: AgentCard,
    prompt: str,
    task_payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Send message to an agent via A2A protocol.

    Follows Lungo's get_farm_yield_inventory pattern.

    Args:
        agent_card: Target agent's AgentCard
        prompt: Message text to send
        task_payload: Optional additional payload (should contain 'image' with 'presigned_url')

    Returns:
        Agent response as dict
    """
    logger.info(f"Sending message to agent: {agent_card.name}")

    try:
        # Create A2A client (Lungo style)
        client = await factory.create_client(
            "A2A",
            agent_topic=A2AProtocol.create_agent_topic(agent_card),
            transport=transport,
        )

        # Build message content
        message_text = prompt
        if task_payload:
            import json
            message_text = f"{prompt}\n\nTask: {json.dumps(task_payload)}"

        # Extract image URL from task payload for metadata
        message_metadata = {}
        if task_payload and "image" in task_payload:
            image_info = task_payload["image"]
            # Support both presigned_url and url keys
            image_url = image_info.get("presigned_url") or image_info.get("url")
            if image_url:
                message_metadata["image_url"] = image_url
                logger.info(f"Including image_url in metadata: {image_url[:80]}...")

        # Create A2A request (exactly like Lungo)
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(
                message=Message(
                    messageId=str(uuid4()),
                    role=Role.user,
                    parts=[Part(TextPart(text=message_text))],
                    metadata=message_metadata if message_metadata else None,
                ),
            )
        )
        
        # Send and get response
        response = await client.send_message(request)
        logger.info(f"Response received from {agent_card.name}")
        
        # Parse response (Lungo style)
        if response.root.result and response.root.result.parts:
            for part in response.root.result.parts:
                if hasattr(part.root, "text"):
                    return {
                        "status": "success",
                        "response": part.root.text,
                        "agent": agent_card.name
                    }
        
        if response.root.error:
            raise A2AAgentError(str(response.root.error))
        
        return {
            "status": "error",
            "error": "No valid response",
            "agent": agent_card.name
        }
        
    except Exception as e:
        logger.error(f"Error communicating with {agent_card.name}: {e}")
        raise A2AAgentError(f"Failed to communicate with {agent_card.name}: {e}")


async def broadcast_message_to_agents(
    agent_cards: list[AgentCard],
    prompt: str,
    task_payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 10.0
) -> list[Dict[str, Any]]:
    """
    Send messages to multiple agents in parallel.
    
    Args:
        agent_cards: List of target agent cards
        prompt: Message text to send
        task_payload: Optional additional payload
        timeout_seconds: Timeout for each request
    
    Returns:
        List of agent responses
    """
    import asyncio
    
    tasks = [
        send_message_to_agent(card, prompt, task_payload)
        for card in agent_cards
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed.append({
                "status": "error",
                "error": str(result),
                "agent": agent_cards[i].name if i < len(agent_cards) else "unknown"
            })
        else:
            processed.append(result)
    
    return processed
