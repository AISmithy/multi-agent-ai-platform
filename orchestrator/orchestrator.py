import asyncio
import logging
from memory.redis_store import RedisStateStore
from memory.audit_log import AuditLog
from orchestrator.case_state import CaseState, CaseStatus
from orchestrator.queue_dispatch import dispatch_agent, notify_compliance, notify_client_reupload

logger = logging.getLogger(__name__)

MAX_DOC_REUPLOAD_ATTEMPTS = 3
SANCTIONS_HIT_THRESHOLD   = 0.85


class KYCOrchestrator:

    def __init__(self, state_store: RedisStateStore, audit: AuditLog):
        self.state_store = state_store
        self.audit = audit

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #

    async def run_case(self, case_id: str) -> dict:
        state = await self.state_store.get(case_id)
        self.audit.log(case_id, "orchestrator_start", {})
        logger.info("Starting case %s", case_id)

        try:
            return await self._run_pipeline(state)
        except Exception as exc:
            logger.exception("Unhandled error in case %s", case_id)
            return await self._send_to_manual_review(state, str(exc))

    # ------------------------------------------------------------------ #
    # Pipeline                                                             #
    # ------------------------------------------------------------------ #

    async def _run_pipeline(self, state: CaseState) -> dict:

        # Step 1 — Document validation
        await self._set_status(state, CaseStatus.DOCUMENT_CHECK)
        doc_result = await self._call_agent("document", state)

        if doc_result["status"] != "passed":
            return await self._handle_doc_failure(state, doc_result)

        state.store_result("document", doc_result)

        # Step 2 — Identity + Sanctions in parallel
        await self._set_status(state, CaseStatus.IDENTITY_CHECK)
        identity_result, sanctions_result = await asyncio.gather(
            self._call_agent("identity",  state),
            self._call_agent("sanctions", state),
        )

        state.store_result("identity",  identity_result)
        state.store_result("sanctions", sanctions_result)

        # Sanctions hit — lock case immediately
        sanctions_inner = sanctions_result.get("result", {})
        if (sanctions_inner.get("hits")
                and sanctions_inner.get("match_score", 0) >= SANCTIONS_HIT_THRESHOLD):
            return await self._escalate(state, "sanctions_hit", sanctions_result)

        # Identity mismatch — pause, do not reject
        # confidence is a top-level field on AgentResult
        if identity_result.get("confidence", 1.0) < 0.90:
            state.set_flag("identity_mismatch")

        # Step 3 — Risk scoring
        await self._set_status(state, CaseStatus.RISK_SCORING)
        risk_result = await self._call_agent("risk", state)
        state.store_result("risk", risk_result)
        risk_inner = risk_result.get("result", {})
        state.risk_level = risk_inner.get("risk_level", "High")
        state.risk_score = risk_inner.get("score", 100)

        # Step 4 — Decision
        await self._set_status(state, CaseStatus.DECISION)
        decision = await self._call_agent("decision", state)
        state.store_result("decision", decision)

        # Step 5 — Notify and close
        return await self._finalise(state, decision)

    # ------------------------------------------------------------------ #
    # Agent dispatch                                                       #
    # ------------------------------------------------------------------ #

    async def _call_agent(self, agent_type: str, state: CaseState) -> dict:
        self.audit.log(state.case_id, f"agent_called:{agent_type}", {})
        result = await dispatch_agent(agent_type, state)
        self.audit.log(state.case_id, f"agent_result:{agent_type}", result,
                       agent_id=agent_type)
        return result

    # ------------------------------------------------------------------ #
    # Branching handlers                                                   #
    # ------------------------------------------------------------------ #

    async def _handle_doc_failure(self, state: CaseState, result: dict) -> dict:
        attempts = state.increment_retry("document_reupload")
        if attempts >= MAX_DOC_REUPLOAD_ATTEMPTS:
            return await self._send_to_manual_review(state, "max_reupload_attempts")
        await self._set_status(state, CaseStatus.AWAITING_REUPLOAD)
        self.audit.log(state.case_id, "reupload_requested",
                       {"attempt": attempts, "issues": result.get("issues", [])})
        await notify_client_reupload(state.case_id, result.get("issues", []))
        return {"status": "awaiting_reupload", "attempt": attempts}

    async def _escalate(self, state: CaseState, reason: str, details: dict) -> dict:
        await self._set_status(state, CaseStatus.ESCALATED)
        state.set_flag("escalated")
        self.audit.log(state.case_id, "escalation", {"reason": reason})
        await notify_compliance(state.case_id, reason, details)
        logger.warning("Case %s escalated: %s", state.case_id, reason)
        return {"decision": "escalate", "reason": reason, "case_id": state.case_id}

    async def _send_to_manual_review(self, state: CaseState, reason: str) -> dict:
        await self._set_status(state, CaseStatus.MANUAL_REVIEW)
        self.audit.log(state.case_id, "manual_review_queued", {"reason": reason})
        await notify_compliance(state.case_id, reason, state.to_dict())
        return {"decision": "manual_review", "reason": reason}

    async def _finalise(self, state: CaseState, decision: dict) -> dict:
        outcome_map = {
            "approve":  CaseStatus.APPROVED,
            "edd":      CaseStatus.EDD_QUEUE,
            "escalate": CaseStatus.ESCALATED,
        }
        decision_inner = decision.get("result", decision)   # unwrap AgentResult if present
        decision_value = decision_inner.get("decision")
        new_status = outcome_map.get(decision_value, CaseStatus.MANUAL_REVIEW)
        await self._set_status(state, new_status)

        # High risk always requires human, never auto-approve
        if state.risk_level == "High" and new_status == CaseStatus.APPROVED:
            return await self._escalate(state, "high_risk_auto_approve_blocked", decision)

        await self._call_agent("notification", state)
        await self._set_status(state, CaseStatus.NOTIFIED)
        self.audit.log(state.case_id, "case_closed",
                       {"decision": decision_value, "risk": state.risk_level})
        return decision_inner

    async def _set_status(self, state: CaseState, status: CaseStatus):
        state.status = status
        await self.state_store.save(state)
