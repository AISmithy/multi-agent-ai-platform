import pytest
from agents.base_agent import AgentResult
from orchestrator.case_state import CaseState
from agents.risk_agent import _base_score
from agents.decision_agent import _apply_hard_rules


def test_base_score_fatf_high_risk():
    score = _base_score("IRN", "individual", False, [])
    assert score == 50


def test_base_score_pep():
    score = _base_score("GBR", "individual", True, [])
    assert score == 30


def test_base_score_caps_at_100():
    score = _base_score("IRN", "individual", True, ["Reuters"])
    assert score == 100


def test_hard_rules_sanctions_hit():
    decision = _apply_hard_rules("Low", ["John Smith"], True)
    assert decision == "escalate"


def test_hard_rules_unverified_identity():
    decision = _apply_hard_rules("Low", [], False)
    assert decision == "escalate"


def test_hard_rules_high_risk():
    decision = _apply_hard_rules("High", [], True)
    assert decision == "escalate"


def test_hard_rules_low_risk_clear():
    decision = _apply_hard_rules("Low", [], True)
    assert decision is None


def test_agent_result_model():
    result = AgentResult(
        case_id="case_001",
        agent_type="document",
        status="passed",
        confidence=1.0,
        result={"issues": []},
        rationale="All good.",
    )
    assert result.status == "passed"
    assert result.latency_ms == 0
    d = result.model_dump()
    assert d["case_id"] == "case_001"
