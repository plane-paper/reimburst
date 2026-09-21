"""Provider-neutral receipt extraction models and Azure implementation."""

import asyncio
import datetime as dt
import json
import os
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Protocol, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ExtractedLineItem:
    description: str
    amount_cents: int


@dataclass(frozen=True)
class ReceiptExtraction:
    merchant: str | None
    date: dt.date | None
    currency: str | None
    total_cents: int | None
    tax_cents: int | None
    line_items: list[ExtractedLineItem]
    raw: dict[str, Any]


class OcrProvider(Protocol):
    async def extract(self, image: bytes, content_type: str) -> ReceiptExtraction: ...


def money_to_cents(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def parse_azure_receipt(result: dict[str, Any]) -> ReceiptExtraction:
    documents = result.get("analyzeResult", {}).get("documents", [])
    fields = documents[0].get("fields", {}) if documents else {}

    def field_value(name: str) -> Any:
        field = fields.get(name, {})
        return field.get("valueCurrency", {}).get("amount", field.get("content"))

    date_value = field_value("TransactionDate")
    parsed_date: dt.date | None = None
    if isinstance(date_value, str):
        try:
            parsed_date = dt.date.fromisoformat(date_value)
        except ValueError:
            pass

    items: list[ExtractedLineItem] = []
    for item in fields.get("Items", {}).get("valueArray", []):
        properties = item.get("valueObject", {})
        description = properties.get("Description", {}).get("content", "Unspecified item")
        amount = properties.get("TotalPrice", {}).get("valueCurrency", {}).get("amount")
        if amount is None:
            amount = properties.get("Price", {}).get("valueCurrency", {}).get("amount")
        cents = money_to_cents(amount)
        if cents is not None:
            items.append(ExtractedLineItem(description=description, amount_cents=cents))

    currency = None
    for name in ("Total", "TotalTax"):
        code = fields.get(name, {}).get("valueCurrency", {}).get("currencyCode")
        if code:
            currency = code
            break

    return ReceiptExtraction(
        merchant=field_value("MerchantName"),
        date=parsed_date,
        currency=currency,
        total_cents=money_to_cents(field_value("Total")),
        tax_cents=money_to_cents(field_value("TotalTax")),
        line_items=items,
        raw=result,
    )


class AzureDocumentIntelligenceOcrProvider:
    """Azure's prebuilt receipt model, kept behind the OcrProvider boundary."""

    def __init__(self, endpoint: str, api_key: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    @classmethod
    def from_environment(cls) -> "AzureDocumentIntelligenceOcrProvider":
        endpoint = os.environ.get("AZURE_DI_ENDPOINT")
        api_key = os.environ.get("AZURE_DI_KEY")
        if not endpoint or not api_key:
            raise RuntimeError("AZURE_DI_ENDPOINT and AZURE_DI_KEY must be configured for OCR")
        return cls(endpoint, api_key)

    async def extract(self, image: bytes, content_type: str) -> ReceiptExtraction:
        result = await asyncio.to_thread(self._analyze, image, content_type)
        return parse_azure_receipt(result)

    def _request(
        self, url: str, *, data: bytes | None = None, content_type: str | None = None
    ) -> Any:
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(url, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - endpoint is configured by operator
                return response.status, response.headers, json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Azure Document Intelligence returned {error.code}: {detail}"
            ) from error

    def _analyze(self, image: bytes, content_type: str) -> dict[str, Any]:
        url = (
            f"{self.endpoint}/documentintelligence/documentModels/prebuilt-receipt:analyze"
            "?api-version=2024-11-30"
        )
        _, headers, _ = self._request(url, data=image, content_type=content_type)
        operation_url = headers.get("Operation-Location")
        if not operation_url:
            raise RuntimeError("Azure Document Intelligence did not return an operation URL")
        for _ in range(30):
            _, _, result = self._request(operation_url)
            status = result.get("status")
            if status == "succeeded":
                return cast(dict[str, Any], result)
            if status == "failed":
                raise RuntimeError("Azure Document Intelligence could not extract this receipt")
            import time

            time.sleep(1)
        raise RuntimeError("Azure Document Intelligence extraction timed out")


def extraction_as_json(extraction: ReceiptExtraction) -> dict[str, Any]:
    result = asdict(extraction)
    result["date"] = extraction.date.isoformat() if extraction.date else None
    return result
