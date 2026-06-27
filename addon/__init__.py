from __future__ import annotations

from aqt import gui_hooks, mw


def _on_show_answer(card) -> None:
    mw.reviewer.web.eval("""
    (function() {
        if (document.getElementById('quizimg-btn')) return;
        const btn = document.createElement('button');
        btn.id = 'quizimg-btn';
        btn.textContent = '画像を取得';
        Object.assign(btn.style, {
            position: 'fixed', bottom: '14px', right: '14px', zIndex: '9999',
            padding: '8px 18px', background: '#55aa77', color: '#fff',
            border: 'none', borderRadius: '6px', cursor: 'pointer',
            fontSize: '14px', boxShadow: '0 2px 6px rgba(0,0,0,.35)',
        });
        btn.onclick = () => pycmd('quizimg:fetch');
        document.body.appendChild(btn);
    })();
    """)


def _on_js_message(handled, message, context):
    if message != "quizimg:fetch":
        return handled
    from . import fetcher
    fetcher.run(mw.reviewer.card)
    return (True, None)


gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
gui_hooks.webview_did_receive_js_message.append(_on_js_message)
