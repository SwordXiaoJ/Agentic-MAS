# MCP Integration for AGNTCY Agents

## AGNTCY/Lungo Style (Recommended)

使用 `AgntcyFactory` 直接连接 MCP 服务器，通过 NATS/SLIM 消息传输。

### 架构

```
Agent → factory.create_client("MCP") → NATS/SLIM → MCP Server (FastMCP)
```

### 启动 MCP 服务

```bash
# 1. 启动基础设施 (包含 NATS)
./scripts/start_infrastructure.sh

# 2. 启动医学工具 MCP 服务
./scripts/start_mcp_medical.sh
```

### 启用 Agent 的 MCP

```bash
# .env
USE_MCP=true
MCP_TOPIC=medical_tools_service
```

### 在 Agent 中使用 MCP (Lungo 风格)

```python
from agntcy_app_sdk.factory import AgntcyFactory

# 创建 factory
factory = AgntcyFactory("my_agent", enable_tracing=False)

# 创建 transport
transport = factory.create_transport(
    "NATS",
    endpoint="nats://localhost:4222",
    name="default/default/my_mcp_client"
)

# 创建 MCP client
mcp_client = factory.create_client(
    "MCP",
    agent_topic="medical_tools_service",
    transport=transport,
    message_timeout=30
)

# 使用 MCP
async with mcp_client as client:
    # 列出工具
    response = await client.list_tools()
    tools = [tool.name for tool in response.tools]

    # 调用工具
    result = await client.call_tool(
        name="search_medical_literature",
        arguments={"query": "pneumonia", "max_results": 3}
    )

    # 解析结果
    content = result.content[0].text
```

### 创建 MCP Server (Lungo 风格)

```python
# agents/mcp_servers/my_service.py
from mcp.server.fastmcp import FastMCP
from agntcy_app_sdk.factory import AgntcyFactory
from agntcy_app_sdk.app_sessions import AppContainer

mcp = FastMCP()
factory = AgntcyFactory("my_mcp_server")

@mcp.tool()
async def my_tool(query: str) -> str:
    """工具描述"""
    return f"Result: {query}"

async def main():
    transport = factory.create_transport(
        "NATS",
        endpoint="nats://localhost:4222",
        name="default/default/my_service"
    )

    app_session = factory.create_app_session(max_sessions=1)
    app_session.add_app_container("default", AppContainer(
        mcp._mcp_server,
        transport=transport,
        topic="my_service"
    ))
    await app_session.start_all_sessions(keep_alive=True)
```

---

## 内置 MCP 服务

| 服务 | Topic | 工具 |
|------|-------|------|
| Medical Tools | `medical_tools_service` | search_medical_literature, get_medical_reference |

## 参考实现

- **Agent**: [agents/org_a_medical/agent.py](../../agents/org_a_medical/agent.py) - `_enhance_with_mcp()` 方法
- **Server**: [agents/mcp_servers/medical_tools_service.py](../../agents/mcp_servers/medical_tools_service.py)
- **Lungo**: `lungo/agents/farms/colombia/agent.py` - `_get_weather_forecast()` 方法
