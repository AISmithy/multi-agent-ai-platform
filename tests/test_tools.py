import pytest
from unittest.mock import patch, MagicMock
from tools.circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError


def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker()
    with patch("tools.circuit_breaker.redis_client") as mock_redis:
        mock_redis.hgetall.return_value = {}
        assert cb.get_state("test_service") == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker()
    with patch("tools.circuit_breaker.redis_client") as mock_redis:
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe
        mock_pipe.execute.return_value = None
        mock_redis.hget.return_value = b"5"
        cb.record_failure("test_service")
        mock_redis.hset.assert_called_with("circuit:test_service", "state", "open")


def test_circuit_breaker_is_open():
    import time
    cb = CircuitBreaker()
    with patch("tools.circuit_breaker.redis_client") as mock_redis:
        mock_redis.hgetall.return_value = {
            b"failures": b"5",
            b"last_failure": str(time.time()).encode(),
            b"state": b"open",
        }
        assert cb.is_open("test_service") is True
