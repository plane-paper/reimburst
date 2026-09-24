"""LLM-backed outbound reimbursement request synopsis generation."""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from shared.categorization import OpenAiCategorizationProvider


@dataclass(frozen=True)
class OutboundItem:
    description: str
    amount_cents: int
    currency: str | None
    merchant: str | None
    receipt_date: str | None
    category: str | None


@dataclass(frozen=True)
class OutboundArtifact:
    synopsis: str
    subject: str
    body: str


def artifact_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "synopsis": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["synopsis", "subject", "body"],
    }


class OpenAiSynopsisProvider(OpenAiCategorizationProvider):
    """Responses API provider kept deliberately small alongside categorization."""

    @classmethod
    def from_environment(cls) -> "OpenAiSynopsisProvider":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY must be configured for synopsis generation")
        return cls(api_key, os.environ.get("OPENAI_SYNOPSIS_MODEL", "gpt-4o-mini"))

    async def generate(self, payer: str, items: list[OutboundItem]) -> OutboundArtifact:
        payload = {
            "model": self.model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Create a concise, professional reimbursement request email. "
                        "Use only the supplied facts. Include an itemized list in the body, "
                        "do not invent a policy or payment deadline."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"external_payer": payer, "items": [item.__dict__ for item in items]}
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "outbound_request",
                    "strict": True,
                    "schema": artifact_schema(),
                }
            },
        }
        response = await asyncio.to_thread(self._post, payload)
        output = response.get("output_text")
        try:
            value = json.loads(output) if isinstance(output, str) else None
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenAI synopsis returned invalid JSON") from error
        if not isinstance(value, dict) or not all(
            isinstance(value.get(key), str) for key in ("synopsis", "subject", "body")
        ):
            raise RuntimeError("OpenAI synopsis returned an invalid payload")
        return OutboundArtifact(value["synopsis"], value["subject"], value["body"])
