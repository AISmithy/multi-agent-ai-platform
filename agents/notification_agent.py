import json, os
import httpx
from agents.base_agent import BaseKYCAgent, AgentResult

SENDGRID_KEY = os.getenv("SENDGRID_KEY", "")
CRM_WEBHOOK  = os.getenv("CRM_WEBHOOK_URL", "")

EMAIL_TEMPLATES = {
    "approve":  "Your application has been approved. Welcome aboard.",
    "edd":      "We need a few more details before we can complete your application.",
    "escalate": "Your application is under review. Our team will be in touch within 2 business days.",
}


class NotificationAgent(BaseKYCAgent):
    agent_type = "notification"
    model      = "claude-haiku-4-5-20251001"

    async def _execute(self, case_id: str, payload: dict) -> AgentResult:
        decision_result = payload.get("agent_results", {}).get("decision", {})
        decision = decision_result.get("result", {}).get("decision", "escalate")
        client_ref = payload.get("client_ref")

        actions_taken = []

        # Send email to client
        email_body = EMAIL_TEMPLATES.get(decision, EMAIL_TEMPLATES["escalate"])
        await self._send_email(client_ref, email_body)
        actions_taken.append("email_sent")

        # Update CRM
        await self._update_crm(case_id, client_ref, decision)
        actions_taken.append("crm_updated")

        return AgentResult(
            case_id=case_id, agent_type="notification",
            status="completed", confidence=1.0,
            result={"actions": actions_taken, "decision_communicated": decision},
            rationale=f"Client notified of decision: {decision}",
        )

    async def _send_email(self, client_ref: str, body: str):
        async with httpx.AsyncClient() as http:
            await http.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {SENDGRID_KEY}"},
                json={
                    "personalizations": [{"to": [{"email": f"{client_ref}@example.com"}]}],
                    "from": {"email": "kyc@yourcompany.com"},
                    "subject": "Your application update",
                    "content": [{"type": "text/plain", "value": body}],
                },
                timeout=10.0,
            )

    async def _update_crm(self, case_id: str, client_ref: str, decision: str):
        async with httpx.AsyncClient() as http:
            await http.post(
                CRM_WEBHOOK,
                json={"case_id": case_id, "client_ref": client_ref, "kyc_status": decision},
                timeout=10.0,
            )
