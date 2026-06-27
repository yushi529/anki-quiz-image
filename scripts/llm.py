"""
Thin LLM abstraction for entity identification.
Swap the _call_gemini implementation here to switch models.
"""

import json
import os
import re
from dataclasses import dataclass, field


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

PROMPT_TEMPLATE = """\
競技クイズ（早押しクイズ）のカードから、問われているエンティティを特定してください。

問題文: {question}
解答: {answer}

以下のJSON形式のみで回答してください（説明文は不要）:
{{
  "entity_name": "エンティティの正式名称（日本語）",
  "wikipedia_title_ja": "日本語Wikipediaの記事タイトル（存在しない場合はnull）",
  "wikipedia_title_en": "英語Wikipediaの記事タイトル（存在しない場合はnull）",
  "commons_queries": ["Wikimedia Commons画像検索クエリ1", "クエリ2"],
  "confidence": "high/medium/low（Wikipediaタイトルの確信度）"
}}

Google検索でWikipedia記事タイトルを必ず確認し、正確なタイトルを返してください。"""


@dataclass
class EntityResult:
    entity_name: str
    wikipedia_title_ja: str | None
    wikipedia_title_en: str | None
    commons_queries: list[str]
    confidence: str  # "high" | "medium" | "low"
    wikipedia_url: str | None = None
    raw_response: str = ""


def identify_entity(question: str, answer: str) -> EntityResult:
    """Identify the entity from a quiz question+answer pair."""
    return _call_gemini(question, answer)


def _call_gemini(question: str, answer: str) -> EntityResult:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")

    client = genai.Client(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(question=question, answer=answer)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
        ),
    )

    raw_text = response.text or ""

    wikipedia_url = _extract_wikipedia_url(response)

    return _parse_response(raw_text, answer, wikipedia_url)


def _extract_wikipedia_url(response) -> str | None:
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        for chunk in chunks:
            uri = getattr(getattr(chunk, "web", None), "uri", None)
            if uri and "wikipedia.org" in uri:
                return uri
    except (AttributeError, IndexError, TypeError):
        pass
    return None


def _parse_response(raw_text: str, answer: str, wikipedia_url: str | None) -> EntityResult:
    match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
    if not match:
        return _fallback(answer, wikipedia_url, raw_text)

    try:
        data = json.loads(match.group())
        return EntityResult(
            entity_name=data.get("entity_name") or answer,
            wikipedia_title_ja=data.get("wikipedia_title_ja"),
            wikipedia_title_en=data.get("wikipedia_title_en"),
            commons_queries=data.get("commons_queries") or [answer],
            confidence=data.get("confidence", "low"),
            wikipedia_url=wikipedia_url,
            raw_response=raw_text,
        )
    except json.JSONDecodeError:
        return _fallback(answer, wikipedia_url, raw_text)


def _fallback(answer: str, wikipedia_url: str | None, raw_text: str) -> EntityResult:
    return EntityResult(
        entity_name=answer,
        wikipedia_title_ja=None,
        wikipedia_title_en=None,
        commons_queries=[answer],
        confidence="low",
        wikipedia_url=wikipedia_url,
        raw_response=raw_text,
    )
