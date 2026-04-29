import json, os
import redis.asyncio as aioredis
from orchestrator.case_state import CaseState, CaseStatus

REDIS_URL   = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TTL_SECONDS = int(os.getenv("CASE_TTL_REDIS", 2_592_000))  # 30 days
KEY_PREFIX  = "kyc:case:"


class RedisStateStore:

    def __init__(self):
        self.r = aioredis.from_url(REDIS_URL, decode_responses=True)

    def _key(self, case_id: str) -> str:
        return KEY_PREFIX + case_id

    async def get(self, case_id: str) -> CaseState:
        raw = await self.r.get(self._key(case_id))
        if not raw:
            raise KeyError(f"Case not found: {case_id}")
        return CaseState.from_dict(json.loads(raw))

    async def save(self, state: CaseState):
        await self.r.setex(
            self._key(state.case_id),
            TTL_SECONDS,
            json.dumps(state.to_dict()),
        )

    async def create(self, case_id: str, client_ref: str,
                     doc_refs: list) -> CaseState:
        state = CaseState(case_id=case_id, client_ref=client_ref, doc_refs=doc_refs)
        await self.save(state)
        return state

    async def set_status(self, case_id: str, status: CaseStatus):
        state = await self.get(case_id)
        state.status = status
        await self.save(state)

    async def exists(self, case_id: str) -> bool:
        return bool(await self.r.exists(self._key(case_id)))
