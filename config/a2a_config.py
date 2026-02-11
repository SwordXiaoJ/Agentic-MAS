"""
A2A Configuration

Matches lungo's config.py pattern for A2A SDK.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Automatically loads from `.env` or `.env.local`

# ============================================
# Transport Configuration
# ============================================

# Transport type: "NATS" or "SLIM"
DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")

# Transport endpoint
# - For NATS: nats://localhost:4222
# - For SLIM: http://localhost:46357
TRANSPORT_SERVER_ENDPOINT = os.getenv(
    "TRANSPORT_SERVER_ENDPOINT",
    "nats://localhost:4222"
)

# Broadcast topic for all agents
FARM_BROADCAST_TOPIC = os.getenv("FARM_BROADCAST_TOPIC", "agents.broadcast")

# ============================================
# HTTP Configuration
# ============================================

# Enable HTTP REST API on farm agents
ENABLE_HTTP = os.getenv("ENABLE_HTTP", "true").lower() in ("true", "1", "yes")

# ============================================
# Logging Configuration
# ============================================

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO").upper()

# ============================================
# Agent Ports
# ============================================

MEDICAL_AGENT_PORT = int(os.getenv("MEDICAL_AGENT_PORT", "9001"))
SATELLITE_AGENT_PORT = int(os.getenv("SATELLITE_AGENT_PORT", "9002"))
GENERAL_AGENT_PORT = int(os.getenv("GENERAL_AGENT_PORT", "9003"))

# ============================================
# Display Configuration
# ============================================

def print_config():
    """Print current configuration (for debugging)"""
    print()
    print("=" * 60)
    print("A2A Configuration")
    print("=" * 60)
    print(f"Transport Type: {DEFAULT_MESSAGE_TRANSPORT}")
    print(f"Transport Endpoint: {TRANSPORT_SERVER_ENDPOINT}")
    print(f"Broadcast Topic: {FARM_BROADCAST_TOPIC}")
    print(f"HTTP Enabled: {ENABLE_HTTP}")
    print(f"Logging Level: {LOGGING_LEVEL}")
    print("=" * 60)
    print()
