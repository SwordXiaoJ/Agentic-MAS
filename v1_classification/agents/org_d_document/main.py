#!/usr/bin/env python3
"""
Farm server for Document Analysis agent (Org D) — A2A + PydanticAI.

No Observe.init / OpenTelemetry in this entrypoint (avoids OTLP 4318 hangs).
"""

import asyncio
import os

from dotenv import load_dotenv
from uvicorn import Config, Server

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from agntcy_app_sdk.app_sessions import AppContainer
from agntcy_app_sdk.factory import AgntcyFactory
from agntcy_app_sdk.semantic.a2a.protocol import A2AProtocol

from agents.org_d_document.agent_executor_a2a import DocumentAgentExecutor
from agents.org_d_document.card import AGENT_CARD, AGENT_ID

try:
    from config.security_config import get_security_config

    SECURITY_CONFIG_AVAILABLE = True
except ImportError:
    SECURITY_CONFIG_AVAILABLE = False

load_dotenv()

DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
TRANSPORT_SERVER_ENDPOINT = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")
FARM_BROADCAST_TOPIC = os.getenv("FARM_BROADCAST_TOPIC", "agents.broadcast")
ENABLE_HTTP = os.getenv("ENABLE_HTTP", "true").lower() in ("true", "1", "yes")

HTTP_PORT = int(os.getenv("DOCUMENT_AGENT_PORT", "9004"))
HTTP_HOST = "0.0.0.0"

security_config = None
if SECURITY_CONFIG_AVAILABLE:
    security_config = get_security_config()

factory = AgntcyFactory("agntcy_network.document_agent", enable_tracing=False)


async def run_http_server(server):
    try:
        config = Config(app=server.build(), host=HTTP_HOST, port=HTTP_PORT, loop="asyncio")
        userver = Server(config)
        await userver.serve()
    except Exception as e:
        print(f"HTTP server encountered an error: {e}")


async def run_transport(server, transport_type, endpoint):
    app_session = None
    try:
        personal_topic = A2AProtocol.create_agent_topic(AGENT_CARD)

        transport_kwargs = {
            "endpoint": endpoint,
            "name": f"default/default/{personal_topic}",
        }

        if transport_type.upper() == "SLIM" and security_config:
            transport_kwargs.update(security_config.get_slim_transport_kwargs())

        transport = factory.create_transport(transport_type, **transport_kwargs)

        if transport_type.upper() == "SLIM":
            app_session = factory.create_app_session(max_sessions=1)
            app_session.add_app_container(
                "group_session",
                AppContainer(server, transport=transport),
            )
            await app_session.start_session("group_session")
            print(f"✅ A2A Transport started (SLIM): {endpoint}")
        else:
            app_session = factory.create_app_session(max_sessions=2)
            app_session.add_app_container(
                "public_session",
                AppContainer(server, transport=transport, topic=FARM_BROADCAST_TOPIC),
            )
            app_session.add_app_container(
                "private_session",
                AppContainer(server, transport=transport, topic=personal_topic),
            )
            await app_session.start_session("public_session")
            await app_session.start_session("private_session")
            print(f"✅ A2A Transport started (NATS): {endpoint}")
            print(f"   Personal topic: {personal_topic}")

    except Exception as e:
        print(f"Transport encountered an error: {e}")
        if app_session:
            await app_session.stop_all_sessions()


async def main(enable_http: bool):
    print("=" * 60)
    print("Document Analysis Agent (Org D) — PydanticAI + A2A")
    print(f"Agent: {AGENT_ID} | Transport: {DEFAULT_MESSAGE_TRANSPORT}")
    print("=" * 60)

    request_handler = DefaultRequestHandler(
        agent_executor=DocumentAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(agent_card=AGENT_CARD, http_handler=request_handler)

    tasks = []
    if enable_http:
        tasks.append(asyncio.create_task(run_http_server(server)))
    tasks.append(
        asyncio.create_task(run_transport(server, DEFAULT_MESSAGE_TRANSPORT, TRANSPORT_SERVER_ENDPOINT))
    )

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main(ENABLE_HTTP))
    except KeyboardInterrupt:
        print("\nShutting down.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
