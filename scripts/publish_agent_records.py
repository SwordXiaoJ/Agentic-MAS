# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

"""Automation script for publishing agent records to ADS.

This module provides utilities for:
- Translating and validating agent records using OASF SDK
- Publishing agent records to the Agent Directory Service (ADS)
- Managing agent card records for classification agents
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional, List

import grpc
from google.protobuf.json_format import ParseDict, MessageToJson
from google.protobuf.struct_pb2 import Struct

logger = logging.getLogger(__name__)

# Check for required AGNTCY SDK imports
try:
    from agntcy.dir_sdk.client import Client, Config
    from agntcy.dir_sdk.models import core_v1, routing_v1
    from agntcy.oasfsdk.translation.v1.translation_service_pb2 import A2AToRecordRequest
    from agntcy.oasfsdk.translation.v1.translation_service_pb2_grpc import TranslationServiceStub
    from a2a.types import AgentCard
except ModuleNotFoundError as e:
    logger.error("Missing required AGNTCY SDK dependencies")
    logger.error("Please install dev dependencies by running:")
    logger.error("   pip install agntcy-dir agntcy-oasf-sdk-grpc-python")
    logger.error(f"Original error: {e}")
    sys.exit(1)

# Configuration constants
DEFAULT_OASF_HOST = "localhost"
DEFAULT_OASF_PORT = 31234
DEFAULT_ADS_ADDRESS = "localhost:8888"
DEFAULT_SCHEMA_VERSION = "0.8.0"
OASF_RECORDS_DIR = "oasf_records"



class OASFUtil:
    """Utility class for translating agent records using OASF SDK."""

    def __init__(self, host: str = DEFAULT_OASF_HOST, port: int = DEFAULT_OASF_PORT):
        self.address = f"{host}:{port}"
        self._channel = None
        self._translation_stub = None

    def connect(self):
        if self._channel is None:
            self._channel = grpc.insecure_channel(self.address)
            self._translation_stub = TranslationServiceStub(self._channel)

    def close(self):
        if self._channel:
            self._channel.close()
            self._channel = None
            self._translation_stub = None

    def a2a_to_oasf(self, agent_card: AgentCard, output_file: Optional[str] = None) -> core_v1.Record:
        """Translate an A2A AgentCard to an OASF record."""
        if not self._translation_stub:
            self.connect()

        dict_agent_card = json.loads(agent_card.model_dump_json())
        data = {"a2aCard": dict_agent_card}

        record_struct = Struct()
        record_struct.update(data)

        request = A2AToRecordRequest(data=record_struct)
        response = self._translation_stub.A2AToRecord(request)

        if output_file:
            with open(output_file, "w") as f:
                f.write(MessageToJson(response.record))

        # Convert to core_v1.Record
        record_dict = json.loads(MessageToJson(response.record))
        record = core_v1.Record()
        record.data.update(record_dict)
        return record


class AdsUtil:
    """Agent Directory Service (ADS) utility."""

    def __init__(self, server_address: str = DEFAULT_ADS_ADDRESS):
        self.client = None
        try:
            config = Config(server_address=server_address)
            self.client = Client(config)
            logger.info(f"Connected to ADS at {server_address}")
        except Exception as e:
            logger.error(f"Failed to create ADS client: {e}")

    def push_agent_record(self, record: core_v1.Record) -> Optional[str]:
        """Push an agent record to the directory and publish it."""
        if not self.client:
            logger.error("ADS client not initialized")
            return None

        try:
            refs = self.client.push([record])
            cid = refs[0].cid
            logger.info(f"Record pushed with CID: {cid}")

            # Publish record to routing
            record_refs = routing_v1.RecordRefs(refs=[core_v1.RecordRef(cid=cid)])
            pub_req = routing_v1.PublishRequest(record_refs=record_refs)
            self.client.publish(pub_req)

            logger.info(f"Successfully published record with CID: {cid}")
            return cid
        except Exception as e:
            logger.error(f"Failed to publish record: {e}")
            return None


def publish_card(card_path: Path, directory: AdsUtil) -> Optional[str]:
    """Publish an agent card from a file to the directory."""
    try:
        with open(card_path, "r") as f:
            card_data = json.load(f)

        card_data["schema_version"] = DEFAULT_SCHEMA_VERSION

        data_struct = Struct()
        ParseDict(card_data, data_struct)
        record = core_v1.Record(data=data_struct)

        logger.info(f"Pushing record for {card_path.stem}...")
        return directory.push_agent_record(record)
    except Exception as e:
        logger.error(f"Failed to load card from {card_path}: {e}")
        return None


def _import_agent_cards() -> List[dict]:
    """Import all available agent cards with their OASF metadata.

    Each agent's card.py declares:
    - AGENT_CARD: A2A AgentCard
    - OASF_SKILLS: OASF standard skill categories (required by ADS)
    - OASF_DOMAINS: OASF standard domain categories (optional)
    """
    try:
        from agents.org_a_medical import card as medical_card
        from agents.org_b_satellite import card as satellite_card
        from agents.org_c_general import card as general_card

        return [
            {
                "card": medical_card.AGENT_CARD,
                "oasf_skills": medical_card.OASF_SKILLS,
                "oasf_domains": getattr(medical_card, "OASF_DOMAINS", []),
            },
            {
                "card": satellite_card.AGENT_CARD,
                "oasf_skills": satellite_card.OASF_SKILLS,
                "oasf_domains": getattr(satellite_card, "OASF_DOMAINS", []),
            },
            {
                "card": general_card.AGENT_CARD,
                "oasf_skills": general_card.OASF_SKILLS,
                "oasf_domains": getattr(general_card, "OASF_DOMAINS", []),
            },
        ]
    except ImportError as e:
        logger.error(f"Failed to import agent cards: {e}")
        raise


def _enrich_oasf_record(card_file: str, oasf_skills: List[dict], oasf_domains: List[dict]):
    """Fill OASF skills/domains and fix schema compatibility.

    The OASF SDK A2AToRecord intentionally leaves skills/domains empty.
    We fill them from each agent's card.py OASF declarations.

    Also fixes v1.0.0 → v0.8.0 schema compatibility:
    - Rename card_schema_version → protocol_version in module data
    """
    with open(card_file, "r") as f:
        record_data = json.load(f)

    # Fill skills/domains
    if not record_data.get("skills") and oasf_skills:
        record_data["skills"] = oasf_skills
    if not record_data.get("domains") and oasf_domains:
        record_data["domains"] = oasf_domains

    # Fix module data for v0.8.0 schema compatibility
    for module in record_data.get("modules", []):
        data = module.get("data", {})
        if "card_schema_version" in data:
            data["protocol_version"] = data.pop("card_schema_version")

    with open(card_file, "w") as f:
        json.dump(record_data, f, indent=2)
    logger.info(f"Enriched OASF record: skills={[s['name'] for s in oasf_skills]}, domains={[d['name'] for d in oasf_domains]}")


def _process_agent_card(
    agent_card: AgentCard,
    oasf_skills: List[dict],
    oasf_domains: List[dict],
    oasf_util: OASFUtil,
    directory: AdsUtil,
) -> Optional[str]:
    """Process a single agent card - translate, enrich with OASF metadata, and publish."""
    Path(OASF_RECORDS_DIR).mkdir(exist_ok=True)
    file_name = agent_card.name.replace(" ", "_").replace("-", "_").rstrip()
    card_file = f"{OASF_RECORDS_DIR}/{file_name}.json"

    try:
        logger.info(f"Processing agent card: {agent_card.name}")
        oasf_util.a2a_to_oasf(agent_card, output_file=card_file)
        _enrich_oasf_record(card_file, oasf_skills, oasf_domains)
        cid = publish_card(Path(card_file), directory)

        if cid:
            logger.info(f"Successfully published {agent_card.name} with CID: {cid}")
            return cid
        else:
            logger.error(f"Failed to publish {agent_card.name}")
            return None
    except Exception as e:
        logger.error(f"Error processing agent card {agent_card.name}: {e}")
        return None


def publish_agent_records(cid_output_file: Optional[str] = None) -> bool:
    """Publish all agent records to the directory."""
    try:
        directory = AdsUtil()
        oasf_util = OASFUtil()
        oasf_util.connect()
    except Exception as e:
        logger.error(f"Failed to initialize required services: {e}")
        return False

    try:
        agent_entries = _import_agent_cards()
    except ImportError:
        return False

    success_count = 0
    total_count = len(agent_entries)
    cids = {}

    logger.info(f"Publishing {total_count} agent records...")

    for entry in agent_entries:
        agent_card = entry["card"]
        cid = _process_agent_card(
            agent_card, entry["oasf_skills"], entry["oasf_domains"],
            oasf_util, directory,
        )
        if cid:
            cids[agent_card.name] = cid
            success_count += 1

    oasf_util.close()
    logger.info(f"Published {success_count}/{total_count} agent records successfully")

    if cid_output_file:
        try:
            with open(cid_output_file, "w") as f:
                json.dump(cids, f, indent=2)
            logger.info(f"Wrote published CIDs to {cid_output_file}")
        except Exception as e:
            logger.error(f"Failed to write CIDs to file: {e}")

    return success_count == total_count


def main(cid_output_file="published_cids.json"):
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    Path(cid_output_file).write_text("")

    logger.info("Starting agent record publishing...")
    success = publish_agent_records(cid_output_file=cid_output_file)

    if success:
        logger.info("✅ All agent records published successfully")
    else:
        logger.error("❌ Some agent records failed to publish")
        sys.exit(1)


if __name__ == "__main__":
    main()
