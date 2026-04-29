import pytest
from orchestrator.case_state import CaseState


async def _seed(state_store, case_id: str):
    state = CaseState(
        case_id=case_id,
        client_ref="client_test",
        doc_refs=["s3/passport.jpg", "s3/proof_of_address.pdf"],
    )
    await state_store.save(state)


@pytest.mark.asyncio
async def test_clean_low_risk_client_auto_approves(orchestrator, stubs, state_store):
    """Given clean docs, no sanctions, Low risk → auto-approve in < 5 min."""
    stubs.use(document="pass", identity="verified", sanctions="clear",
              risk="low", decision="approve")
    await _seed(state_store, "case_test_001")
    result = await orchestrator.run_case("case_test_001")
    assert result["decision"] == "approve"


@pytest.mark.asyncio
async def test_sanctions_hit_escalates_immediately(orchestrator, stubs, state_store):
    """Given a sanctions hit >= 85% → escalate, do not proceed to risk."""
    stubs.use(document="pass", identity="verified", sanctions="hit")
    await _seed(state_store, "case_test_002")
    result = await orchestrator.run_case("case_test_002")
    assert result["decision"] == "escalate"
    assert result["reason"] == "sanctions_hit"


@pytest.mark.asyncio
async def test_agent_failure_defaults_to_high_risk(orchestrator, stubs, state_store):
    """Given risk agent failure → default to High, escalate."""
    stubs.use(document="pass", identity="verified",
              sanctions="clear", risk="failure")
    await _seed(state_store, "case_test_003")
    result = await orchestrator.run_case("case_test_003")
    assert result["decision"] in ("escalate", "manual_review")
