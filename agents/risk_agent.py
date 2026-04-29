import json
from agents.base_agent import BaseKYCAgent, AgentResult

# FATF high-risk and monitored jurisdictions (update quarterly)
FATF_HIGH_RISK = {"IRN", "PRK", "MMR"}
FATF_GREY_LIST = {"SYR", "YEM", "TZA", "VUT", "LBY", "MLI"}

RISK_OUTPUT_SCHEMA = {
    "risk_level":  "Low | Medium | High",
    "score":       "integer 0–100",
    "factors":     ["list of contributing risk factors"],
    "rationale":   "string — clear explanation for compliance record",
    "confidence":  "float 0.0–1.0"
}


def _base_score(nationality: str, entity_type: str,
                pep_status: bool, adverse_media: list) -> int:
    score = 0
    if nationality in FATF_HIGH_RISK:  score += 50
    elif nationality in FATF_GREY_LIST: score += 25
    if entity_type in ("company", "trust", "foundation"): score += 15
    if pep_status:      score += 30
    if adverse_media:   score += 20
    return min(score, 100)


class RiskAgent(BaseKYCAgent):
    agent_type  = "risk"
    model       = "claude-sonnet-4-6"
    prompt_file = "risk_v1.txt"

    async def _execute(self, case_id: str, payload: dict) -> AgentResult:
        identity_result  = payload.get("agent_results", {}).get("identity", {})
        sanctions_result = payload.get("agent_results", {}).get("sanctions", {})

        nationality  = identity_result.get("result", {}).get("extracted", {}).get("nationality", "")
        entity_type  = payload.get("entity_type", "individual")
        pep_status   = sanctions_result.get("result", {}).get("pep_status", False)
        adverse_media = sanctions_result.get("result", {}).get("adverse_media", [])

        # Rule-based base score first
        base_score = _base_score(nationality, entity_type, pep_status, adverse_media)

        # Claude handles edge cases and generates rationale
        context = {
            "base_score":     base_score,
            "nationality":    nationality,
            "entity_type":    entity_type,
            "pep_status":     pep_status,
            "adverse_media":  adverse_media,
            "identity_flags": payload.get("flags", {}),
        }

        assessed = self.call_claude(
            f"Risk assessment context:\n{json.dumps(context, indent=2)}",
            RISK_OUTPUT_SCHEMA,
        )

        # Safety: if risk scoring fails, default to High — never Low
        if assessed.get("risk_level") not in ("Low", "Medium", "High"):
            assessed["risk_level"] = "High"
            assessed["score"]      = 100
            assessed["rationale"]  = "Risk assessment inconclusive — defaulting to High (conservative)."

        return AgentResult(
            case_id=case_id, agent_type="risk",
            status="completed",
            confidence=assessed.get("confidence", 0.5),
            result=assessed,
            rationale=assessed.get("rationale", ""),
        )
