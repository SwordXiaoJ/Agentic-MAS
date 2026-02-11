"""
Agntcy Transport Layer (A2A SDK)

Uses agntcy-app-sdk's AgntcyFactory to create transport,
exactly like lungo's implementation.

Security Support:
    This module integrates with config.security_config for future
    security upgrades (TLS, JWT, mTLS, SPIRE).
"""

import os
import logging
from typing import Dict, Any, Optional

from agntcy_app_sdk.factory import AgntcyFactory
from a2a.types import (
    SendMessageRequest,
    MessageSendParams,
    Message,
    Part,
    TextPart,
    Role,
    AgentCard as A2AAgentCard,
)

from shared.schemas.request import ClassificationRequest
from shared.schemas.result import ClassificationResult
from shared.schemas.agent_record import AgentRecord

# Import security config (with fallback for backward compatibility)
try:
    from config.security_config import get_security_config, SecurityConfig
    SECURITY_CONFIG_AVAILABLE = True
except ImportError:
    SECURITY_CONFIG_AVAILABLE = False
    SecurityConfig = None

logger = logging.getLogger(__name__)


class AgntcyTransport:
    """
    Transport layer using agntcy-app-sdk.

    Exactly like lungo's supervisor tools.py pattern.

    Supports security configuration for future upgrades:
    - TLS encryption
    - JWT authentication
    - MLS end-to-end encryption
    """

    def __init__(
        self,
        factory_name: str = "agntcy_network.planner",
        transport_type: str = None,
        endpoint: str = None,
        security_config: Optional['SecurityConfig'] = None
    ):
        """
        Initialize Agntcy transport.

        Args:
            factory_name: Name for the factory
            transport_type: "NATS" or "SLIM" (default from env)
            endpoint: Transport endpoint (default from env)
            security_config: Optional security configuration (auto-loaded if not provided)
        """
        # Get from environment if not specified
        self.transport_type = transport_type or os.getenv(
            "DEFAULT_MESSAGE_TRANSPORT", "NATS"
        )
        self.endpoint = endpoint or os.getenv(
            "TRANSPORT_SERVER_ENDPOINT",
            "nats://localhost:4222" if self.transport_type == "NATS" else "http://localhost:46357"
        )

        # Load security config if available and not provided
        self.security_config = security_config
        if self.security_config is None and SECURITY_CONFIG_AVAILABLE:
            self.security_config = get_security_config()

        # Create factory (like lungo)
        self.factory = AgntcyFactory(factory_name, enable_tracing=False)

        # Build transport kwargs with security settings
        transport_kwargs = self._build_transport_kwargs()

        # Create transport (like lungo)
        self.transport = self.factory.create_transport(
            self.transport_type,
            **transport_kwargs
        )

        # Log initialization
        self._log_init()

    def _build_transport_kwargs(self) -> Dict[str, Any]:
        """
        Build transport keyword arguments including security settings.

        Returns:
            Dict of kwargs for factory.create_transport()
        """
        kwargs = {
            "endpoint": self.endpoint,
            "name": "default/default/planner",
        }

        # Add SLIM-specific security settings
        # SLIMTransport supports: tls_insecure, shared_secret_identity, jwt, audience
        if self.transport_type.upper() == "SLIM" and self.security_config:
            slim_kwargs = self.security_config.get_slim_transport_kwargs()
            kwargs.update(slim_kwargs)

        return kwargs

    def _log_init(self):
        """Log transport initialization details"""
        security_mode = "insecure"
        if self.security_config and self.security_config.is_secure:
            security_mode = self.security_config.auth_mode.value

        logger.info(
            f"Initialized AgntcyTransport: {self.transport_type} @ {self.endpoint} "
            f"(security: {security_mode})"
        )

    @property
    def is_secure(self) -> bool:
        """Check if transport is running in secure mode"""
        if self.security_config:
            return self.security_config.is_secure
        return False

    async def connect(self):
        """Connect to transport (if needed)"""
        logger.info(f"AgntcyTransport ready: {self.transport_type}")

    async def close(self):
        """Close transport connection"""
        logger.info("AgntcyTransport closed")

    def _agent_record_to_a2a_card(self, agent_record: AgentRecord) -> A2AAgentCard:
        """
        Convert AgentRecord to A2A AgentCard.

        Args:
            agent_record: Our AgentRecord from discovery

        Returns:
            A2A AgentCard
        """
        return A2AAgentCard(
            name=agent_record.agent_id,
            url=agent_record.url,
            version="1.0.0",
            description=f"Agent {agent_record.agent_id} ({agent_record.organization})",
        )

    def _classification_to_message(self, request: ClassificationRequest) -> Message:
        """
        Convert ClassificationRequest to A2A Message.

        Args:
            request: Classification request

        Returns:
            A2A Message
        """
        # Get image reference (presigned_url > url > ref)
        image_ref = request.image.presigned_url or request.image.url or request.image.ref or ""
        text = f"Classify image: {image_ref}\nPrompt: {request.prompt}"

        return Message(
            message_id=request.request_id,
            role=Role.user,
            parts=[Part(TextPart(text=text))],
            metadata={
                "image_url": image_ref,
                "prompt": request.prompt,
            }
        )

    def _parse_response(self, response) -> ClassificationResult:
        """
        Parse A2A response to ClassificationResult.

        Args:
            response: A2A response

        Returns:
            ClassificationResult
        """
        # Extract text from response parts
        if hasattr(response, 'parts') and response.parts:
            text = response.parts[0].text if hasattr(response.parts[0], 'text') else str(response)
        else:
            text = str(response)

        # Parse text response (simple parsing)
        # Format: "Label: dog\nConfidence: 0.85\n..."
        lines = text.split('\n')
        label = "unknown"
        confidence = 0.0

        for line in lines:
            if line.startswith("Label:"):
                label = line.split(":", 1)[1].strip()
            elif line.startswith("Confidence:"):
                conf_str = line.split(":", 1)[1].strip()
                confidence = float(conf_str)

        return ClassificationResult(
            request_id="resp-" + str(response.message_id) if hasattr(response, 'message_id') else "unknown",
            agent_id="unknown",
            label=label,
            confidence=confidence,
            latency_ms=100,
            top_k=[],
        )

    async def send_classification_request(
        self,
        agent_record: AgentRecord,
        request: ClassificationRequest,
        timeout: float = 30.0
    ) -> ClassificationResult:
        """
        Send classification request via A2A transport.

        Like lungo's tools pattern.

        Args:
            agent_record: Target agent's AgentRecord
            request: Classification request
            timeout: Request timeout

        Returns:
            ClassificationResult
        """
        logger.info(f"Sending request to {agent_record.agent_id} via {self.transport_type}")

        # Convert AgentRecord to A2A card
        a2a_card = self._agent_record_to_a2a_card(agent_record)

        # Convert request to A2A message
        message = self._classification_to_message(request)

        # Send via transport (like lungo)
        response = await self.transport.send_message(
            agent_card=a2a_card,
            message=message,
            timeout=timeout
        )

        # Parse response
        result = self._parse_response(response)
        result.agent_id = agent_record.agent_id
        result.request_id = request.request_id

        logger.info(f"Received response: {result.label} ({result.confidence:.2f})")

        return result


def create_agntcy_transport(
    security_config: Optional['SecurityConfig'] = None
) -> AgntcyTransport:
    """
    Create AgntcyTransport from environment variables.

    Like lungo's pattern.

    Environment Variables:
        DEFAULT_MESSAGE_TRANSPORT: "NATS" or "SLIM"
        TRANSPORT_SERVER_ENDPOINT: Transport endpoint URL
        SLIM_AUTH_MODE: Security mode (insecure, basic, jwt, etc.)

    Args:
        security_config: Optional security configuration

    Returns:
        AgntcyTransport instance
    """
    return AgntcyTransport(security_config=security_config)
