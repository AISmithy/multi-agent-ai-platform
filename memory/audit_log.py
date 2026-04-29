import hashlib, json, os, logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")
logger       = logging.getLogger(__name__)

# Fields that must never appear in the audit log
PII_FIELDS = {"name", "dob", "passport_number", "national_id_number",
              "address", "phone", "email", "full_name", "date_of_birth"}

INSERT_SQL = """
    INSERT INTO kyc_audit_log
      (case_id, event_type, agent_id, input_hash,
       result_summary, prompt_version, risk_level, latency_ms, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class AuditLog:

    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.autocommit = True

    def log(self, case_id: str, event_type: str, payload: dict,
            agent_id: str = None, prompt_version: str = None,
            risk_level: str = None, latency_ms: int = None):
        try:
            input_hash = self._hash(payload)
            summary    = self._sanitise(payload)

            with self.conn.cursor() as cur:
                cur.execute(INSERT_SQL, (
                    case_id, event_type, agent_id,
                    input_hash, json.dumps(summary),
                    prompt_version, risk_level,
                    latency_ms, datetime.utcnow(),
                ))
        except Exception:
            # Audit failures must never crash the pipeline — log and continue
            logger.exception("Audit log write failed for case %s event %s",
                             case_id, event_type)

    def get_case_trail(self, case_id: str) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM kyc_audit_log WHERE case_id = %s ORDER BY created_at",
                (case_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    def _hash(self, payload: dict) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _sanitise(self, payload: dict) -> dict:
        """Deep-strip PII keys before storing."""
        if not isinstance(payload, dict):
            return {}
        return {
            k: self._sanitise(v) if isinstance(v, dict) else v
            for k, v in payload.items()
            if k.lower() not in PII_FIELDS
        }
