import asyncio
import json
import uuid
import aio_pika
import os
from orchestrator.case_state import CaseState

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_MAP = {
    "document":     "kyc.document",
    "identity":     "kyc.identity",
    "sanctions":    "kyc.sanctions",
    "risk":         "kyc.risk",
    "decision":     "kyc.decision",
    "notification": "kyc.notification",
}
REPLY_TIMEOUT = 30  # seconds


async def dispatch_agent(agent_type: str, state: CaseState) -> dict:
    """Publish task to agent queue, wait for reply."""
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()

        # Temporary reply queue for this task
        reply_queue = await channel.declare_queue(
            f"kyc.reply.{state.case_id}.{agent_type}",
            exclusive=True,
            auto_delete=True,
        )

        correlation_id = str(uuid.uuid4())
        message_body = json.dumps({
            "case_id":         state.case_id,
            "client_ref":      state.client_ref,
            "agent_type":      agent_type,
            "doc_refs":        state.doc_refs,
            "agent_results":   state.agent_results,
            "flags":           state.flags,
            "idempotency_key": f"{state.case_id}_{agent_type}_attempt_{state.retry_counts.get(agent_type, 0)}",
        }).encode()

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=message_body,
                correlation_id=correlation_id,
                reply_to=reply_queue.name,
                content_type="application/json",
            ),
            routing_key=QUEUE_MAP[agent_type],
        )

        # Wait for reply
        future = asyncio.get_event_loop().create_future()

        async def on_message(msg: aio_pika.IncomingMessage):
            async with msg.process():
                if msg.correlation_id == correlation_id:
                    future.set_result(json.loads(msg.body))

        await reply_queue.consume(on_message)

        try:
            return await asyncio.wait_for(future, timeout=REPLY_TIMEOUT)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Agent {agent_type} timed out after {REPLY_TIMEOUT}s")


async def notify_compliance(case_id: str, reason: str, details: dict):
    """Send to compliance officer notification queue."""
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps({"case_id": case_id, "reason": reason, "details": details}).encode(),
                content_type="application/json",
            ),
            routing_key="kyc.compliance.alert",
        )


async def notify_client_reupload(case_id: str, issues: list):
    """Trigger client re-upload notification."""
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps({"case_id": case_id, "issues": issues}).encode(),
                content_type="application/json",
            ),
            routing_key="kyc.client.reupload",
        )
