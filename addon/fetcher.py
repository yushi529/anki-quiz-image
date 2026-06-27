"""Orchestrates the fetch → chooser → save pipeline."""
from __future__ import annotations

import json
import re
import time
import urllib.request

from aqt import mw
from aqt.operations import CollectionOp
from aqt.utils import tooltip

_USER_AGENT = "AnkiQuizImage/0.1"


def run(card) -> None:
    from . import config
    cfg = config.get()

    note = card.note()
    front_field = cfg.get("front_field", "表面")
    back_field = cfg.get("back_field", "裏面")

    if back_field not in note:
        tooltip(f"フィールド '{back_field}' が見つかりません。アドオン設定を確認してください。")
        return

    if "<img" in note[back_field]:
        tooltip("画像は既に設定されています（スキップ）")
        return

    api_key = cfg.get("gemini_api_key", "")
    if not api_key:
        tooltip("Gemini API キーが未設定です。アドオン設定 → gemini_api_key を入力してください。")
        return

    question = note[front_field] if front_field in note else ""
    answer = _extract_answer(note[back_field])
    model = cfg.get("gemini_model", "gemini-2.0-flash")
    max_cand = int(cfg.get("max_candidates", 9))

    tooltip("画像を検索中…")

    def background():
        from . import llm, image_sources
        entity = llm.identify_entity(question, answer, api_key, model)
        candidates = image_sources.fetch_candidates(
            entity_name=entity.entity_name,
            wikipedia_title_ja=entity.wikipedia_title_ja,
            wikipedia_title_en=entity.wikipedia_title_en,
            commons_queries=entity.commons_queries,
        )
        candidates = candidates[:max_cand]

        thumb_data: dict[str, bytes | None] = {}
        for c in candidates:
            try:
                req = urllib.request.Request(c.thumb_url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=10) as r:
                    thumb_data[c.url] = r.read()
            except Exception:
                thumb_data[c.url] = None

        return candidates, thumb_data

    def on_done(future):
        try:
            candidates, thumb_data = future.result()
        except Exception as e:
            tooltip(f"検索エラー: {e}")
            return

        if not candidates:
            tooltip("画像が見つかりませんでした")
            return

        _show_chooser(note, back_field, candidates, thumb_data)

    mw.taskman.run_in_background(background, on_done)


def _show_chooser(note, back_field: str, candidates, thumb_data: dict) -> None:
    from . import chooser
    dialog = chooser.ImageChooser(candidates, thumb_data, parent=mw)
    if dialog.exec() != chooser.ImageChooser.DialogCode.Accepted:
        return

    selected = dialog.selected_candidate
    if not selected:
        return

    def download_and_register():
        req = urllib.request.Request(selected.url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            content_type = r.headers.get("Content-Type", "")
        ext = _guess_ext(selected.url, content_type)
        fname = f"quiz_img_{note.id}_{int(time.time())}.{ext}"
        actual_fname = mw.col.media.write_data(fname, data)
        return actual_fname

    def on_registered(future):
        try:
            actual_fname = future.result()
        except Exception as e:
            tooltip(f"保存エラー: {e}")
            return
        img_tag = f'<br><img src="{actual_fname}">'
        note[back_field] += img_tag
        _commit_note(note, img_tag)

    mw.taskman.run_in_background(download_and_register, on_registered)


def _commit_note(note, img_tag: str) -> None:
    # Inject immediately into the current DOM for visual feedback
    escaped = json.dumps(img_tag)
    mw.reviewer.web.eval(
        f"var a = document.getElementById('answer-area');"
        f"if (a) a.innerHTML += {escaped};"
    )

    def op(col):
        return col.update_note(note)

    CollectionOp(parent=mw, op=op).success(
        lambda _: tooltip("画像を保存しました ✓")
    ).run_in_background()


def _extract_answer(back_field: str) -> str:
    text = back_field.split("\n")[0].split("<br>")[0]
    return re.sub(r"<[^>]+>", "", text).strip()


def _guess_ext(url: str, content_type: str) -> str:
    path = url.split("?")[0].lower()
    for ext in ("jpg", "jpeg", "png", "gif", "webp", "svg"):
        if path.endswith(ext):
            return "jpg" if ext == "jpeg" else ext
    if "png" in content_type:
        return "png"
    if "gif" in content_type:
        return "gif"
    if "webp" in content_type:
        return "webp"
    return "jpg"
