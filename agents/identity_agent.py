import json
from agents.base_agent import BaseKYCAgent, AgentResult
from tools.ocr_client import OCRClient
from tools.liveness_client import LivenessClient
from memory.document_store import DocumentStore

IDENTITY_OUTPUT_SCHEMA = {
    "verified":      "boolean — true if identity confirmed",
    "confidence":    "float 0.0–1.0",
    "discrepancies": ["list of field-level mismatches found"],
    "extracted": {
        "name":       "string from document",
        "dob":        "YYYY-MM-DD from document",
        "nationality":"ISO 3166-1 alpha-3",
        "doc_number": "masked — last 4 chars only, e.g. '****1234'",
        "expiry":     "YYYY-MM-DD"
    },
    "rationale": "string — clear explanation for compliance record"
}


class IdentityAgent(BaseKYCAgent):
    agent_type  = "identity"
    model       = "claude-sonnet-4-6"
    prompt_file = "identity_v1.txt"

    def __init__(self, ocr: OCRClient, liveness: LivenessClient,
                 doc_store: DocumentStore):
        self.ocr      = ocr
        self.liveness = liveness
        self.doc_store = doc_store

    async def _execute(self, case_id: str, payload: dict) -> AgentResult:
        doc_refs   = payload.get("doc_refs", [])
        client_ref = payload.get("client_ref")

        # Run OCR on ID document
        id_doc_ref  = next((r for r in doc_refs if "passport" in r or "id" in r), doc_refs[0])
        ocr_result  = await self.ocr.extract(id_doc_ref)

        # Liveness check (if selfie ref present)
        liveness_ok = True
        selfie_ref  = next((r for r in doc_refs if "selfie" in r), None)
        if selfie_ref:
            liveness_ok = await self.liveness.check(selfie_ref, id_doc_ref)

        # Fetch declared form data (tokenised — client_ref only, no raw PII in prompt)
        declared = await self.doc_store.get_declared_data(client_ref)

        # Claude cross-checks extracted vs declared — no raw passport number in prompt
        safe_ocr = {k: v for k, v in ocr_result.items()
                    if k not in ("passport_number", "national_id_number")}

        user_message = (
            f"OCR extracted from identity document: {json.dumps(safe_ocr)}\n"
            f"Client declared on form: {json.dumps(declared)}\n"
            f"Liveness check passed: {liveness_ok}"
        )

        assessed = self.call_claude(user_message, IDENTITY_OUTPUT_SCHEMA)

        return AgentResult(
            case_id=case_id, agent_type="identity",
            status="completed",
            confidence=assessed.get("confidence", 0.0),
            result=assessed,
            rationale=assessed.get("rationale", ""),
        )
