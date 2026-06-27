"""QDialog for selecting an image from candidates."""
from __future__ import annotations

from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QIcon,
    QPixmap,
    QScrollArea,
    QSize,
    Qt,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_THUMB = 180
_COLS = 3


class ImageChooser(QDialog):
    def __init__(self, candidates, thumb_data: dict, parent=None):
        super().__init__(parent)
        self.selected_candidate = None
        self._build(candidates, thumb_data)

    def _build(self, candidates, thumb_data: dict) -> None:
        self.setWindowTitle("画像を選択（クリックで確定）")
        self.setMinimumWidth(_COLS * (_THUMB + 24) + 40)

        root = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)

        for i, cand in enumerate(candidates):
            btn = self._make_btn(cand, thumb_data.get(cand.url))
            grid.addWidget(btn, i // _COLS, i % _COLS)

        scroll.setWidget(grid_widget)
        root.addWidget(scroll)

        bar = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        bar.rejected.connect(self.reject)
        root.addWidget(bar)

    def _make_btn(self, candidate, img_bytes) -> QToolButton:
        btn = QToolButton()
        btn.setFixedSize(_THUMB + 20, _THUMB + 36)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(_THUMB, _THUMB))
        btn.setToolTip(candidate.title)

        if img_bytes:
            px = QPixmap()
            px.loadFromData(img_bytes)
            scaled = px.scaled(
                _THUMB, _THUMB,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            btn.setIcon(QIcon(scaled))
        else:
            btn.setText("(読込失敗)")

        btn.setText(candidate.source)
        btn.setStyleSheet(
            "QToolButton { border: 2px solid #ccc; border-radius: 4px; }"
            "QToolButton:hover { border-color: #5a9; background: #f0fff4; }"
        )
        btn.clicked.connect(lambda _, c=candidate: self._select(c))
        return btn

    def _select(self, candidate) -> None:
        self.selected_candidate = candidate
        self.accept()
