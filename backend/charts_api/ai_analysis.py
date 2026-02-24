from __future__ import annotations

import base64
from typing import Any

import requests


class OpenAIChartAnalyzer:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        organization: str = "",
        project: str = "",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.organization = organization
        self.project = project

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def analyze_chart(self, image_bytes: bytes, prompt: str, system_prompt: str = "") -> dict[str, Any]:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        if self.project:
            headers["OpenAI-Project"] = self.project

        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{image_b64}",
                        },
                    ],
                }
            ],
        }
        if system_prompt:
            payload["instructions"] = system_prompt

        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400:
            try:
                error_message = response.json().get("error", {}).get("message")
            except Exception:
                error_message = "OpenAI analysis request failed."
            raise RuntimeError(error_message or "OpenAI analysis request failed.")

        payload = response.json()
        text = payload.get("output_text", "")
        if not text:
            text = self._extract_fallback_text(payload)

        return {
            "analysis_text": str(text).strip(),
            "analysis_model": payload.get("model") or self.model,
            "usage": payload.get("usage", {}),
            "response_id": payload.get("id", ""),
        }

    def _extract_fallback_text(self, payload: dict[str, Any]) -> str:
        outputs = payload.get("output") or []
        chunks: list[str] = []
        for item in outputs:
            if not isinstance(item, dict):
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                text_value = content.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    chunks.append(text_value.strip())
        return "\n\n".join(chunks)
