"""Official Gemini SDK adapter; no retrieval, source mapping or raw logging."""

from google import genai
from google.genai import types

from askanu_rag.config import Settings
from askanu_rag.synthesis import SYSTEM_INSTRUCTION, SynthesisContext, SynthesisError


class GeminiSynthesisClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def synthesize(self, context: SynthesisContext) -> str:
        try:
            if not self._settings.api_key.get_secret_value():
                raise SynthesisError()
            # Per-call context managers close both clients, including on failure.
            # Pin the official endpoint; environment cannot redirect evidence/key.
            with genai.Client(
                api_key=self._settings.api_key.get_secret_value(),
                vertexai=False,
                http_options=types.HttpOptions(
                    base_url="https://generativelanguage.googleapis.com",
                    timeout=int(self._settings.timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                async with client.aio as async_client:
                    response = await async_client.models.generate_content(
                        model=self._settings.model,
                        contents=context.contents(),
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            response_mime_type="application/json",
                            response_json_schema=context.response_schema(),
                            max_output_tokens=self._settings.max_output_tokens,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                                disable=True
                            ),
                        ),
                    )
                    # Never accept partial/truncated/blocked responses.
                    candidates = response.candidates or []
                    if len(candidates) != 1 or candidates[0].finish_reason != "STOP":
                        raise SynthesisError()
                    parts = candidates[0].content.parts if candidates[0].content else []
                    if not parts or any(
                        part.function_call or part.inline_data for part in parts
                    ):
                        raise SynthesisError()
                    raw = response.text
                    if not raw:
                        raise SynthesisError()
                    return raw
        except Exception:
            # SDK exceptions can contain request details; never retain their text.
            raise SynthesisError() from None
