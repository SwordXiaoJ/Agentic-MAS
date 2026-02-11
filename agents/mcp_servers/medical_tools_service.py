"""
Medical Tools MCP Server

Provides medical literature search and reference tools via MCP protocol.
Based on lungo's weather_service.py pattern.

Usage:
    python -m agents.mcp_servers.medical_tools_service

This will start an MCP server that listens on the "medical_tools_service" topic
via NATS/SLIM transport.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP
from agntcy_app_sdk.factory import AgntcyFactory
from agntcy_app_sdk.app_sessions import AppContainer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medical_tools_service")

# Configuration
DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
TRANSPORT_SERVER_ENDPOINT = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")
SERVICE_TOPIC = "medical_tools_service"

# Initialize factory
factory = AgntcyFactory("agntcy_network.medical_mcp", enable_tracing=False)

# Create the MCP server
mcp = FastMCP()


# ============================================
# MCP Tools
# ============================================

@mcp.tool()
async def search_medical_literature(query: str, max_results: int = 5) -> str:
    """
    Search medical literature databases for relevant articles.

    Args:
        query: Search query (e.g., "pneumonia diagnosis")
        max_results: Maximum number of results to return

    Returns:
        Formatted search results
    """
    logger.info(f"Searching medical literature for: {query}")

    query_lower = query.lower()

    # Condition-specific literature results
    if "fracture" in query_lower or "bone" in query_lower:
        mock_results = [
            {
                "title": "AI-Assisted Bone Fracture Detection in X-ray Images: A Systematic Review",
                "authors": "Zhang Y, Roberts M, Anderson K",
                "journal": "Journal of Orthopedic Radiology",
                "year": 2024,
                "abstract": "Deep learning models achieve 95%+ accuracy in detecting fractures. Key imaging signs include cortical disruption, fracture lines, and bone fragment displacement."
            },
            {
                "title": "Radiographic Assessment of Bone Fractures: Best Practices",
                "authors": "Williams J, Chen H",
                "journal": "Radiology Today",
                "year": 2024,
                "abstract": "Standard X-ray views essential for fracture diagnosis. Look for: cortical breaks, trabecular disruption, soft tissue swelling, and periosteal reaction."
            },
            {
                "title": "Classification and Management of Long Bone Fractures",
                "authors": "Orthopedic Society Guidelines",
                "journal": "Clinical Orthopedics",
                "year": 2023,
                "abstract": "Fracture classification systems (AO/OTA) guide treatment. Key factors: fracture location, displacement degree, comminution, and joint involvement."
            }
        ]
    else:
        # Generic medical literature results
        mock_results = [
            {
                "title": f"Recent advances in {query} diagnosis",
                "authors": "Smith J, Johnson K",
                "journal": "Medical Imaging Journal",
                "year": 2024,
                "abstract": f"This study examines new techniques for {query} detection using AI."
            },
            {
                "title": f"Machine learning approaches to {query}",
                "authors": "Chen L, Wang M",
                "journal": "AI in Medicine",
                "year": 2024,
                "abstract": f"A comprehensive review of ML methods for {query} classification."
            },
            {
                "title": f"Clinical guidelines for {query}",
                "authors": "Medical Association",
                "journal": "Clinical Standards",
                "year": 2023,
                "abstract": f"Updated clinical guidelines for diagnosing and treating {query}."
            }
        ]

    # Format results
    output = f"Found {len(mock_results[:max_results])} results for '{query}':\n\n"
    for i, result in enumerate(mock_results[:max_results], 1):
        output += f"{i}. {result['title']}\n"
        output += f"   Authors: {result['authors']}\n"
        output += f"   Journal: {result['journal']} ({result['year']})\n"
        output += f"   Abstract: {result['abstract'][:100]}...\n\n"

    return output


@mcp.tool()
async def get_medical_reference(condition: str) -> str:
    """
    Get reference information about a medical condition.

    Args:
        condition: Medical condition name (e.g., "pneumonia", "tuberculosis")

    Returns:
        Reference information about the condition
    """
    logger.info(f"Getting reference for condition: {condition}")

    # Simulated reference data
    references = {
        "pneumonia": {
            "description": "Infection that inflames air sacs in one or both lungs",
            "symptoms": ["Cough", "Fever", "Difficulty breathing", "Chest pain"],
            "imaging_signs": ["Consolidation", "Air bronchograms", "Ground-glass opacity"],
            "common_causes": ["Bacteria", "Viruses", "Fungi"]
        },
        "tuberculosis": {
            "description": "Bacterial infection primarily affecting the lungs",
            "symptoms": ["Persistent cough", "Weight loss", "Night sweats", "Fever"],
            "imaging_signs": ["Cavitation", "Upper lobe infiltrates", "Miliary pattern"],
            "common_causes": ["Mycobacterium tuberculosis"]
        },
        "lung_nodule": {
            "description": "Small rounded growth in the lung",
            "symptoms": ["Often asymptomatic", "May cause cough if large"],
            "imaging_signs": ["Well-defined rounded opacity", "Size < 3cm"],
            "common_causes": ["Infection", "Inflammation", "Neoplasm"]
        },
        "fracture": {
            "description": "A break or crack in a bone, commonly caused by trauma or stress",
            "symptoms": ["Severe pain at injury site", "Swelling and bruising", "Deformity", "Limited mobility", "Tenderness"],
            "imaging_signs": ["Cortical disruption", "Fracture line visible on X-ray", "Displacement of bone fragments", "Soft tissue swelling", "Periosteal reaction in healing fractures"],
            "common_causes": ["Trauma (falls, accidents)", "Sports injuries", "Osteoporosis", "Stress/overuse", "Pathological conditions"]
        },
        "bone_fracture": {
            "description": "A break or crack in a bone, commonly caused by trauma or stress",
            "symptoms": ["Severe pain at injury site", "Swelling and bruising", "Deformity", "Limited mobility", "Tenderness"],
            "imaging_signs": ["Cortical disruption", "Fracture line visible on X-ray", "Displacement of bone fragments", "Soft tissue swelling", "Periosteal reaction in healing fractures"],
            "common_causes": ["Trauma (falls, accidents)", "Sports injuries", "Osteoporosis", "Stress/overuse", "Pathological conditions"]
        }
    }

    condition_lower = condition.lower().replace(" ", "_")
    if condition_lower in references:
        ref = references[condition_lower]
        output = f"Medical Reference: {condition.title()}\n\n"
        output += f"Description: {ref['description']}\n\n"
        output += f"Common Symptoms:\n"
        for symptom in ref['symptoms']:
            output += f"  - {symptom}\n"
        output += f"\nImaging Signs:\n"
        for sign in ref['imaging_signs']:
            output += f"  - {sign}\n"
        output += f"\nCommon Causes:\n"
        for cause in ref['common_causes']:
            output += f"  - {cause}\n"
        return output
    else:
        return f"No reference found for condition: {condition}"


@mcp.tool()
async def calculate_confidence_adjustment(
    base_confidence: float,
    image_quality: str = "good",
    patient_history_available: bool = False
) -> Dict[str, Any]:
    """
    Calculate adjusted confidence score based on clinical factors.

    Args:
        base_confidence: Initial confidence score (0-1)
        image_quality: Quality of the medical image ("poor", "fair", "good", "excellent")
        patient_history_available: Whether patient history is available

    Returns:
        Adjusted confidence and reasoning
    """
    logger.info(f"Calculating confidence adjustment: base={base_confidence}")

    quality_factors = {
        "poor": 0.7,
        "fair": 0.85,
        "good": 1.0,
        "excellent": 1.1
    }

    quality_factor = quality_factors.get(image_quality.lower(), 1.0)
    history_factor = 1.1 if patient_history_available else 1.0

    adjusted = min(base_confidence * quality_factor * history_factor, 1.0)

    return {
        "original_confidence": base_confidence,
        "adjusted_confidence": round(adjusted, 3),
        "quality_factor": quality_factor,
        "history_factor": history_factor,
        "reasoning": f"Adjusted from {base_confidence:.2f} to {adjusted:.2f} "
                    f"(image quality: {image_quality}, history: {patient_history_available})"
    }


# ============================================
# Server Main
# ============================================

async def main():
    """Start the MCP server via NATS/SLIM transport

    Supports both transport modes:
    - NATS: Uses topic-based routing
    - SLIM: Uses group session mode
    """
    logger.info(f"Starting Medical Tools MCP Server...")
    logger.info(f"Transport: {DEFAULT_MESSAGE_TRANSPORT}")
    logger.info(f"Endpoint: {TRANSPORT_SERVER_ENDPOINT}")
    logger.info(f"Topic: {SERVICE_TOPIC}")

    # Create transport
    transport = factory.create_transport(
        DEFAULT_MESSAGE_TRANSPORT,
        endpoint=TRANSPORT_SERVER_ENDPOINT,
        name=f"default/default/{SERVICE_TOPIC}"
    )

    # Create app session with MCP server
    app_session = factory.create_app_session(max_sessions=1)

    if DEFAULT_MESSAGE_TRANSPORT.upper() == "SLIM":
        # SLIM mode: group session without explicit topic
        app_container = AppContainer(
            mcp._mcp_server,
            transport=transport,
        )
        logger.info(f"MCP Server started in SLIM group mode")
    else:
        # NATS mode: topic-based routing
        app_container = AppContainer(
            mcp._mcp_server,
            transport=transport,
            topic=SERVICE_TOPIC,
        )
        logger.info(f"MCP Server started on topic: {SERVICE_TOPIC}")

    app_session.add_app_container("default_session", app_container)
    await app_session.start_all_sessions(keep_alive=True)


if __name__ == "__main__":
    asyncio.run(main())
