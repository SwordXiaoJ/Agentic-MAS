"""
MCP Agent Mixin

Provides MCP tool integration capabilities that can be mixed into any agent.
"""

import logging
from typing import Any, Dict, List, Optional

from shared.mcp.client import MCPClient, MCPToolResult
from shared.mcp.config import MCPConfig, load_mcp_config

logger = logging.getLogger(__name__)


class MCPAgentMixin:
    """
    Mixin class that adds MCP tool capabilities to an agent.

    Usage:
        class MyAgent(MCPAgentMixin):
            def __init__(self):
                self.init_mcp("medical")  # or "satellite", "general"

            async def classify(self, request):
                # Use MCP tools during classification
                if self.mcp_enabled:
                    result = await self.call_mcp_tool("search_pubmed", {"query": "pneumonia"})
                    if result.success:
                        # Use the tool result to enhance classification
                        pass
    """

    _mcp_client: Optional[MCPClient] = None
    _mcp_config: Optional[MCPConfig] = None
    _mcp_connected: bool = False

    def init_mcp(self, agent_type: str) -> bool:
        """
        Initialize MCP for this agent.

        Args:
            agent_type: Agent type (medical, satellite, general)

        Returns:
            True if MCP was initialized successfully
        """
        self._mcp_config = load_mcp_config(agent_type)
        if self._mcp_config and self._mcp_config.enabled:
            self._mcp_client = MCPClient(self._mcp_config)
            logger.info(f"MCP initialized for {agent_type} agent: {self._mcp_config.name}")
            return True
        return False

    @property
    def mcp_enabled(self) -> bool:
        """Check if MCP is enabled and configured"""
        return self._mcp_config is not None and self._mcp_config.enabled

    async def connect_mcp(self) -> bool:
        """Connect to the MCP server"""
        if not self._mcp_client:
            return False

        self._mcp_connected = await self._mcp_client.connect()
        if self._mcp_connected:
            tools = await self._mcp_client.list_tools()
            logger.info(f"MCP connected with {len(tools)} tools available")
        return self._mcp_connected

    async def disconnect_mcp(self):
        """Disconnect from the MCP server"""
        if self._mcp_client:
            await self._mcp_client.disconnect()
            self._mcp_connected = False

    async def list_mcp_tools(self) -> List[Dict]:
        """List available MCP tools"""
        if not self._mcp_client or not self._mcp_connected:
            return []
        return await self._mcp_client.list_tools()

    async def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            MCPToolResult
        """
        if not self._mcp_client:
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error="MCP not initialized"
            )

        if not self._mcp_connected:
            # Try to connect first
            if not await self.connect_mcp():
                return MCPToolResult(
                    tool_name=tool_name,
                    success=False,
                    result=None,
                    error="Failed to connect to MCP server"
                )

        # Check if tool is allowed
        if self._mcp_config.allowed_tools:
            if tool_name not in self._mcp_config.allowed_tools:
                return MCPToolResult(
                    tool_name=tool_name,
                    success=False,
                    result=None,
                    error=f"Tool '{tool_name}' not in allowed_tools list"
                )

        return await self._mcp_client.call_tool(tool_name, arguments)

    def get_mcp_tools_for_llm(self) -> List[Dict]:
        """
        Get MCP tools in LLM-compatible format for function calling.

        Returns:
            List of tool definitions
        """
        if not self._mcp_client:
            return []
        return self._mcp_client.get_tools_for_llm()

    async def enhance_with_mcp(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use MCP tools to enhance classification context.

        Override this method in subclasses for agent-specific tool usage.

        Args:
            prompt: User prompt
            context: Current classification context

        Returns:
            Enhanced context with MCP tool results
        """
        # Default implementation - override in subclass
        return context
