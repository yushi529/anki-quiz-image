# CLAUDE.md — Anki クイズ画像 半自動付与アドオン

> このファイルは、別チャットで詰めた設計の引き継ぎメモです。実装はここ（Claude Code）で行います。
> ユーザーは日本語で対話します。コード識別子・パス・技術用語は英語のままで構いません。

## プロジェクト目的

競技クイズ（早押しクイズ）用 Anki カードの **裏面に、問題文・解答に対応する画像を半自動で付与**する。
復習中（PC）にボタンを押す → 候補画像をチューザーで提示 → 選んだ画像を裏面フィールドに `<img>` として埋め込む。
全カードでAPIを叩かず、**ボタン押下時のみ**通信する（コスト最小化）。

## 最重要の制約（読み飛ばさないこと）

- **現在の `front.html` / `back.html` で実装されている機能を保ったままコードの変更を行うこと。**
- **Python/PyQt アドオンはデスクトップ版 Anki でしか動かない。** AnkiMobile / AnkiDroid はアドオン非対応。
- ユーザーは **普段スマホで復習**、PC でも復習可能。
  → 画像付与処理は **PC で実行**し、埋め込まれた `<img>` は AnkiWeb 同期でスマホに反映される、という運用。
- **設計上の帰結**: 「画像取得ボタン」は **カードテンプレートに直書きせず、アドオンから復習画面に注入**する（desktop 限定で表示）。
  テンプレートに直書きするとスマホ復習時に機能しない死にボタンが出るため。

## 確定済みの設計判断

- **対象**: 汎用（絵画・観光地に限らない）。品質管理は候補チューザーで担保する。
- **画像ソース**（無料・ライセンスクリーン優先。Google 画像検索は権利不明なので避ける）:
  1. Wikipedia REST `page/summary/{title}` の lead image（`thumbnail` / `originalimage`）
  2. Wikidata `P18 (image)`
  3. Wikimedia Commons 検索（候補を複数集める用）
  4. （任意・後段フォールバック）Google Custom Search JSON API（無料枠 100 クエリ/日）
- **エンティティ同定 / 検索語生成**: **Gemini Flash または Flash-Lite ＋ Google 検索グラウンディング**。
  - 入力 `問題文 + 解答` → 出力 `正規エンティティ名 / Wikipedia タイトル / 検索クエリ` を **JSON で構造化出力**させる。
  - グラウンディングで Wikipedia URL まで取れると、「解答 → 正しい記事 → 代表画像」の最難関が省ける。
  - **LLM 呼び出しは差し替え可能な薄い抽象レイヤ越し**にする（後で Claude Haiku 等へ変更できるように）。
  - Gemini 無料枠の現状: Flash/Flash-Lite 系、約 15 RPM / 1,500 RPD / 1M TPM、カード不要、function calling・JSON モード可。
    注意: **無料枠は入出力がモデル改善に使われ得る**。クイズカードは機微でないので可だが認識しておく。
- **UX**: 候補チューザー（QDialog）。サムネをグリッド表示 → クリックで確定 → フル解像度 DL → メディア登録 → 裏面に追記。
  合う候補がなければキャンセル可能。

## ノートタイプ / テンプレート

- フィールド: `表面`（問題文）, `裏面`（解答＋既存解説。**ここに画像を追記する**）。
- 既存テンプレートは確定ポイント（早押し位置）を再現するタイプライター表示。
  忠実なコピーが `card_templates/front.html` / `card_templates/back.html` にある（Anki は実行時にこれらを読まない。参照・版管理用）。
- **注入時に壊してはいけない既存JS**:
  - `sessionStorage`: `ankiStartTime`, `ankiBuzzIndex`
  - グローバル: `window.ankiTimer`, `window.ankiCountdown`
  - DOM 目印: `#q-source`, `#q-display`, `#answer-area`
- 注入ボタンの `onclick` は `pycmd('quizimg:fetch')` を発火させる。

## アドオン実装メモ

- **ボタン注入**: `reviewer_did_show_answer`（裏面表示時）に JS 注入、または reviewer 下部バーへ追加。`pycmd('quizimg:fetch')` 発火。
- **受信**: `gui_hooks.webview_did_receive_js_message` で `quizimg:fetch` を捕捉し `(handled, value)` を返す。
- **現在ノート取得**: `mw.reviewer.card.note()`。
- **スレッド**: 通信は `mw.taskman.run_in_background`、UI 更新は `mw.taskman.run_on_main`。reviewer を固めない。
- **ノート更新**: `aqt.operations.CollectionOp` 経由で Undo 対応。
  ただし復習中のコレクション変更は reviewer 状態と競合し得るので、**再描画挙動は実機検証必須**。
- **即時反映**: 永続化と並行して現在の DOM に `<img>` を直接注入する手もある（カード再描画を回避できる）。
- **メディア登録**: `col.media.write_data(desired_fname, data)` の返り値（実ファイル名）で `<img src="...">` を裏面に追記。
- **依存ライブラリの罠**: Anki は独自の Python 環境。`uv pip install` は効かない。
  Gemini / HTTP は標準ライブラリ `urllib.request` で叩くか、必要な依存をアドオンフォルダに **vendoring** する。
- **API キー**: 環境変数 or アドオンの `config.json` から読む。**リポジトリにコミットしない**（`.gitignore`）。

## 想定プロジェクト構成

```
anki-quiz-image/                # リポジトリ直下（Claude Code ワークスペース）
├── CLAUDE.md                   # このファイル
├── README.md
├── pyproject.toml              # uv 管理（Phase 0 スクリプト用の環境）
├── .env.example                # GEMINI_API_KEY=...
├── .gitignore                  # .env, addon/config.json の実値など
├── card_templates/
│   ├── front.html              # 表面テンプレート 忠実コピー
│   └── back.html               # 裏面テンプレート 忠実コピー（注入ポイントのコメント付き）
├── addon/                      # 実際の Anki アドオン（addons21 へ symlink）
│   ├── __init__.py             # hooks 登録（webview_did_receive_js_message ほか）
│   ├── manifest.json
│   ├── config.json             # フィールド名・ソース有効化・API キー等
│   ├── config.md
│   ├── llm.py                  # Gemini 同定（差し替え可能な薄い抽象）
│   ├── image_sources.py        # Wikipedia / Wikidata / Commons フェッチャ
│   └── chooser.py              # QDialog 候補チューザー
└── scripts/
    └── phase0_eval.py          # スタンドアロン同定ヒット率検証（Anki 非依存）
```

## 開発ワークフロー

- 開発はこのリポジトリで。`addon/` を Anki のアドオンフォルダに symlink して実機テスト:
  ```
  ln -s "$PWD/addon" ~/.local/share/Anki2/addons21/quiz_image_dev
  ```
- アドオンはホットリロードされない → コード変更後は **Anki 再起動**で反映。
- `scripts/phase0_eval.py` はスタンドアロン（uv 環境、`google-genai` SDK 使用可）。Anki とは独立に同定ヒット率を検証する。

## フェーズ

- **Phase 0 — 同定ヒット率検証（Anki 非依存）** ← まずここから
  手持ちカード数十枚で `問題文+解答 → Gemini grounding → Wikipedia/Commons 候補` のヒット率をログ。
  ここで LLM / ソース構成と、チューザーに出す候補数を確定する。
- **Phase 1 — アドオン化**
  ボタン注入 ＋ pycmd ＋ チューザー ＋ メディア登録 ＋ 裏面追記（CollectionOp）。PC 復習で動作確認。
- **Phase 2 — 拡張**
  必要に応じ Google CSE 等フォールバック候補ソース、設定 UI、再実行時の上書き/追記/スキップ挙動。

## 未決事項（実装前にユーザーと詰める）

- 裏面の既存解説と画像の配置（解答の下に追記でよいか／専用 div を設けるか）。
- 再実行時の挙動（上書き / 追記 / スキップ）。
- 候補ソースの優先順位と、チューザーに出す候補枚数。
- Gemini に渡すプロンプト設計（曖昧な解答を問題文の文脈で解決させる）。

## 現在の状況

設計は確定。**次の一手は Phase 0 の `scripts/phase0_eval.py`** を書き、実際のカードでヒット率を測ること。
