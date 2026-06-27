"""Image fetchers from Wikipedia, Wikidata, and Wikimedia Commons."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

_USER_AGENT = "AnkiQuizImage/0.1 (https://github.com/yushi529/anki-quiz-image)"


@dataclass
class ImageCandidate:
    url: str
    thumb_url: str
    source: str  # "wikipedia_ja" | "wikipedia_en" | "wikidata" | "commons"
    title: str
    description: str = ""


def fetch_candidates(
    entity_name: str,
    wikipedia_title_ja: str | None,
    wikipedia_title_en: str | None,
    commons_queries: list[str],
) -> list[ImageCandidate]:
    candidates: list[ImageCandidate] = []
    if wikipedia_title_ja:
        candidates.extend(_fetch_wikipedia(wikipedia_title_ja, "ja"))
    if wikipedia_title_en:
        candidates.extend(_fetch_wikipedia(wikipedia_title_en, "en"))
    if entity_name:
        candidates.extend(_fetch_wikidata(entity_name))
    if commons_queries:
        candidates.extend(_fetch_commons(commons_queries, max_per_query=3))
    return candidates


def _fetch_wikipedia(title: str, lang: str) -> list[ImageCandidate]:
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        data = _get(url)
        for key in ("originalimage", "thumbnail"):
            if key in data and "source" in data[key]:
                img_url = data[key]["source"]
                thumb = data.get("thumbnail", {}).get("source", img_url)
                return [ImageCandidate(
                    url=img_url, thumb_url=thumb,
                    source=f"wikipedia_{lang}",
                    title=data.get("title", title),
                    description=data.get("description", ""),
                )]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    except Exception:
        pass
    return []


def _fetch_wikidata(entity_name: str) -> list[ImageCandidate]:
    search_url = (
        "https://www.wikidata.org/w/api.php"
        f"?action=wbsearchentities&search={urllib.parse.quote(entity_name)}"
        "&language=ja&limit=3&format=json"
    )
    try:
        items = _get(search_url).get("search", [])
        if not items:
            return []
        qid = items[0]["id"]
        entity_data = _get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
        claims = entity_data.get("entities", {}).get(qid, {}).get("claims", {})
        candidates = []
        for claim in claims.get("P18", [])[:2]:
            filename = claim.get("mainsnak", {}).get("datavalue", {}).get("value", "")
            if not filename:
                continue
            encoded = urllib.parse.quote(filename.replace(" ", "_"), safe="")
            img_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}"
            candidates.append(ImageCandidate(
                url=img_url, thumb_url=f"{img_url}?width=300",
                source="wikidata", title=filename,
            ))
        return candidates
    except Exception:
        return []


def _fetch_commons(queries: list[str], max_per_query: int = 3) -> list[ImageCandidate]:
    candidates: list[ImageCandidate] = []
    seen: set[str] = set()
    for query in queries:
        if not query:
            continue
        url = (
            "https://commons.wikimedia.org/w/api.php"
            f"?action=query&list=search&srsearch={urllib.parse.quote(query)}"
            f"&srnamespace=6&srlimit={max_per_query}&format=json"
        )
        try:
            for r in _get(url).get("query", {}).get("search", []):
                filename = r["title"].removeprefix("File:")
                encoded = urllib.parse.quote(filename.replace(" ", "_"), safe="")
                img_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}"
                if img_url not in seen:
                    seen.add(img_url)
                    candidates.append(ImageCandidate(
                        url=img_url, thumb_url=f"{img_url}?width=300",
                        source="commons", title=filename,
                    ))
        except Exception:
            pass
        time.sleep(0.3)
    return candidates


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())
