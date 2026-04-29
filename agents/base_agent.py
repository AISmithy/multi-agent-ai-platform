import json
import time
import logging
from abc import ABC, abstractmethod
from pathlib import Path
import anthropic
from pydantic import BaseModel, ValidationError

client = anthropic.Anthropic()
logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class AgentResult(BaseModel):
    case_id:        str
    agent_type:     str
    status:         str         # completed | failed | needs_input
    confidence:     float       # 0.0 – 1.0
    result:         dict
    rationale:      str
    prompt_version: str = "unknown"
    latency_ms:     int = 0


class BaseKYCAgent(ABC):
    model:      str = "claude-haiku-4-5-20251001"
    agent_type: str = "base"
    prompt_file: str = ""       # filename in prompts/

    def get_system_prompt(self) -> str:
        if self.prompt_file:
            path = PROMPTS_DIR / self.prompt_file
            return path.read_text(encoding="utf-8")
        return ""

    def get_prompt_version(self) -> str:
        return self.prompt_file.replace(".txt", "") if self.prompt_file else "inline"

    async def run(self, case_id: str, payload: dict) -> AgentResult:
        start = time.time()
        try:
            result = await self._execute(case_id, payload)
            result.latency_ms     = int((time.time() - start) * 1000)
            result.prompt_version = self.get_prompt_version()
            return result
        except Exception as exc:
            logger.exception("Agent %s failed for case %s", self.agent_type, case_id)
            return AgentResult(
                case_id=case_id, agent_type=self.agent_type,
                status="failed", confidence=0.0,
                result={"error": str(exc)}, rationale=str(exc),
                latency_ms=int((time.time() - start) * 1000),
            )

    def call_claude(self, user_message: str, output_schema: dict,
                    max_tokens: int = 1024) -> dict:
        system = (self.get_system_prompt()
                  + "\n\nRespond ONLY with valid JSON matching this schema. "
                    "No preamble, no markdown fences:\n"
                  + json.dumps(output_schema, indent=2))
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Strip markdown fences if model added them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())

    @abstractmethod
    async def _execute(self, case_id: str, payload: dict) -> AgentResult:
        ...
