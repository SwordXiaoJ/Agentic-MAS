# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""
LLM Configuration

Follows lungo's pattern using litellm for unified LLM access.
Supports: OpenAI, Azure OpenAI, Anthropic, Groq, Ollama, NVIDIA NIM, and more.
"""

import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ============================================
# LLM Model Configuration
# ============================================

# Primary LLM model (following lungo's pattern)
# Format: "provider/model_name"
# Examples:
#   - "openai/gpt-4o-mini"
#   - "anthropic/claude-3-5-sonnet-20241022"
#   - "azure/your_deployment_name"
#   - "groq/llama-3.3-70b-versatile"
#   - "ollama/llama3.2"
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

# LiteLLM Proxy (optional - for centralized LLM management)
LITELLM_PROXY_BASE_URL = os.getenv("LITELLM_PROXY_BASE_URL", None)
LITELLM_PROXY_API_KEY = os.getenv("LITELLM_PROXY_API_KEY", None)

# LLM Parameters
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# ============================================
# Provider-specific API Keys
# ============================================

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Azure OpenAI
AZURE_API_KEY = os.getenv("AZURE_API_KEY", None)
AZURE_API_BASE = os.getenv("AZURE_API_BASE", None)
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", None)

# Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY", None)

# Ollama
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

# NVIDIA NIM
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", None)


# ============================================
# Helper Functions
# ============================================

def get_llm_config() -> dict:
    """
    Get LLM configuration dictionary.

    Returns:
        dict: Configuration for initializing LLM
    """
    config = {
        "model": LLM_MODEL,
        "temperature": OPENAI_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }

    # Add proxy configuration if available
    if LITELLM_PROXY_BASE_URL and LITELLM_PROXY_API_KEY:
        config["api_base"] = LITELLM_PROXY_BASE_URL
        config["api_key"] = LITELLM_PROXY_API_KEY
        logger.info(f"Using LiteLLM proxy: {LITELLM_PROXY_BASE_URL}")

    return config


def create_llm():
    """
    Create LangChain-compatible LLM instance.

    Returns a LangChain chat model that supports:
    - .invoke() for synchronous calls
    - .ainvoke() for async calls
    - .with_structured_output() for structured outputs

    Returns:
        LangChain ChatModel instance
    """
    # Parse provider and model from LLM_MODEL (format: "provider/model")
    if "/" in LLM_MODEL:
        provider, model_name = LLM_MODEL.split("/", 1)
    else:
        provider = "openai"
        model_name = LLM_MODEL

    provider = provider.lower()
    logger.info(f"Initializing LLM: {LLM_MODEL}")

    try:
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model_name,
                temperature=OPENAI_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )

        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model_name,
                temperature=OPENAI_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )

        elif provider == "azure":
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                deployment_name=model_name,
                api_version=AZURE_API_VERSION,
                temperature=OPENAI_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )

        else:
            # Fallback: use LlamaIndex LiteLLM for other providers
            # (groq, ollama, nvidia, etc.)
            from llama_index.llms.litellm import LiteLLM

            class _LiteLLMWrapper:
                """Wrap LlamaIndex LiteLLM to provide LangChain interface"""

                def __init__(self, llm):
                    self._llm = llm

                def invoke(self, messages):
                    # Convert messages to prompt
                    if isinstance(messages, list):
                        prompt = "\n".join([
                            f"{m.type}: {m.content}" if hasattr(m, 'type') else str(m)
                            for m in messages
                        ])
                    else:
                        prompt = str(messages)
                    response = self._llm.complete(prompt)
                    return type("AIMessage", (), {"content": response.text})()

                async def ainvoke(self, messages):
                    if isinstance(messages, list):
                        prompt = "\n".join([
                            f"{m.type}: {m.content}" if hasattr(m, 'type') else str(m)
                            for m in messages
                        ])
                    else:
                        prompt = str(messages)
                    response = await self._llm.acomplete(prompt)
                    return type("AIMessage", (), {"content": response.text})()

                def with_structured_output(self, schema, **kwargs):
                    # Return self - structured output not supported for this provider
                    logger.warning(f"with_structured_output not supported for provider: {provider}")
                    return self

            llm = LiteLLM(
                model=LLM_MODEL,
                temperature=OPENAI_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )
            return _LiteLLMWrapper(llm)

    except ImportError as e:
        logger.error(f"Failed to import LLM libraries: {e}")
        raise


def validate_llm_config() -> bool:
    """
    Validate LLM configuration.

    Returns:
        bool: True if configuration is valid
    """
    if not LLM_MODEL:
        logger.error("LLM_MODEL is not configured")
        return False

    # Check for required API keys based on provider
    provider = LLM_MODEL.split("/")[0].lower()

    if provider == "openai" and not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set")
        return False
    elif provider == "anthropic" and not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set")
        return False
    elif provider == "azure" and not (AZURE_API_KEY or LITELLM_PROXY_API_KEY):
        logger.warning("AZURE_API_KEY or LITELLM_PROXY_API_KEY is not set")
        return False
    elif provider == "groq" and not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY is not set")
        return False

    logger.info(f"LLM configuration validated: {LLM_MODEL}")
    return True


# ============================================
# Initialization Log
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("LLM Configuration")
    print("=" * 60)
    print(f"Model: {LLM_MODEL}")
    print(f"Temperature: {OPENAI_TEMPERATURE}")
    print(f"Max Tokens: {LLM_MAX_TOKENS}")
    print(f"Proxy: {LITELLM_PROXY_BASE_URL or 'Not configured'}")
    print()
    print(f"Valid: {validate_llm_config()}")
    print("=" * 60)
