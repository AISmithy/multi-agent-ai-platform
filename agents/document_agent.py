from agents.base_agent import BaseKYCAgent, AgentResult
from memory.document_store import DocumentStore
from datetime import date

REQUIRED_DOCS = {"passport_or_id", "proof_of_address"}
MIN_FILE_SIZE  = 10_000   # bytes — reject tiny/corrupt files
MAX_FILE_SIZE  = 15_000_000  # 15MB


class DocumentAgent(BaseKYCAgent):
    agent_type = "document"
    model      = "claude-haiku-4-5-20251001"

    def __init__(self, doc_store: DocumentStore):
        self.doc_store = doc_store

    async def _execute(self, case_id: str, payload: dict) -> AgentResult:
        doc_refs  = payload.get("doc_refs", [])
        issues    = []
        doc_types_found = set()

        for ref in doc_refs:
            meta = await self.doc_store.get_metadata(ref)

            # File size check
            size = meta.get("size", 0)
            if size < MIN_FILE_SIZE:
                issues.append(f"{ref}: file too small or corrupt ({size} bytes)")
                continue
            if size > MAX_FILE_SIZE:
                issues.append(f"{ref}: file exceeds 15MB limit")
                continue

            # Format check
            content_type = meta.get("content_type", "")
            if content_type not in ("image/jpeg", "image/png", "application/pdf"):
                issues.append(f"{ref}: unsupported format ({content_type})")
                continue

            # Expiry check (for passports — basic year from filename metadata)
            if expiry := meta.get("expiry_date"):
                if expiry < date.today().isoformat():
                    issues.append(f"{ref}: document expired on {expiry}")
                    continue

            doc_type = meta.get("doc_type", "unknown")
            doc_types_found.add(doc_type)

        # Completeness check
        missing = REQUIRED_DOCS - doc_types_found
        if missing:
            issues.append(f"Missing required documents: {', '.join(missing)}")

        passed = len(issues) == 0
        return AgentResult(
            case_id=case_id, agent_type="document",
            status="passed" if passed else "needs_input",
            confidence=1.0 if passed else 0.0,
            result={"issues": issues, "docs_found": list(doc_types_found)},
            rationale=("All documents valid." if passed
                       else f"{len(issues)} issue(s) found: " + "; ".join(issues)),
        )
