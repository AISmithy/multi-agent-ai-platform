from agents.base_agent import AgentResult


def stub_document_pass(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="document",
                       status="passed", confidence=1.0,
                       result={"issues": [], "docs_found": ["passport_or_id", "proof_of_address"]},
                       rationale="All documents valid.")

def stub_document_fail(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="document",
                       status="needs_input", confidence=0.0,
                       result={"issues": ["Missing required documents: proof_of_address"],
                               "docs_found": ["passport_or_id"]},
                       rationale="1 issue(s) found.")

def stub_identity_verified(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="identity",
                       status="completed", confidence=0.98,
                       result={"verified": True, "confidence": 0.98, "discrepancies": [],
                               "extracted": {"name": "John Smith", "dob": "1985-06-15",
                                             "nationality": "GBR", "doc_number": "****1234",
                                             "expiry": "2030-01-01"},
                               "rationale": "All fields match."},
                       rationale="All fields match.")

def stub_identity_mismatch(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="identity",
                       status="completed", confidence=0.75,
                       result={"verified": False, "confidence": 0.75,
                               "discrepancies": ["Name mismatch: Jon vs John"],
                               "extracted": {"name": "Jon Smith", "dob": "1985-06-15",
                                             "nationality": "GBR", "doc_number": "****1234",
                                             "expiry": "2030-01-01"},
                               "rationale": "Name discrepancy detected."},
                       rationale="Name discrepancy detected.")

def stub_sanctions_clear(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="sanctions",
                       status="completed", confidence=0.98,
                       result={"hits": [], "match_score": 0.0, "pep_status": False,
                               "adverse_media": []},
                       rationale="No matches found.")

def stub_sanctions_hit(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="sanctions",
                       status="completed", confidence=0.95,
                       result={"hits": ["John A. Smith"], "match_score": 0.92,
                               "pep_status": False, "adverse_media": []},
                       rationale="High-confidence match on OFAC SDN list.")

def stub_risk_low(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="risk",
                       status="completed", confidence=0.95,
                       result={"risk_level": "Low", "score": 12, "factors": []},
                       rationale="Low-risk jurisdiction, no adverse factors.")

def stub_risk_high(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="risk",
                       status="completed", confidence=0.95,
                       result={"risk_level": "High", "score": 85,
                               "factors": ["PEP status"]},
                       rationale="High risk — PEP detected.")

def stub_risk_failure(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="risk",
                       status="failed", confidence=0.0,
                       result={"risk_level": "High", "score": 100,
                               "factors": ["agent_failure"]},
                       rationale="Risk assessment inconclusive — defaulting to High (conservative).")

def stub_decision_approve(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="decision",
                       status="completed", confidence=0.97,
                       result={"decision": "approve", "risk_level": "Low",
                               "memo": "All checks passed.", "next_steps": []},
                       rationale="Approved.")

def stub_decision_escalate(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="decision",
                       status="completed", confidence=1.0,
                       result={"decision": "escalate", "risk_level": "High",
                               "memo": "Hard rule applied: escalate.",
                               "next_steps": ["Assign to compliance officer"]},
                       rationale="Hard rule triggered: escalate.")

def stub_notification(case_id, payload):
    return AgentResult(case_id=case_id, agent_type="notification",
                       status="completed", confidence=1.0,
                       result={"actions": ["email_sent", "crm_updated"],
                               "decision_communicated": "approve"},
                       rationale="Client notified.")


_STUB_MAP = {
    ("document",     "pass"):     stub_document_pass,
    ("document",     "fail"):     stub_document_fail,
    ("identity",     "verified"): stub_identity_verified,
    ("identity",     "mismatch"): stub_identity_mismatch,
    ("sanctions",    "clear"):    stub_sanctions_clear,
    ("sanctions",    "hit"):      stub_sanctions_hit,
    ("risk",         "low"):      stub_risk_low,
    ("risk",         "high"):     stub_risk_high,
    ("risk",         "failure"):  stub_risk_failure,
    ("decision",     "approve"):  stub_decision_approve,
    ("decision",     "escalate"): stub_decision_escalate,
    ("notification", "notify"):   stub_notification,
}


class Stubs:
    """Registry that maps string keys to stub functions and patches dispatch_agent."""

    def __init__(self):
        self._config: dict[str, str] = {}

    def use(self, document=None, identity=None, sanctions=None,
            risk=None, decision=None, notification="notify"):
        if document:     self._config["document"]     = document
        if identity:     self._config["identity"]     = identity
        if sanctions:    self._config["sanctions"]    = sanctions
        if risk:         self._config["risk"]         = risk
        if decision:     self._config["decision"]     = decision
        if notification: self._config["notification"] = notification

    async def dispatch(self, agent_type: str, state) -> dict:
        key = self._config.get(agent_type)
        if key is None:
            # Default per agent type if not configured
            defaults = {"notification": "notify"}
            key = defaults.get(agent_type)
        fn = _STUB_MAP.get((agent_type, key))
        if fn is None:
            raise ValueError(
                f"No stub registered for ({agent_type!r}, {key!r}). "
                f"Call stubs.use({agent_type}=...) before running."
            )
        result = fn(state.case_id, state.to_dict())
        return result.model_dump()
