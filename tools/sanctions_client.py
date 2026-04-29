import httpx, os
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tools.circuit_breaker import circuit_breaker, CircuitOpenError


class SanctionsAPIClient:

    BASE_URL = os.getenv("SANCTIONS_API_URL", "https://api.complyadvantage.com")
    API_KEY  = os.getenv("SANCTIONS_API_KEY", "")
    TIMEOUT  = 10.0   # Hard ceiling in seconds

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=32),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    def _screen(self, name: str, dob: str, nationality: str, aliases: list) -> dict:
        with httpx.Client(timeout=self.TIMEOUT) as http:
            resp = http.post(
                f"{self.BASE_URL}/searches",
                json={
                    "search_term": name,
                    "filters": {
                        "birth_year":   dob[:4] if dob else None,
                        "country_codes": [nationality],
                        "types":        ["sanction", "pep", "adverse-media"],
                    },
                    "share_url": False,
                },
                headers={"Authorization": f"Token {self.API_KEY}"},
            )
            resp.raise_for_status()
            return resp.json()

    def screen_safe(self, name: str, dob: str,
                    nationality: str, aliases: list = None) -> dict:
        if circuit_breaker.is_open("sanctions_api"):
            raise CircuitOpenError("Sanctions API circuit is open — routing to manual review")
        try:
            result = self._screen(name, dob, nationality, aliases or [])
            circuit_breaker.record_success("sanctions_api")
            return result
        except Exception as exc:
            circuit_breaker.record_failure("sanctions_api")
            raise
