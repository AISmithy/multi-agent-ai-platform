import boto3, os
from botocore.exceptions import ClientError

S3_BUCKET  = os.getenv("S3_BUCKET", "kyc-documents")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")


class OCRClient:

    def __init__(self):
        self.textract = boto3.client("textract", region_name=AWS_REGION)

    async def extract(self, s3_key: str) -> dict:
        """Extract structured data from an identity document via AWS Textract."""
        try:
            response = self.textract.analyze_id(
                DocumentPages=[{
                    "S3Object": {"Bucket": S3_BUCKET, "Name": s3_key}
                }]
            )
        except ClientError as exc:
            raise RuntimeError(f"OCR failed for {s3_key}: {exc}") from exc

        fields = {}
        for doc in response.get("IdentityDocuments", []):
            for field in doc.get("IdentityDocumentFields", []):
                key   = field.get("Type", {}).get("Text", "").lower().replace(" ", "_")
                value = field.get("ValueDetection", {}).get("Text", "")
                conf  = field.get("ValueDetection", {}).get("Confidence", 0)
                if key and value and conf > 80:
                    fields[key] = value

        return {
            "document_type":   fields.get("document_type", "unknown"),
            "last_name":       fields.get("last_name", ""),
            "first_name":      fields.get("given_name", ""),
            "date_of_birth":   fields.get("date_of_birth", ""),
            "expiration_date": fields.get("expiration_date", ""),
            "id_type":         fields.get("id_type", ""),
            "mrz_line1":       fields.get("mrz_line1", ""),
            "mrz_line2":       fields.get("mrz_line2", ""),
        }
