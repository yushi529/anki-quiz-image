"""
Thin LLM abstraction. Uses Gemini REST API via urllib — no SDK vendoring needed.
Swap _call_gemini to change models or providers.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field

_PROMPT = """\
競技クイズ（早押しクイズ）のカードから、解答エンティティと、問題文中で具体的に名前が挙がっている関連エンティティ（作品・場所など）を特定してください。

問題文: {question}
解答: {answer}

以下のJSON形式のみで回答してください（説明文は不要）:
{{
  "entity_name": "解答エンティティの正式名称（日本語）",
  "wikipedia_title_ja": "日本語Wikipediaの記事タイトル（存在しない場合はnull）",
  "wikipedia_title_en": "英語Wikipediaの記事タイトル（存在しない場合はnull）",
  "commons_queries": ["Wikimedia Commons検索クエリ1", "クエリ2"],
  "confidence": "high/medium/low",
  "related": [
    {{
      "entity_name": "問題文中で名前が挙がっている関連エンティティ名",
      "wikipedia_title_ja": "日本語Wikipediaの記事タイトル",
      "wikipedia_title_en": "英語Wikipediaの記事タイトル",
      "commons_queries": ["検索クエリ"]
    }}
  ]
}}

related には問題文中で具体的な名称が挙がっているエンティティのみ含めてください（最大3件）。
名称が挙がっていないものは含めないでください。
Google検索でWikipedia記事タイトルを必ず確認し、正確なタイトルを返してください。"""


@dataclass
class RelatedEntity:
    entity_name: str
    wikipedia_title_ja: str | None
    wikipedia_title_en: str | None
    commons_queries: list[str]


@dataclass
class EntityResult:
    entity_name: str
    wikipedia_title_ja: str | None
    wikipedia_title_en: str | None
    commons_queries: list[str]
    confidence: str
    wikipedia_url: str | None = None
    related: list[RelatedEntity] = field(default_factory=list)


def identify_entity(
    question: str, answer: str, api_key: str, model: str = "gemini-2.0-flash"
) -> EntityResult:
    return _call_gemini(question, answer, api_key, model)


def _call_gemini(question: str, answer: str, api_key: str, model: str) -> EntityResult:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models"
        f"/{model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": _PROMPT.format(question=question, answer=answer)}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {"temperature": 0.1},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())

    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    wikipedia_url = _extract_wikipedia_url(data)
    return _parse(raw_text, answer, wikipedia_url)


def _extract_wikipedia_url(data: dict) -> str | None:
    try:
        chunks = data["candidates"][0]["groundingMetadata"]["groundingChunks"]
        for chunk in chunks:
            uri = chunk.get("web", {}).get("uri", "")
            if "wikipedia.org" in uri:
                return uri
    except (KeyError, IndexError, TypeError):
        pass
    return None


def _parse(raw: str, answer: str, wikipedia_url: str | None) -> EntityResult:
    # Use find/rfind to avoid regex failing on nested JSON
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return _fallback(answer, wikipedia_url)
    try:
        d = json.loads(raw[start:end + 1])
        related = [
            RelatedEntity(
                entity_name=r.get("entity_name", ""),
                wikipedia_title_ja=r.get("wikipedia_title_ja"),
                wikipedia_title_en=r.get("wikipedia_title_en"),
                commons_queries=r.get("commons_queries") or [],
            )
            for r in d.get("related", [])[:3]
            if r.get("entity_name")
        ]
        return EntityResult(
            entity_name=d.get("entity_name") or answer,
            wikipedia_title_ja=d.get("wikipedia_title_ja"),
            wikipedia_title_en=d.get("wikipedia_title_en"),
            commons_queries=d.get("commons_queries") or [answer],
            confidence=d.get("confidence", "low"),
            wikipedia_url=wikipedia_url,
            related=related,
        )
    except json.JSONDecodeError:
        return _fallback(answer, wikipedia_url)


def _fallback(answer: str, wikipedia_url: str | None) -> EntityResult:
    return EntityResult(
        entity_name=answer,
        wikipedia_title_ja=None,
        wikipedia_title_en=None,
        commons_queries=[answer],
        confidence="low",
        wikipedia_url=wikipedia_url,
    )
