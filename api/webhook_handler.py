import uuid
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from memory.redis_store import RedisStateStore
from memory.audit_log import AuditLog
from orchestrator.orchestrator import KYCOrchestrator

app        = FastAPI(title="KYC Onboarding API")
state_store = RedisStateStore()
audit       = AuditLog()
logger      = logging.getLogger(__name__)


class OnboardingSubmission(BaseModel):
    client_ref:  str
    doc_s3_keys: list[str]   # S3 keys uploaded by the client portal


@app.post("/webhooks/onboarding")
async def receive_submission(
    submission: OnboardingSubmission,
    background_tasks: BackgroundTasks,
):
    case_id = f"case_{uuid.uuid4().hex[:12]}"

    await state_store.create(
        case_id=case_id,
        client_ref=submission.client_ref,
        doc_refs=submission.doc_s3_keys,
    )
    audit.log(case_id, "intake", {"client_ref": submission.client_ref})

    # Run orchestration in the background — return case_id immediately
    background_tasks.add_task(run_orchestration, case_id)

    return {"case_id": case_id, "status": "processing"}


@app.get("/cases/{case_id}/status")
async def get_case_status(case_id: str):
    try:
        state = await state_store.get(case_id)
        return {"case_id": case_id, "status": state.status.value,
                "risk_level": state.risk_level}
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found")


@app.get("/cases/{case_id}/audit")
async def get_audit_trail(case_id: str):
    trail = audit.get_case_trail(case_id)
    return {"case_id": case_id, "events": trail}


async def run_orchestration(case_id: str):
    orchestrator = KYCOrchestrator(state_store, audit)
    try:
        await orchestrator.run_case(case_id)
    except Exception:
        logger.exception("Orchestration failed for case %s", case_id)
