"""
MCP Client Wrapper for AGNTCY Agents

Provides a unified interface for agents to connect to MCP servers
and use external tools during classification.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPToolResult:
    """Result from calling an MCP tool"""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None


class MCPClient:
    """
    MCP Client for connecting agents to external tools.

    Supports two modes:
    1. stdio: Connect to MCP server via stdin/stdout
    2. http: Connect to MCP server via HTTP (like dir-mcp-server)

    Usage:
        client = MCPClient(config)
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("search_database", {"query": "pneumonia"})
        await client.disconnect()
    """

    def __init__(self, config: "MCPConfig"):
        self.config = config
        self.connected = False
        self._session = None
        self._tools_cache: List[Dict] = []

    async def connect(self) -> bool:
        """Connect to the MCP server"""
        try:
            if self.config.transport == "stdio":
                return await self._connect_stdio()
            elif self.config.transport == "http":
                return await self._connect_http()
            else:
                logger.error(f"Unknown MCP transport: {self.config.transport}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            return False

    async def _connect_stdio(self) -> bool:
        """Connect via stdio transport"""
        try:
            # Import MCP SDK
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args or [],
                env=self.config.env or {}
            )

            # Create stdio client
            read_stream, write_stream = await stdio_client(server_params).__aenter__()
            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

            self.connected = True
            logger.info(f"Connected to MCP server via stdio: {self.config.command}")
            return True

        except ImportError:
            logger.warning("MCP SDK not installed. Install with: pip install mcp")
            return False
        except Exception as e:
            logger.error(f"Stdio connection failed: {e}")
            return False

    async def _connect_http(self) -> bool:
        """Connect via HTTP transport (for servers like dir-mcp-server)"""
        try:
            import aiohttp

            # Test connection
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.config.url}/health") as resp:
                    if resp.status == 200:
                        self.connected = True
                        logger.info(f"Connected to MCP server via HTTP: {self.config.url}")
                        return True

            # If no health endpoint, try listing tools
            self.connected = True
            tools = await self.list_tools()
            if tools:
                logger.info(f"Connected to MCP server via HTTP: {self.config.url}")
                return True

            self.connected = False
            return False

        except Exception as e:
            logger.error(f"HTTP connection failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from the MCP server"""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
        self.connected = False
        self._session = None

    async def list_tools(self) -> List[Dict]:
        """List available tools from the MCP server"""
        if not self.connected:
            return []

        try:
            if self.config.transport == "stdio" and self._session:
                tools_response = await self._session.list_tools()
                self._tools_cache = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema
                    }
                    for tool in tools_response.tools
                ]
            elif self.config.transport == "http":
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.config.url}/tools/list",
                        json={}
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self._tools_cache = data.get("tools", [])

            return self._tools_cache

        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """
        Call an MCP tool with arguments.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            MCPToolResult with success status and result/error
        """
        if not self.connected:
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error="Not connected to MCP server"
            )

        try:
            if self.config.transport == "stdio" and self._session:
                result = await self._session.call_tool(tool_name, arguments)
                return MCPToolResult(
                    tool_name=tool_name,
                    success=True,
                    result=result.content
                )

            elif self.config.transport == "http":
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.config.url}/tools/call",
                        json={
                            "name": tool_name,
                            "arguments": arguments
                        }
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return MCPToolResult(
                                tool_name=tool_name,
                                success=True,
                                result=data.get("content", data)
                            )
                        else:
                            error_text = await resp.text()
                            return MCPToolResult(
                                tool_name=tool_name,
                                success=False,
                                result=None,
                                error=f"HTTP {resp.status}: {error_text}"
                            )

            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error="Unknown transport type"
            )

        except Exception as e:
            logger.error(f"Failed to call MCP tool {tool_name}: {e}")
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error=str(e)
            )

    def get_tools_for_llm(self) -> List[Dict]:
        """
        Get tools in LLM-compatible format (OpenAI function calling schema).

        Returns:
            List of tool definitions for LLM
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                }
            }
            for tool in self._tools_cache
        ]
