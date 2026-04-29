import time, os
import redis
from enum import Enum

redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

FAILURE_THRESHOLD    = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5))
RECOVERY_TIMEOUT     = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", 30))
WINDOW_SECONDS       = 60


class CircuitState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:

    def _key(self, service: str) -> str:
        return f"circuit:{service}"

    def get_state(self, service: str) -> CircuitState:
        data = redis_client.hgetall(self._key(service))
        if not data:
            return CircuitState.CLOSED

        failures     = int(data.get(b"failures", 0))
        last_failure = float(data.get(b"last_failure", 0))
        state        = data.get(b"state", b"closed").decode()

        if state == "open":
            if time.time() - last_failure > RECOVERY_TIMEOUT:
                return CircuitState.HALF_OPEN
            return CircuitState.OPEN

        return CircuitState.CLOSED

    def is_open(self, service: str) -> bool:
        return self.get_state(service) == CircuitState.OPEN

    def record_failure(self, service: str):
        key = self._key(service)
        pipe = redis_client.pipeline()
        pipe.hincrby(key, "failures", 1)
        pipe.hset(key, "last_failure", time.time())
        pipe.expire(key, WINDOW_SECONDS * 2)
        pipe.execute()

        failures = int(redis_client.hget(key, "failures") or 0)
        if failures >= FAILURE_THRESHOLD:
            redis_client.hset(key, "state", "open")

    def record_success(self, service: str):
        redis_client.hset(self._key(service), mapping={
            "failures": 0, "state": "closed"
        })


circuit_breaker = CircuitBreaker()
