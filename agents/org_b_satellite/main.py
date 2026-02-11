#!/usr/bin/env python3
"""
Farm Server for Satellite Classification Agent (A2A SDK)

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

from agents.org_b_satellite.agent_executor_a2a import SatelliteAgentExecutor
from agents.org_b_satellite.card import AGENT_CARD, AGENT_ID

# Import security config (with fallback for backward compatibility)
try:
    from config.security_config import get_security_config
    SECURITY_CONFIG_AVAILABLE = True
except ImportError:
    SECURITY_CONFIG_AVAILABLE = False

load_dotenv()

# Configuration (like lungo's config.py)
DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
TRANSPORT_SERVER_ENDPOINT = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")
FARM_BROADCAST_TOPIC = os.getenv("FARM_BROADCAST_TOPIC", "agents.broadcast")
ENABLE_HTTP = os.getenv("ENABLE_HTTP", "true").lower() in ("true", "1", "yes")

HTTP_PORT = int(os.getenv("SATELLITE_AGENT_PORT", "9002"))
HTTP_HOST = "0.0.0.0"

# Load security configuration
security_config = None
if SECURITY_CONFIG_AVAILABLE:
    security_config = get_security_config()

# Initialize Agntcy Factory (like lungo)
factory = AgntcyFactory("agntcy_network.satellite_agent", enable_tracing=False)


async def run_http_server(server):
    """Run the HTTP/REST server."""
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
    """Run the transport and broadcast bridge.

    Supports both NATS (topic-based) and SLIM (group session) modes.

    Security:
        Uses security_config for TLS and MLS settings when available.
    """
    app_session = None
    try:
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

        transport = factory.create_transport(
            transport_type,
            **transport_kwargs
        )

        if transport_type.upper() == "SLIM":
            # SLIM mode: group session without topics
            app_session = factory.create_app_session(max_sessions=1)
            app_session.add_app_container("group_session", AppContainer(
                server,
                transport=transport
            ))
            await app_session.start_session("group_session")

            security_mode = "insecure"
            if security_config and security_config.is_secure:
                security_mode = security_config.auth_mode.value

            print(f"✅ A2A Transport started (SLIM group mode):")
            print(f"   Endpoint: {endpoint}")
            print(f"   Security: {security_mode}")
        else:
            # NATS mode: topic-based routing
            app_session = factory.create_app_session(max_sessions=2)
            app_session.add_app_container("public_session", AppContainer(
                server,
                transport=transport,
                topic=FARM_BROADCAST_TOPIC,
            ))
            app_session.add_app_container("private_session", AppContainer(
                server,
                transport=transport,
                topic=personal_topic,
            ))
            await app_session.start_session("public_session")
            await app_session.start_session("private_session")
            print(f"✅ A2A Transport started (NATS topic mode):")
            print(f"   Endpoint: {endpoint}")
            print(f"   Personal topic: {personal_topic}")
            print(f"   Broadcast topic: {FARM_BROADCAST_TOPIC}")

    except Exception as e:
        print(f"Transport encountered an error: {e}")
        if app_session:
            await app_session.stop_all_sessions()


async def main(enable_http: bool):
    """Run the A2A server with both HTTP and transport logic."""
    print()
    print("=" * 60)
    print("Satellite Agent Farm Server (A2A SDK)")
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

    request_handler = DefaultRequestHandler(
        agent_executor=SatelliteAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=AGENT_CARD,
        http_handler=request_handler
    )

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
