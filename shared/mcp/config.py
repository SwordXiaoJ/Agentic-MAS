"""
MCP Configuration for AGNTCY Agents

Each agent can have its own MCP configuration to connect to
different external tools based on its specialization.
"""

import os
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MCPConfig:
    """
    MCP Server configuration.

    Supports two transport types:
    - stdio: Run MCP server as subprocess (command + args)
    - http: Connect to running MCP server via HTTP (url)
    """
    name: str
    transport: str  # "stdio" or "http"
    enabled: bool = True

    # For stdio transport
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None

    # For http transport
    url: Optional[str] = None

    # Tool filtering (optional)
    allowed_tools: Optional[List[str]] = None


def load_mcp_config(agent_type: str) -> Optional[MCPConfig]:
    """
    Load MCP configuration for a specific agent type.

    Looks for config in:
    1. Environment variable: MCP_CONFIG_{AGENT_TYPE} (JSON string)
    2. Config file: config/mcp/{agent_type}.json
    3. Default config file: config/mcp/default.json

    Args:
        agent_type: Agent type (e.g., "medical", "satellite", "general")

    Returns:
        MCPConfig if found and enabled, None otherwise
    """
    # 1. Check environment variable
    env_key = f"MCP_CONFIG_{agent_type.upper()}"
    env_config = os.getenv(env_key)
    if env_config:
        try:
            config_dict = json.loads(env_config)
            return _dict_to_config(config_dict, agent_type)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {env_key}: {e}")

    # 2. Check agent-specific config file
    project_root = Path(__file__).parent.parent.parent
    agent_config_path = project_root / "config" / "mcp" / f"{agent_type}.json"
    if agent_config_path.exists():
        return _load_config_file(agent_config_path, agent_type)

    # 3. Check default config file
    default_config_path = project_root / "config" / "mcp" / "default.json"
    if default_config_path.exists():
        return _load_config_file(default_config_path, agent_type)

    logger.debug(f"No MCP config found for agent type: {agent_type}")
    return None


def _load_config_file(path: Path, agent_type: str) -> Optional[MCPConfig]:
    """Load MCP config from JSON file"""
    try:
        with open(path) as f:
            config_dict = json.load(f)
        return _dict_to_config(config_dict, agent_type)
    except Exception as e:
        logger.error(f"Failed to load MCP config from {path}: {e}")
        return None


def _dict_to_config(config_dict: Dict[str, Any], agent_type: str) -> Optional[MCPConfig]:
    """Convert dictionary to MCPConfig"""
    if not config_dict.get("enabled", True):
        logger.debug(f"MCP disabled for {agent_type}")
        return None

    transport = config_dict.get("transport", "stdio")

    return MCPConfig(
        name=config_dict.get("name", f"{agent_type}-mcp"),
        transport=transport,
        enabled=config_dict.get("enabled", True),
        command=config_dict.get("command"),
        args=config_dict.get("args"),
        env=config_dict.get("env"),
        url=config_dict.get("url"),
        allowed_tools=config_dict.get("allowed_tools")
    )


# ============================================
# Example configurations for each agent type
# ============================================

EXAMPLE_CONFIGS = {
    "medical": {
        "name": "medical-tools",
        "transport": "stdio",
        "enabled": True,
        "command": "npx",
        "args": ["-y", "@anthropic/mcp-server-pubmed"],
        "allowed_tools": ["search_pubmed", "get_article"]
    },
    "satellite": {
        "name": "satellite-tools",
        "transport": "http",
        "enabled": True,
        "url": "http://localhost:3001",  # Custom GIS MCP server
        "allowed_tools": ["geocode", "get_satellite_data", "analyze_terrain"]
    },
    "general": {
        "name": "general-tools",
        "transport": "stdio",
        "enabled": True,
        "command": "npx",
        "args": ["-y", "@anthropic/mcp-server-brave-search"],
        "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
        "allowed_tools": ["brave_search"]
    }
}
