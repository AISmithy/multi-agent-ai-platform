import json
from agents.base_agent import BaseKYCAgent, AgentResult
from tools.sanctions_client import SanctionsAPIClient
from memory.document_store import DocumentStore

SANCTIONS_OUTPUT_SCHEMA = {
    "hits":          ["list of matched entity names — empty if none"],
    "match_score":   "float 0.0–1.0 — highest match confidence across all hits",
    "pep_status":    "boolean — true if politically exposed person",
    "adverse_media": ["list of adverse media source names found"],
    "confidence":    "float 0.0–1.0 — confidence in your assessment",
    "rationale":     "string — clear explanation for compliance officer"
}


class SanctionsAgent(BaseKYCAgent):
    agent_type = "sanctions"
    model      = "claude-haiku-4-5-20251001"

    def __init__(self, sanctions_client: SanctionsAPIClient,
                 doc_store: DocumentStore):
        self.sanctions = sanctions_client
        self.doc_store = doc_store

    async def _execute(self, case_id: str, payload: dict) -> AgentResult:
        client_ref = payload.get("client_ref")

        # Fetch only the fields the sanctions API needs — not full PII
        screening_data = await self.doc_store.get_screening_data(client_ref)
        # Returns: {verified_name, verified_dob, nationality, aliases}

        # Third-party API does the actual screening
        api_response = self.sanctions.screen_safe(
            name=screening_data["verified_name"],
            dob=screening_data["verified_dob"],
            nationality=screening_data["nationality"],
            aliases=screening_data.get("aliases", []),
        )

        # Claude articulates the result — does NOT do the screening itself
        user_message = (
            f"Sanctions API response for case {case_id}:\n"
            f"{json.dumps(api_response)}\n\n"
            "Assess the match quality and write a rationale for the compliance officer."
        )

        assessed = self.call_claude(user_message, SANCTIONS_OUTPUT_SCHEMA)

        return AgentResult(
            case_id=case_id, agent_type="sanctions",
            status="completed",
            confidence=assessed.get("confidence", 0.0),
            result=assessed,
            rationale=assessed.get("rationale", ""),
        )
