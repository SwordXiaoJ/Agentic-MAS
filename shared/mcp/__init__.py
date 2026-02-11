# MCP Integration for AGNTCY Agents
#
# For AGNTCY/Lungo style MCP (NATS/SLIM transport):
#   Use factory.create_client("MCP", ...) directly from agntcy_app_sdk
#   See: agents/org_a_medical/agent.py for example
#
# For generic MCP (stdio/http transport):
#   Use MCPClient or MCPAgentMixin from this module

from shared.mcp.client import MCPClient, MCPToolResult
from shared.mcp.config import MCPConfig, load_mcp_config
from shared.mcp.agent_mixin import MCPAgentMixin

__all__ = [
    "MCPClient",
    "MCPToolResult",
    "MCPConfig",
    "load_mcp_config",
    "MCPAgentMixin",
]
