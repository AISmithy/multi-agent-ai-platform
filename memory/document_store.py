import boto3, os
from botocore.exceptions import ClientError

S3_BUCKET  = os.getenv("S3_BUCKET", "kyc-documents")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")


class DocumentStore:

    def __init__(self):
        self.s3 = boto3.client("s3", region_name=AWS_REGION)
        # In-memory token map (use Redis or a secrets store in production)
        self._token_map: dict[str, str] = {}

    def tokenise(self, field: str, value: str) -> str:
        """Returns a token that refers to the value without exposing it."""
        import hashlib
        token = "tok_" + hashlib.sha256(f"{field}:{value}".encode()).hexdigest()[:16]
        self._token_map[token] = value
        return token

    def detokenise(self, token: str) -> str:
        return self._token_map.get(token, "")

    async def get_metadata(self, s3_key: str) -> dict:
        try:
            response = self.s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
            return {
                "size":         response.get("ContentLength", 0),
                "content_type": response.get("ContentType", ""),
                "doc_type":     response.get("Metadata", {}).get("doc_type", "unknown"),
                "expiry_date":  response.get("Metadata", {}).get("expiry_date"),
            }
        except ClientError:
            return {}

    async def get_declared_data(self, client_ref: str) -> dict:
        """Fetch tokenised declared form data for a client."""
        # In production: fetch from your client database by client_ref
        # Return only non-sensitive structural data for Claude cross-check
        return {
            "declared_nationality": "GBR",
            "declared_dob_year":    "1985",   # Year only — not full DOB
            "declared_name_tokens": ["John", "Smith"],  # Split, not full name
        }

    async def get_screening_data(self, client_ref: str) -> dict:
        """Fetch the minimal data needed for sanctions API screening."""
        # Fetches from secure client DB — never from the message payload
        return {
            "verified_name": "John Smith",
            "verified_dob":  "1985-06-15",
            "nationality":   "GBR",
            "aliases":       [],
        }
