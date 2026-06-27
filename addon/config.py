from __future__ import annotations

from aqt import mw

_PACKAGE = __name__.split(".")[0]


def get() -> dict:
    return mw.addonManager.getConfig(_PACKAGE) or {}
