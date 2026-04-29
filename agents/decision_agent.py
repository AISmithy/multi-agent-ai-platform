import json
from agents.base_agent import BaseKYCAgent, AgentResult

DECISION_OUTPUT_SCHEMA = {
    "decision":    "approve | edd | escalate",
    "risk_level":  "Low | Medium | High",
    "memo":        "string — compliance-ready decision memo, 2–4 sentences",
    "next_steps":  ["list of required follow-up actions"],
    "confidence":  "float 0.0–1.0"
}

# Hard decision rules — applied BEFORE Claude
def _apply_hard_rules(risk_level: str, sanctions_hits: list,
                      identity_verified: bool) -> str | None:
    """Return forced decision or None to let Claude decide."""
    if sanctions_hits:
        return "escalate"      # Always escalate on any sanctions hit
    if not identity_verified:
        return "escalate"      # Never approve unverified identity
    if risk_level == "High":
        return "escalate"      # High risk always to human
    return None                # Let Claude handle Low and Medium


class DecisionAgent(BaseKYCAgent):
    agent_type  = "decision"
    model       = "claude-sonnet-4-6"
    prompt_file = "decision_v1.txt"

    async def _execute(self, case_id: str, payload: dict) -> AgentResult:
        results   = payload.get("agent_results", {})
        flags     = payload.get("flags", {})
        risk_level = results.get("risk", {}).get("result", {}).get("risk_level", "High")

        sanctions_hits    = results.get("sanctions", {}).get("result", {}).get("hits", [])
        identity_verified = results.get("identity", {}).get("result", {}).get("verified", False)

        # Apply hard rules first — Claude cannot override these
        forced = _apply_hard_rules(risk_level, sanctions_hits, identity_verified)

        if forced:
            return AgentResult(
                case_id=case_id, agent_type="decision",
                status="completed", confidence=1.0,
                result={"decision": forced, "risk_level": risk_level,
                        "memo": f"Hard rule applied: {forced}.",
                        "next_steps": ["Assign to compliance officer"]},
                rationale=f"Hard rule triggered: {forced}",
            )

        # Claude decides for Low / Medium (EDD vs approve)
        context = {
            "risk_level":        risk_level,
            "risk_score":        results.get("risk", {}).get("result", {}).get("score"),
            "risk_factors":      results.get("risk", {}).get("result", {}).get("factors", []),
            "pep_status":        results.get("sanctions", {}).get("result", {}).get("pep_status"),
            "identity_confidence": results.get("identity", {}).get("confidence"),
            "identity_mismatch": flags.get("identity_mismatch", False),
        }

        assessed = self.call_claude(
            f"Case decision context:\n{json.dumps(context, indent=2)}",
            DECISION_OUTPUT_SCHEMA,
            max_tokens=512,
        )

        # Validate output — if invalid, escalate conservatively
        if assessed.get("decision") not in ("approve", "edd", "escalate"):
            assessed["decision"] = "escalate"
            assessed["memo"]     = "Decision output invalid — escalating conservatively."

        return AgentResult(
            case_id=case_id, agent_type="decision",
            status="completed",
            confidence=assessed.get("confidence", 0.5),
            result=assessed,
            rationale=assessed.get("memo", ""),
        )
