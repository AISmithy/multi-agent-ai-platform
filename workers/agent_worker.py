"""RabbitMQ consumer — routes incoming messages to the correct agent and publishes the result."""

import asyncio
import json
import logging
import os

import aio_pika

from agents.document_agent import DocumentAgent
from agents.identity_agent import IdentityAgent
from agents.sanctions_agent import SanctionsAgent
from agents.risk_agent import RiskAgent
from agents.decision_agent import DecisionAgent
from agents.notification_agent import NotificationAgent
from memory.document_store import DocumentStore
from tools.ocr_client import OCRClient
from tools.liveness_client import LivenessClient
from tools.sanctions_client import SanctionsAPIClient

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_MAP = {
    "document":     "kyc.document",
    "identity":     "kyc.identity",
    "sanctions":    "kyc.sanctions",
    "risk":         "kyc.risk",
    "decision":     "kyc.decision",
    "notification": "kyc.notification",
}

logger = logging.getLogger(__name__)


def _build_agents() -> dict:
    doc_store    = DocumentStore()
    ocr          = OCRClient()
    liveness     = LivenessClient()
    sanctions_cl = SanctionsAPIClient()
    return {
        "document":     DocumentAgent(doc_store),
        "identity":     IdentityAgent(ocr, liveness, doc_store),
        "sanctions":    SanctionsAgent(sanctions_cl, doc_store),
        "risk":         RiskAgent(),
        "decision":     DecisionAgent(),
        "notification": NotificationAgent(),
    }


async def process_message(
    msg: aio_pika.IncomingMessage,
    agents: dict,
    channel: aio_pika.Channel,
):
    async with msg.process(requeue=False):
        payload    = json.loads(msg.body)
        agent_type = payload.get("agent_type")
        case_id    = payload.get("case_id")

        agent = agents.get(agent_type)
        if agent is None:
            logger.error("Unknown agent_type %s for case %s", agent_type, case_id)
            return

        try:
            result = await agent.run(case_id, payload)
        except Exception:
            logger.exception("Agent %s crashed for case %s", agent_type, case_id)
            return

        if msg.reply_to:
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(result.model_dump()).encode(),
                    correlation_id=msg.correlation_id,
                    content_type="application/json",
                ),
                routing_key=msg.reply_to,
            )


async def main():
    logging.basicConfig(level=logging.INFO)
    agents = _build_agents()

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        for agent_type, queue_name in QUEUE_MAP.items():
            queue = await channel.declare_queue(queue_name, durable=True)
            await queue.consume(
                lambda msg, at=agent_type, ch=channel: process_message(msg, agents, ch)
            )
            logger.info("Listening on queue %s", queue_name)

        logger.info("Worker ready — waiting for messages")
        await asyncio.Future()   # run forever


if __name__ == "__main__":
    asyncio.run(main())
