import httpx, os

ONFIDO_KEY     = os.getenv("ONFIDO_API_KEY", "")
ONFIDO_API_URL = "https://api.eu.onfido.com/v3.6"


class LivenessClient:

    async def check(self, selfie_s3_key: str, id_doc_s3_key: str) -> bool:
        """
        Calls Onfido to verify the selfie matches the identity document
        and that the selfie is of a live person.
        Returns True if liveness confirmed and faces match.
        """
        # In production: upload documents to Onfido, run check, poll result
        # Stub implementation — replace with full Onfido SDK flow
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(
                f"{ONFIDO_API_URL}/checks",
                headers={
                    "Authorization": f"Token token={ONFIDO_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "report_names": ["document", "facial_similarity_photo"],
                },
            )
            if resp.status_code == 201:
                result = resp.json()
                return result.get("status") == "complete" and result.get("result") == "clear"
        return False
