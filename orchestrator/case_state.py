from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import os


class CaseStatus(str, Enum):
    INTAKE             = "intake"
    DOCUMENT_CHECK     = "document_check"
    AWAITING_REUPLOAD  = "awaiting_reupload"
    IDENTITY_CHECK     = "identity_check"
    SANCTIONS_CHECK    = "sanctions_check"
    RISK_SCORING       = "risk_scoring"
    DECISION           = "decision"
    APPROVED           = "approved"
    EDD_QUEUE          = "edd_queue"
    ESCALATED          = "escalated"
    MANUAL_REVIEW      = "manual_review"
    NOTIFIED           = "notified"


@dataclass
class CaseState:
    case_id:        str
    client_ref:     str
    status:         CaseStatus = CaseStatus.INTAKE
    doc_refs:       list       = field(default_factory=list)   # S3 keys
    agent_results:  dict       = field(default_factory=dict)
    retry_counts:   dict       = field(default_factory=dict)
    flags:          dict       = field(default_factory=dict)
    risk_level:     Optional[str] = None   # Low | Medium | High
    risk_score:     Optional[int] = None   # 0–100
    created_at:     datetime   = field(default_factory=datetime.utcnow)
    sla_deadline:   Optional[datetime] = None

    def __post_init__(self):
        if self.sla_deadline is None:
            sla_seconds = int(os.getenv("CASE_SLA_LOW_RISK", 300))
            self.sla_deadline = self.created_at + timedelta(seconds=sla_seconds)

    def increment_retry(self, agent: str) -> int:
        self.retry_counts[agent] = self.retry_counts.get(agent, 0) + 1
        return self.retry_counts[agent]

    def set_flag(self, flag: str, value: bool = True):
        self.flags[flag] = value

    def store_result(self, agent: str, result: dict):
        self.agent_results[agent] = result

    def is_sla_breached(self) -> bool:
        return datetime.utcnow() > self.sla_deadline

    def to_dict(self) -> dict:
        return {
            "case_id":       self.case_id,
            "client_ref":    self.client_ref,
            "status":        self.status.value,
            "doc_refs":      self.doc_refs,
            "agent_results": self.agent_results,
            "retry_counts":  self.retry_counts,
            "flags":         self.flags,
            "risk_level":    self.risk_level,
            "risk_score":    self.risk_score,
            "created_at":    self.created_at.isoformat(),
            "sla_deadline":  self.sla_deadline.isoformat() if self.sla_deadline else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CaseState":
        d = d.copy()
        d["status"]      = CaseStatus(d["status"])
        d["created_at"]  = datetime.fromisoformat(d["created_at"])
        if d.get("sla_deadline"):
            d["sla_deadline"] = datetime.fromisoformat(d["sla_deadline"])
        return cls(**d)
