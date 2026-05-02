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
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

import aiohttp

from mcp.server.fastmcp import FastMCP
from agntcy_app_sdk.factory import AgntcyFactory
from agntcy_app_sdk.app_sessions import AppContainer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medical_tools_service")

# Configuration
DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "NATS")
TRANSPORT_SERVER_ENDPOINT = os.getenv("TRANSPORT_SERVER_ENDPOINT", "nats://localhost:4222")
SERVICE_TOPIC = "medical_tools_service"

# PubMed E-utilities API
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_LINK_BASE = "https://pubmed.ncbi.nlm.nih.gov"

# Initialize IOA Observe SDK
try:
    from ioa_observe.sdk import Observe
    Observe.init(
        app_name="medical-mcp-server",
        api_endpoint=os.getenv("OTLP_HTTP_ENDPOINT", "http://localhost:4318"),
    )
    logger.info("IOA Observe SDK initialized for MCP Server")
except ImportError:
    logger.warning("ioa-observe-sdk not installed, observability disabled")

# Initialize factory
factory = AgntcyFactory("agntcy_network.medical_mcp", enable_tracing=False)

# Create the MCP server
mcp = FastMCP()


# ============================================
# PubMed API Helpers
# ============================================

async def _search_pubmed(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search PubMed via E-utilities and return structured results."""
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Step 1: ESearch — get PMIDs
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }
        async with session.get(PUBMED_SEARCH_URL, params=search_params) as resp:
            resp.raise_for_status()
            search_data = await resp.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        # Step 2: ESummary — get paper metadata
        summary_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json",
        }
        async with session.get(PUBMED_SUMMARY_URL, params=summary_params) as resp:
            resp.raise_for_status()
            summary_data = await resp.json()

        results = []
        for pmid in id_list:
            article = summary_data.get("result", {}).get(pmid, {})
            if not article or "error" in article:
                continue

            authors_list = article.get("authors", [])
            authors = ", ".join(a.get("name", "") for a in authors_list[:3])
            if len(authors_list) > 3:
                authors += " et al."

            journal = article.get("fulljournalname", article.get("source", ""))
            pub_date = article.get("pubdate", "")
            year = pub_date[:4] if pub_date else ""

            results.append({
                "title": article.get("title", "Untitled"),
                "authors": authors,
                "journal": journal,
                "year": year,
                "url": f"{PUBMED_LINK_BASE}/{pmid}/",
            })

        return results


# ============================================
# MCP Tools
# ============================================

def _simplify_query(query: str) -> str:
    """Simplify a long query for PubMed by keeping key medical terms."""
    # Remove filler words
    stopwords = {
        "and", "or", "the", "a", "an", "for", "of", "in", "on", "with",
        "to", "is", "are", "from", "by", "key", "evidence", "findings",
        "imaging", "signs", "diagnostic", "criteria", "identified",
        "suspected", "condition", "image", "medical", "radiograph",
    }
    words = query.replace("'", "").replace('"', "").split()
    kept = [w for w in words if w.lower() not in stopwords]
    # Keep at most 6 terms
    return " ".join(kept[:6])


@mcp.tool()
async def search_medical_literature(query: str, max_results: int = 5) -> str:
    """
    Search PubMed medical literature for relevant articles.

    Args:
        query: Search query (e.g., "pneumonia diagnosis")
        max_results: Maximum number of results to return

    Returns:
        Formatted search results with titles, authors, journal, and PubMed links
    """
    logger.info(f"Searching PubMed for: {query}")

    try:
        results = await _search_pubmed(query, max_results)

        # Retry with simplified query if no results
        if not results:
            simplified = _simplify_query(query)
            if simplified != query:
                logger.info(f"No results, retrying with simplified query: {simplified}")
                results = await _search_pubmed(simplified, max_results)

        if not results:
            return f"No results found on PubMed for '{query}'"

        output = f"Found {len(results)} results for '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r['title']}\n"
            output += f"   Authors: {r['authors']}\n"
            output += f"   Journal: {r['journal']} ({r['year']})\n"
            output += f"   URL: {r['url']}\n\n"

        return output

    except Exception as e:
        logger.warning(f"PubMed API failed ({e}), returning error")
        return f"PubMed search failed for '{query}': {e}"


# ============================================
# MedlinePlus API Helpers
# ============================================

MEDLINEPLUS_SEARCH_URL = "https://wsearch.nlm.nih.gov/ws/query"


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def _search_medlineplus(condition: str) -> Optional[Dict[str, str]]:
    """Search MedlinePlus Health Topics for a condition summary."""
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        params = {
            "db": "healthTopics",
            "term": condition,
            "retmax": 1,
        }
        async with session.get(MEDLINEPLUS_SEARCH_URL, params=params) as resp:
            if resp.status != 200:
                return None
            xml_text = await resp.text()

    try:
        root = ET.fromstring(xml_text)
        doc = root.find(".//document")
        if doc is None:
            return None

        url = doc.get("url", "")
        title = ""
        summary = ""

        for content in doc.findall("content"):
            name = content.get("name", "")
            text = content.text or ""
            if name == "title":
                title = text.strip()
            elif name == "FullSummary":
                summary = _strip_html(text)
            elif name == "snippet" and not summary:
                summary = _strip_html(text)

        if not title or not summary:
            return None

        return {"title": title, "summary": summary, "url": url}
    except ET.ParseError:
        return None


@mcp.tool()
async def get_medical_reference(condition: str) -> str:
    """
    Get reference information about a medical condition from MedlinePlus (NIH).

    Args:
        condition: Medical condition name (e.g., "pneumonia", "fracture")

    Returns:
        Medical condition summary with description and MedlinePlus link
    """
    logger.info(f"Getting MedlinePlus reference for: {condition}")

    try:
        result = await _search_medlineplus(condition)
        if not result:
            return f"No MedlinePlus reference found for: {condition}"

        # Truncate long summaries
        summary = result["summary"]
        if len(summary) > 1000:
            summary = summary[:1000] + "..."

        output = f"Medical Reference: {result['title']}\n\n"
        output += f"Description: {summary}\n\n"
        output += f"Source: {result['url']}"
        return output

    except Exception as e:
        logger.warning(f"MedlinePlus API failed ({e}), returning error")
        return f"MedlinePlus lookup failed for '{condition}': {e}"


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

    # MCP server always requires a topic (unlike A2A agents in SLIM mode)
    app_container = AppContainer(
        mcp._mcp_server,
        transport=transport,
        topic=SERVICE_TOPIC,
    )
    logger.info(f"MCP Server started on topic: {SERVICE_TOPIC} (transport: {DEFAULT_MESSAGE_TRANSPORT})")

    app_session.add_app_container("default_session", app_container)
    await app_session.start_all_sessions(keep_alive=True)


if __name__ == "__main__":
    asyncio.run(main())
