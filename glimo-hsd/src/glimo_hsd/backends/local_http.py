"""OpenAI-compatible tool-calling chat backend for descriptive restatements."""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib import error, request

RESTATEMENT_TOOL_NAME = "record_backend_restatement_batch"

RESTATEMENT_SYSTEM_PROMPT = f"""Call the required {RESTATEMENT_TOOL_NAME} tool.
Do not explain.

Rewrite privacy-protected comments into concise third-person evidence sentences
for a hate-speech review backend. Return exactly one sentence for each input row,
in order. Preserve hate/non-hate label semantics, protected group cues, public
target groups, accusation roles, and offensive intensity in abstract form. Keep
direct privacy placeholders such as [PERSON], [USER], [URL], [LOCATION], [ORG],
and [STYLE] exactly as placeholders. Do not add new facts or stronger threats.
"""


def normalize_base_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/v1/chat/completions"):
        return endpoint[: -len("/v1/chat/completions")]
    if endpoint.endswith("/chat/completions"):
        return endpoint[: -len("/chat/completions")]
    if endpoint.endswith("/v1"):
        return endpoint[: -len("/v1")]
    return endpoint


def chat_endpoint(endpoint: str) -> str:
    return normalize_base_endpoint(endpoint) + "/v1/chat/completions"


def normalize_restatement(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class NoopRestatementBackend:
    model = "none"
    endpoint = None

    def restate_batch(
        self,
        batch: list[dict[str, str]],
        *,
        text_col: str,
        label_col: str,
        id_col: str | None,
    ) -> list[str]:
        del label_col, id_col
        return [str(row.get(text_col, "") or "") for row in batch]


class LocalHttpRestatementBackend:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def restate_batch(
        self,
        batch: list[dict[str, str]],
        *,
        text_col: str,
        label_col: str,
        id_col: str | None,
    ) -> list[str]:
        payload = self._payload(
            batch,
            text_col=text_col,
            label_col=label_col,
            id_col=id_col,
        )
        url = chat_endpoint(self.endpoint)
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                response = self._post_json(url, payload)
                return self._parse_response(response, expected_count=len(batch))
            except (
                RuntimeError,
                json.JSONDecodeError,
                TimeoutError,
                error.URLError,
                error.HTTPError,
            ) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(last_error or "restatement request failed")

    def _payload(
        self,
        batch: list[dict[str, str]],
        *,
        text_col: str,
        label_col: str,
        id_col: str | None,
    ) -> dict[str, Any]:
        rows = [
            {
                "id": str(row.get(id_col or "", "") or index + 1),
                "hs": str(row.get(label_col, "")),
                "protected_text": str(row.get(text_col, "") or ""),
            }
            for index, row in enumerate(batch)
        ]
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": RESTATEMENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Rewrite these rows:\n"
                    + json.dumps(rows, ensure_ascii=False),
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": RESTATEMENT_TOOL_NAME,
                        "description": "Record one ordered restatement per input item.",
                        "parameters": {
                            "type": "object",
                            "required": ["restatements"],
                            "properties": {
                                "restatements": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            },
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "tool_choice": "required",
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _parse_response(
        self,
        response: dict[str, Any],
        *,
        expected_count: int,
    ) -> list[str]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("response missing choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise RuntimeError("response missing message")
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            raise RuntimeError("response missing tool calls")
        function = tool_calls[0].get("function")
        if not isinstance(function, dict):
            raise RuntimeError("tool call missing function")
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise RuntimeError("tool call missing arguments")
        parsed = json.loads(arguments)
        restatements = parsed.get("restatements")
        if not isinstance(restatements, list):
            raise RuntimeError("tool payload missing restatements array")
        if len(restatements) != expected_count:
            raise RuntimeError(
                f"restatement count mismatch: expected {expected_count}, "
                f"got {len(restatements)}"
            )
        return [normalize_restatement(str(item or "")) for item in restatements]
