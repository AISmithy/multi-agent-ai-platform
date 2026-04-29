import pytest
from orchestrator.case_state import CaseState, CaseStatus


async def _seed(state_store, case_id: str, **kwargs):
    state = CaseState(
        case_id=case_id,
        client_ref=kwargs.get("client_ref", "client_test"),
        doc_refs=kwargs.get("doc_refs", ["s3/passport.jpg", "s3/proof.pdf"]),
    )
    await state_store.save(state)
    return state


@pytest.mark.asyncio
async def test_happy_path_approve(orchestrator, stubs, state_store):
    stubs.use(document="pass", identity="verified", sanctions="clear",
              risk="low", decision="approve")
    await _seed(state_store, "case_hp_001")
    result = await orchestrator.run_case("case_hp_001")
    assert result.get("decision") == "approve"


@pytest.mark.asyncio
async def test_document_failure_returns_awaiting_reupload(orchestrator, stubs, state_store):
    stubs.use(document="fail")
    await _seed(state_store, "case_doc_fail_001")
    result = await orchestrator.run_case("case_doc_fail_001")
    assert result.get("status") == "awaiting_reupload"
    assert result.get("attempt") == 1


@pytest.mark.asyncio
async def test_sanctions_hit_escalates(orchestrator, stubs, state_store):
    stubs.use(document="pass", identity="verified", sanctions="hit")
    await _seed(state_store, "case_sanc_001")
    result = await orchestrator.run_case("case_sanc_001")
    assert result.get("decision") == "escalate"
    assert result.get("reason") == "sanctions_hit"


@pytest.mark.asyncio
async def test_high_risk_never_auto_approved(orchestrator, stubs, state_store):
    stubs.use(document="pass", identity="verified", sanctions="clear",
              risk="high", decision="escalate")
    await _seed(state_store, "case_hr_001")
    result = await orchestrator.run_case("case_hr_001")
    assert result.get("decision") == "escalate"
