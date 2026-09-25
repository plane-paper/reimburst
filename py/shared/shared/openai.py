"""Small shared transport for OpenAI Responses API providers."""

import asyncio
import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class OpenAiResponsesProvider:
    """Base class for providers that use the Responses API."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def post(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._post, payload)

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
            raise RuntimeError(f"OpenAI returned {error.code}: {detail}") from error
        if not isinstance(result, dict):
            raise RuntimeError("OpenAI returned an invalid response")
        return result
