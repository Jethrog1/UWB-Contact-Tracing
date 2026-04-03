from __future__ import annotations

from PyQt6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, QParallelAnimationGroup, QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QPushButton, QToolButton, QVBoxLayout, QWidget


class WorkspaceSwitcher(QWidget):
    workspace_requested = pyqtSignal(str)

    def __init__(
        self,
        host: QWidget,
        items: list[tuple[str, str]],
        current_key: str,
        top_offset: int = 0,
        panel_width: int = 196,
        parent=None,
    ):
        super().__init__(parent or host)
        self._host = host
        self._items = items
        self._current_key = current_key
        self._top_offset = top_offset
        self._panel_width = panel_width
        self._button_width = 22
        self._button_height = 76
        self._item_height = 40
        self._panel_margin = 10
        self._panel_spacing = 8
        self._button_y = 0
        self._expanded = False
        self._anim_group = QParallelAnimationGroup(self)
        self._panel_anim = QPropertyAnimation(self._panel if hasattr(self, "_panel") else self, b"geometry", self)
        self._button_anim = QPropertyAnimation(self._toggle_btn if hasattr(self, "_toggle_btn") else self, b"geometry", self)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("workspace_switcher")
        self.setStyleSheet(
            """
            QWidget#workspace_switcher {
                background: transparent;
            }
            QToolButton#workspace_toggle {
                background-color: rgba(32, 37, 60, 245);
                color: #eef2ff;
                border: 1px solid rgba(122, 146, 198, 0.30);
                border-top-right-radius: 11px;
                border-bottom-right-radius: 11px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                font-size: 14px;
                font-weight: 700;
                padding: 0px;
            }
            QToolButton#workspace_toggle:hover {
                background-color: rgba(42, 49, 78, 250);
                border-color: rgba(135, 168, 255, 0.55);
            }
            QToolButton#workspace_toggle:pressed {
                background-color: rgba(24, 29, 45, 250);
            }
            QFrame#workspace_panel {
                background-color: rgba(18, 23, 37, 245);
                border: 1px solid rgba(103, 127, 173, 0.26);
                border-top-right-radius: 14px;
                border-bottom-right-radius: 14px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
            }
            QPushButton#workspace_item {
                background: transparent;
                color: #eef2ff;
                border: 1px solid transparent;
                border-radius: 10px;
                text-align: left;
                padding: 10px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#workspace_item:hover {
                background-color: rgba(42, 49, 78, 250);
                border-color: rgba(135, 168, 255, 0.35);
            }
            QPushButton#workspace_item[current="true"] {
                background-color: rgba(61, 78, 120, 230);
                color: #ffffff;
                border-color: rgba(150, 180, 255, 0.45);
            }
            """
        )

        self._toggle_btn = QToolButton(self)
        self._toggle_btn.setObjectName("workspace_toggle")
        self._toggle_btn.setText("▶")
        self._toggle_btn.clicked.connect(self.toggle)

        self._panel = QFrame(self)
        self._panel.setObjectName("workspace_panel")
        self._panel_layout = QVBoxLayout(self._panel)
        self._panel_layout.setContentsMargins(
            self._panel_margin,
            self._panel_margin,
            self._panel_margin,
            self._panel_margin,
        )
        self._panel_layout.setSpacing(self._panel_spacing)

        self._buttons: dict[str, QPushButton] = {}
        for key, label in items:
            btn = QPushButton(label, self._panel)
            btn.setObjectName("workspace_item")
            btn.setFixedHeight(self._item_height)
            btn.clicked.connect(lambda _checked=False, k=key: self._select_workspace(k))
            self._panel_layout.addWidget(btn)
            self._buttons[key] = btn

        self._host.installEventFilter(self)
        self._panel_anim.setTargetObject(self._panel)
        self._panel_anim.setPropertyName(b"geometry")
        self._panel_anim.setDuration(220)
        self._panel_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._button_anim.setTargetObject(self._toggle_btn)
        self._button_anim.setPropertyName(b"geometry")
        self._button_anim.setDuration(220)
        self._button_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_group.addAnimation(self._panel_anim)
        self._anim_group.addAnimation(self._button_anim)
        self._refresh_current_state()
        self._update_geometry()
        self.show()
        self.raise_()

    def set_current_workspace(self, key: str):
        self._current_key = key
        self._refresh_current_state()

    def set_top_offset(self, top_offset: int):
        self._top_offset = top_offset
        self._update_geometry()

    def toggle(self):
        self._expanded = not self._expanded
        self._toggle_btn.setText("◀" if self._expanded else "▶")
        self._animate_state(self._expanded)

    def close_panel(self):
        if not self._expanded:
            return
        self._expanded = False
        self._toggle_btn.setText("▶")
        self._animate_state(False)

    def eventFilter(self, obj, event):
        if obj is self._host and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._update_geometry()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._button_y = max(0, (self.height() - self._button_height) // 2)
        panel_width = self._panel.width() if self._expanded else self._panel.width()
        button_x = panel_width
        self._toggle_btn.setGeometry(button_x, self._button_y, self._button_width, self._button_height)
        self._panel.setGeometry(0, 0, panel_width, self.height())

    def _select_workspace(self, key: str):
        self.workspace_requested.emit(key)
        self.close_panel()

    def _refresh_current_state(self):
        for key, btn in self._buttons.items():
            is_current = key == self._current_key
            btn.setProperty("current", "true" if is_current else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setEnabled(not is_current)

    def _target_geometry(self, expanded: bool) -> QRect:
        width = self._panel_width + self._button_width
        height = (
            (self._panel_margin * 2)
            + (len(self._items) * self._item_height)
            + (max(0, len(self._items) - 1) * self._panel_spacing)
        )
        available_height = max(0, self._host.height() - self._top_offset)
        y = self._top_offset + max(0, (available_height - height) // 2)
        return QRect(0, y, width, height)

    def _update_geometry(self):
        self.setGeometry(self._target_geometry(self._expanded))
        panel_width = self._panel_width if self._expanded else 0
        self._panel.setGeometry(0, 0, panel_width, self.height())
        self._toggle_btn.setGeometry(
            panel_width,
            self._button_y,
            self._button_width,
            self._button_height,
        )
        self.raise_()

    def _animate_state(self, expanded: bool):
        self._anim_group.stop()
        start_panel_width = self._panel.width()
        end_panel_width = self._panel_width if expanded else 0
        self._panel_anim.setStartValue(QRect(0, 0, start_panel_width, self.height()))
        self._panel_anim.setEndValue(QRect(0, 0, end_panel_width, self.height()))
        self._button_anim.setStartValue(self._toggle_btn.geometry())
        self._button_anim.setEndValue(QRect(end_panel_width, self._button_y, self._button_width, self._button_height))
        self._anim_group.start()
