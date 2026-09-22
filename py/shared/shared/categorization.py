"""LLM-backed, taxonomy-constrained receipt line-item categorization."""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from shared.taxonomy import UNCATEGORIZED


@dataclass(frozen=True)
class CategorizationInput:
    id: int
    description: str
    amount_cents: int


@dataclass(frozen=True)
class CategorizationResult:
    line_item_id: int
    category: str
    needs_review: bool


class CategorizationProvider(Protocol):
    async def categorize(
        self, items: list[CategorizationInput], taxonomy: list[str]
    ) -> list[CategorizationResult]: ...


def categorization_schema(taxonomy: list[str]) -> dict[str, Any]:
    """Responses API strict JSON schema, whose enum is the active taxonomy."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "line_item_id": {"type": "integer"},
                        "category": {"type": "string", "enum": taxonomy},
                        "confidence": {"type": "string", "enum": ["high", "low"]},
                    },
                    "required": ["line_item_id", "category", "confidence"],
                },
            }
        },
        "required": ["items"],
    }


def parse_categorizations(
    payload: dict[str, Any], items: list[CategorizationInput], taxonomy: list[str]
) -> list[CategorizationResult]:
    """Validate model output and safely fall back for every missing/invalid item."""
    allowed = set(taxonomy)
    expected_ids = {item.id for item in items}
    results: dict[int, CategorizationResult] = {}
    for value in payload.get("items", []):
        if not isinstance(value, dict):
            continue
        item_id = value.get("line_item_id")
        category = value.get("category")
        confidence = value.get("confidence")
        if (
            not isinstance(item_id, int)
            or item_id not in expected_ids
            or item_id in results
            or not isinstance(category, str)
            or category not in allowed
            or confidence not in {"high", "low"}
        ):
            continue
        results[item_id] = CategorizationResult(
            line_item_id=item_id,
            category=category,
            needs_review=confidence == "low" or category == UNCATEGORIZED,
        )
    return [
        results.get(
            item.id,
            CategorizationResult(item.id, UNCATEGORIZED, needs_review=True),
        )
        for item in items
    ]


class OpenAiCategorizationProvider:
    """OpenAI Responses API implementation using Structured Outputs."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_environment(cls) -> "OpenAiCategorizationProvider":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY must be configured for categorization")
        return cls(api_key, os.environ.get("OPENAI_CATEGORIZATION_MODEL", "gpt-4o-mini"))

    async def categorize(
        self, items: list[CategorizationInput], taxonomy: list[str]
    ) -> list[CategorizationResult]:
        if UNCATEGORIZED not in taxonomy:
            raise ValueError("The taxonomy must include uncategorized")
        request_body = {
            "model": self.model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Categorize receipt line items. Select only a supplied category. "
                        "Use uncategorized and low confidence if the description is ambiguous."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "taxonomy": taxonomy,
                            "line_items": [
                                {
                                    "line_item_id": item.id,
                                    "description": item.description,
                                    "amount_cents": item.amount_cents,
                                }
                                for item in items
                            ],
                        }
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "receipt_categorizations",
                    "strict": True,
                    "schema": categorization_schema(taxonomy),
                }
            },
        }
        response = await asyncio.to_thread(self._post, request_body)
        output_text = response.get("output_text")
        if not isinstance(output_text, str):
            raise RuntimeError("OpenAI categorization returned no text output")
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenAI categorization returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise RuntimeError("OpenAI categorization returned an invalid payload")
        return parse_categorizations(payload, items, taxonomy)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed API endpoint
                result = json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI categorization returned {error.code}: {detail}") from error
        if not isinstance(result, dict):
            raise RuntimeError("OpenAI categorization returned an invalid response")
        return result
