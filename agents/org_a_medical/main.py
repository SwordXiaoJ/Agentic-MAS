#!/usr/bin/env python3
"""
Farm Server for Medical Classification Agent (A2A SDK)

Based on lungo's farm_server.py architecture using a2a-sdk and agntcy-app-sdk.
Exact same pattern as lungo/agents/farms/brazil/farm_server.py

Security Support:
    Integrates with config.security_config for future security upgrades.
"""

import asyncio
import os
from uvicorn import Config, Server
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler

from agntcy_app_sdk.semantic.a2a.protocol import A2AProtocol
from agntcy_app_sdk.app_sessions import AppContainer
from agntcy_app_sdk.factory import AgntcyFactory

from agents.org_a_medical.agent_executor_a2a import MedicalAgentExecutor
from agents.org_a_medical.card import AGENT_CARD, AGENT_ID

# Import security config (with fallback for backward compatibility)
try:
    from config.security_config import get_security_config, print_security_config
    SECURITY_CONFIG_AVAILABLE = True
except ImportError:
    SECURITY_CONFIG_AVAILABLE = False

load_dotenv()

# ============================================
# Configuration (like lungo's config.py)
# ============================================

DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
TRANSPORT_SERVER_ENDPOINT = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")
FARM_BROADCAST_TOPIC = os.getenv("FARM_BROADCAST_TOPIC", "agents.broadcast")
ENABLE_HTTP = os.getenv("ENABLE_HTTP", "true").lower() in ("true", "1", "yes")

HTTP_PORT = int(os.getenv("MEDICAL_AGENT_PORT", "9001"))
HTTP_HOST = "0.0.0.0"

# Load security configuration
security_config = None
if SECURITY_CONFIG_AVAILABLE:
    security_config = get_security_config()

# ============================================
# Initialize Agntcy Factory
# ============================================

# Initialize a multi-protocol, multi-transport agntcy factory.
# Same as lungo's pattern
factory = AgntcyFactory("agntcy_network.medical_agent", enable_tracing=False)


# ============================================
# Server Functions
# ============================================

async def run_http_server(server):
    """
    Run the HTTP/REST server.

    Exactly the same as lungo's pattern.
    """
    try:
        config = Config(
            app=server.build(),
            host=HTTP_HOST,
            port=HTTP_PORT,
            loop="asyncio"
        )
        userver = Server(config)
        await userver.serve()
    except Exception as e:
        print(f"HTTP server encountered an error: {e}")


async def run_transport(server, transport_type, endpoint):
    """
    Run the transport and broadcast bridge.

    Supports both NATS and SLIM transports (following lungo's patterns):
    - NATS: Uses topic-based routing (broadcast + personal topics)
    - SLIM: Uses group session mode (no explicit topics)

    Security:
        Uses security_config for TLS and MLS settings when available.
    """
    app_session = None
    try:
        # Create personal topic using A2A protocol
        personal_topic = A2AProtocol.create_agent_topic(AGENT_CARD)

        # Build transport kwargs with security settings
        transport_kwargs = {
            "endpoint": endpoint,
            "name": f"default/default/{personal_topic}",
        }

        # Add SLIM-specific security settings
        # SLIMTransport supports: tls_insecure, shared_secret_identity, jwt, audience
        if transport_type.upper() == "SLIM" and security_config:
            slim_kwargs = security_config.get_slim_transport_kwargs()
            transport_kwargs.update(slim_kwargs)

        # Create transport via factory (like lungo)
        transport = factory.create_transport(
            transport_type,
            **transport_kwargs
        )

        if transport_type.upper() == "SLIM":
            # SLIM mode: Use group session without explicit topics
            # Following lungo's logistics agent pattern
            app_session = factory.create_app_session(max_sessions=1)

            # For SLIM, don't specify topic - it uses group-based sessions
            app_session.add_app_container(
                "group_session",
                AppContainer(
                    server,
                    transport=transport
                    # No topic for SLIM - uses group conversation mode
                )
            )

            await app_session.start_session("group_session")

            # Security status
            security_mode = "insecure"
            if security_config and security_config.is_secure:
                security_mode = security_config.auth_mode.value

            print(f"✅ A2A Transport started (SLIM group mode):")
            print(f"   Type: {transport_type}")
            print(f"   Endpoint: {endpoint}")
            print(f"   Security: {security_mode}")

        else:
            # NATS mode: Use topic-based routing
            # Following lungo's farm agent pattern
            app_session = factory.create_app_session(max_sessions=2)

            # Add containers for broadcast and personal topics
            app_session.add_app_container(
                "public_session",
                AppContainer(
                    server,
                    transport=transport,
                    topic=FARM_BROADCAST_TOPIC,  # agents.broadcast
                )
            )

            app_session.add_app_container(
                "private_session",
                AppContainer(
                    server,
                    transport=transport,
                    topic=personal_topic,  # agents.direct.{agent_id}
                )
            )

            # Start both sessions
            await app_session.start_session("public_session")
            await app_session.start_session("private_session")

            print(f"✅ A2A Transport started (NATS topic mode):")
            print(f"   Type: {transport_type}")
            print(f"   Endpoint: {endpoint}")
            print(f"   Personal topic: {personal_topic}")
            print(f"   Broadcast topic: {FARM_BROADCAST_TOPIC}")

    except Exception as e:
        print(f"Transport encountered an error: {e}")
        if app_session:
            await app_session.stop_all_sessions()


async def main(enable_http: bool):
    """
    Run the A2A server with both HTTP and transport logic.

    Exactly the same as lungo's pattern.
    """
    print()
    print("=" * 60)
    print("Medical Agent Farm Server (A2A SDK)")
    print("=" * 60)
    print(f"Agent: {AGENT_ID}")
    print(f"Name: {AGENT_CARD.name}")
    print(f"HTTP: {enable_http}")
    print(f"Transport: {DEFAULT_MESSAGE_TRANSPORT}")
    print(f"Endpoint: {TRANSPORT_SERVER_ENDPOINT}")

    # Print security configuration if available
    if security_config:
        print(f"Security Mode: {security_config.auth_mode.value}")
        print(f"TLS Enabled: {security_config.tls.enabled}")
        print(f"MLS Enabled: {security_config.mls.enabled}")

    print("=" * 60)
    print()

    # Create request handler with executor
    request_handler = DefaultRequestHandler(
        agent_executor=MedicalAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # Create A2A Starlette application
    server = A2AStarletteApplication(
        agent_card=AGENT_CARD,
        http_handler=request_handler
    )

    # Run HTTP server and transport logic concurrently
    tasks = []

    if enable_http:
        print(f"Starting HTTP server on {HTTP_HOST}:{HTTP_PORT}")
        tasks.append(asyncio.create_task(run_http_server(server)))

    print(f"Starting {DEFAULT_MESSAGE_TRANSPORT} transport...")
    tasks.append(
        asyncio.create_task(
            run_transport(server, DEFAULT_MESSAGE_TRANSPORT, TRANSPORT_SERVER_ENDPOINT)
        )
    )

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    try:
        asyncio.run(main(ENABLE_HTTP))
    except KeyboardInterrupt:
        print("\nShutting down gracefully on keyboard interrupt.")
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()
