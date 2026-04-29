import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from orchestrator.case_state import CaseState, CaseStatus
from orchestrator.orchestrator import KYCOrchestrator
from tests.stubs.agent_stubs import Stubs


async def _noop(*args, **kwargs):
    pass


class FakeStateStore:
    """In-memory stand-in for RedisStateStore."""

    def __init__(self):
        self._store: dict[str, CaseState] = {}

    async def get(self, case_id: str) -> CaseState:
        if case_id not in self._store:
            raise KeyError(f"Case not found: {case_id}")
        return self._store[case_id]

    async def save(self, state: CaseState):
        self._store[state.case_id] = state

    async def create(self, case_id: str, client_ref: str, doc_refs: list) -> CaseState:
        state = CaseState(case_id=case_id, client_ref=client_ref, doc_refs=doc_refs)
        await self.save(state)
        return state

    async def exists(self, case_id: str) -> bool:
        return case_id in self._store

    def seed(self, state: CaseState):
        self._store[state.case_id] = state


class FakeAuditLog:
    """In-memory stand-in for AuditLog."""

    def __init__(self):
        self.events: list[dict] = []

    def log(self, case_id, event_type, payload, **kwargs):
        self.events.append({"case_id": case_id, "event_type": event_type,
                            "payload": payload, **kwargs})

    def get_case_trail(self, case_id: str) -> list[dict]:
        return [e for e in self.events if e["case_id"] == case_id]


@pytest.fixture
def stubs():
    return Stubs()


@pytest.fixture
def state_store():
    return FakeStateStore()


@pytest.fixture
def audit():
    return FakeAuditLog()


@pytest.fixture
def orchestrator(state_store, audit, stubs):
    orch = KYCOrchestrator(state_store, audit)
    # Patch _call_agent to use stubs instead of RabbitMQ
    async def fake_call_agent(agent_type, state):
        return await stubs.dispatch(agent_type, state)
    orch._call_agent = fake_call_agent
    # Patch queue functions that bypass _call_agent and connect to RabbitMQ directly
    orch._escalate = _patched_escalate(orch)
    orch._send_to_manual_review = _patched_manual_review(orch)
    orch._handle_doc_failure = _patched_doc_failure(orch)
    return orch


def _patched_escalate(orch):
    async def _escalate(state, reason, details):
        from orchestrator.case_state import CaseStatus
        state.set_flag("escalated")
        orch.audit.log(state.case_id, "escalation", {"reason": reason})
        await orch.state_store.save(state)
        return {"decision": "escalate", "reason": reason, "case_id": state.case_id}
    return _escalate


def _patched_manual_review(orch):
    async def _send_to_manual_review(state, reason):
        from orchestrator.case_state import CaseStatus
        state.status = CaseStatus.MANUAL_REVIEW
        orch.audit.log(state.case_id, "manual_review_queued", {"reason": reason})
        await orch.state_store.save(state)
        return {"decision": "manual_review", "reason": reason}
    return _send_to_manual_review


def _patched_doc_failure(orch):
    async def _handle_doc_failure(state, result):
        from orchestrator.case_state import CaseStatus
        attempts = state.increment_retry("document_reupload")
        if attempts >= 3:
            return await orch._send_to_manual_review(state, "max_reupload_attempts")
        state.status = CaseStatus.AWAITING_REUPLOAD
        orch.audit.log(state.case_id, "reupload_requested",
                       {"attempt": attempts, "issues": result.get("issues", [])})
        await orch.state_store.save(state)
        return {"status": "awaiting_reupload", "attempt": attempts}
    return _handle_doc_failure


@pytest_asyncio.fixture
async def seeded_case(state_store):
    """Pre-created case in the fake store, ready for orchestrator.run_case()."""
    state = CaseState(
        case_id="case_test_001",
        client_ref="client_gbr_001",
        doc_refs=["s3/passport_gbr.jpg", "s3/proof_of_address.pdf"],
    )
    await state_store.save(state)
    return state
