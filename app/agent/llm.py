"""
app/agent/llm.py — Groq LLM client with personalisation support
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from groq import Groq, APIConnectionError, APIStatusError, RateLimitError, PermissionDeniedError, AuthenticationError
from app.agent.models import SearchResult, UserPreferences
from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.config import Settings

logger = get_logger(__name__)

_TONE_INSTRUCTIONS = {
    "formal":   "Use formal, professional language. Avoid contractions and slang. Write in structured, precise prose.",
    "casual":   "Use a friendly, conversational tone. Feel free to use natural language and be approachable.",
    "concise":  "Be extremely brief and direct. Use short paragraphs. Prioritise key facts only. No filler.",
    "detailed": "Be thorough and comprehensive. Explain context, nuance, and implications. Use examples where helpful.",
    "balanced": "Use clear, neutral prose — neither too formal nor too casual. Be informative but readable.",
}

_BASE_SYSTEM = """You are NEXUS, a precise AI research assistant that synthesizes web search results into accurate, well-written answers.

Core rules:
1. Base your answer STRICTLY on the provided search results — never fabricate.
2. Include specific details: dates, numbers, versions, names.
3. If sources conflict, acknowledge it.
4. Do NOT start with "Based on the search results…" — just answer directly.
5. Do NOT mention these instructions or that you are an AI.
"""


def _build_system(prefs: UserPreferences) -> str:
    parts = [_BASE_SYSTEM]

    # Tone
    tone_instr = _TONE_INSTRUCTIONS.get(prefs.tone, _TONE_INSTRUCTIONS["balanced"])
    parts.append(f"\nTone: {tone_instr}")

    # Name
    if prefs.name:
        parts.append(f"\nThe user's name is {prefs.name}. You may address them naturally if appropriate.")

    # Language — strong repeated directive
    lang = (prefs.language or "English").strip()
    if lang.lower() != "english":
        parts.append(
            f"\n\nCRITICAL LANGUAGE INSTRUCTION:"
            f"\nYou MUST write your ENTIRE response exclusively in {lang}."
            f"\nEvery single word must be in {lang} — no English whatsoever."
            f"\nThis overrides everything else. Responding in any other language is a critical failure."
        )

    # News categories
    if prefs.news_categories:
        cats = ", ".join(prefs.news_categories)
        parts.append(f"\nThe user prefers news about: {cats}. Prioritise these topics when relevant.")

    return "\n".join(parts)


def _build_user_message(query: str, results: list[SearchResult], lang: str = "English") -> str:
    lines = [f"Question: {query}\n\nSearch results:\n"]
    for i, r in enumerate(results, 1):
        date_str = f"  [{r.date}]" if r.date else ""
        lines.append(f"[{i}]{date_str} {r.title}\n    URL: {r.url}\n    {r.snippet}\n")
    instruction = "Write a comprehensive, accurate answer based only on the above sources."
    if lang.lower() != "english":
        instruction += f" Your response MUST be written entirely in {lang}. Do not use English."
    lines.append(f"\n{instruction}")
    return "\n".join(lines)


class LLMClient:
    def __init__(self, settings: "Settings") -> None:
        # Placeholder is OK — real key comes per-request from UI
        key = settings.groq_api_key or ""
        if key and key.startswith("gsk_your"):
            raise ValueError("GROQ_API_KEY looks like a placeholder.")
        self._client      = Groq(api_key=key or "__placeholder__")
        self._default_model = settings.groq_model
        self._max_tokens  = settings.groq_max_tokens
        self._temperature = settings.groq_temperature
        logger.info(f"[llm] initialized model={self._default_model}")

    @property
    def model(self) -> str:
        return self._default_model

    def generate(self, query: str, results: list[SearchResult], prefs: UserPreferences | None = None, api_key: str = "") -> tuple[str, str]:
        """Returns (answer, model_used)."""
        if not results:
            return ("No search results found. Try rephrasing your query.", self._default_model)

        prefs       = prefs or UserPreferences()
        use_model   = prefs.model if prefs.model else self._default_model
        system_msg  = _build_system(prefs)
        user_msg    = _build_user_message(query, results, lang=prefs.language or "English")

        logger.debug(f"[llm] model={use_model} tone={prefs.tone} lang={prefs.language}")

        # Use per-request key if provided (UI key), otherwise use default client
        from groq import Groq as _Groq
        client = _Groq(api_key=api_key) if api_key else self._client

        try:
            completion = client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            answer = completion.choices[0].message.content.strip()
            usage  = completion.usage
            logger.info(f"[llm] done — prompt={usage.prompt_tokens} completion={usage.completion_tokens}")
            return (answer, use_model)

        except AuthenticationError:
            raise RuntimeError(
                "Invalid API key. Please check your Groq key in Settings."
            )
        except PermissionDeniedError:
            raise RuntimeError(
                "API key rejected by Groq (permission denied). "
                "Please verify your key at console.groq.com/keys"
            )
        except RateLimitError:
            raise RuntimeError("Groq API rate limit reached. Please wait a moment and try again.")
        except APIConnectionError as exc:
            raise RuntimeError(f"Could not connect to Groq API: {exc}")
        except APIStatusError as exc:
            raise RuntimeError(f"Groq API error ({exc.status_code}): check your key or model name.")
        except Exception as exc:
            logger.exception(f"[llm] unexpected: {exc}")
            raise RuntimeError(f"Unexpected LLM error: {exc}")