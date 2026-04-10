from __future__ import annotations

import json
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from utils.font_utils import get_default_font_family


DEVICE_TYPES = ["Wrist Band", "Arm Band", "Belt Clip-on", "Breast Pocket"]
TAG_PROFILE_DIR = os.path.join(os.path.dirname(__file__), "tag_profiles")
FIELD_HELP = {
    "profile_id": "Internal profile identifier used to save, search, and reference this tag record.",
    "name": "Human-readable name assigned to the person or profile.",
    "tag_id": "Physical RTLS tag identifier assigned to the device.",
    "identity_description": "Optional identifying notes that help distinguish this record from similar profiles.",
    "mac_address": "Hardware MAC address for the RTLS device, if known.",
    "device_type": "Where the tag is normally worn or mounted on the body.",
    "wrist_to_floor_ft": "Measured wrist height from the floor for a wrist-mounted device.",
    "arm_to_floor_ft": "Measured arm height from the floor for an arm-mounted device.",
    "hip_to_floor_ft": "Measured hip height from the floor for a belt or waist-mounted device.",
    "breast_to_floor_ft": "Measured chest height from the floor for a breast-pocket device.",
    "device_description": "Optional notes about placement habits, hardware fit, or device-specific details.",
    "eq_a0": "Calibration equation or correction value associated with anchor A0.",
    "eq_a1": "Calibration equation or correction value associated with anchor A1.",
    "eq_a2": "Calibration equation or correction value associated with anchor A2.",
    "eq_a3": "Calibration equation or correction value associated with anchor A3.",
    "last_calibration_date": "Date this profile or its correction values were last calibrated.",
    "notes": "General operational notes that do not fit into the other sections.",
}
TAG_PROFILER_STYLE = f"""
QWidget#tag_profiler_root {{
    background-color: #12121f;
    color: #e0e0f0;
    font-family: "{get_default_font_family()}";
}}
QFrame#tag_profiler_header {{
    background-color: #171726;
    border-bottom: 1px solid #2d2d5e;
}}
QPushButton#tag_header_button {{
    background-color: rgba(45, 45, 94, 0.95);
    color: #f2f4ff;
    border: 1px solid rgba(114, 135, 198, 0.25);
    border-radius: 9px;
    padding: 9px 14px;
    font-size: 12px;
    font-weight: 700;
}}
QPushButton#tag_header_button:hover {{
    background-color: rgba(58, 58, 122, 0.98);
    border-color: rgba(145, 170, 255, 0.42);
}}
QPushButton#tag_header_button:pressed {{
    background-color: rgba(34, 34, 72, 0.98);
}}
QLabel#tag_profiler_title {{
    color: #f4f5ff;
    font-size: 18px;
    font-weight: 700;
}}
QLabel#tag_profiler_subtitle {{
    color: #9aa5c6;
    font-size: 12px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QWidget#tag_profiler_content {{
    background: transparent;
}}
QFrame#section_card {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(22, 30, 48, 242),
        stop:1 rgba(18, 25, 41, 236)
    );
    border: 1px solid rgba(107, 129, 177, 0.22);
    border-radius: 16px;
}}
QLabel#section_title {{
    color: #f4f5ff;
    font-size: 13px;
    font-weight: 700;
}}
QLabel#section_subtitle {{
    color: #8f99bb;
    font-size: 10px;
}}
QLabel#field_label {{
    color: #cfd6f3;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#help_icon {{
    color: #9fb4e6;
    background-color: rgba(36, 50, 81, 0.95);
    border: 1px solid rgba(120, 146, 194, 0.34);
    border-radius: 7px;
    font-size: 10px;
    font-weight: 700;
    min-width: 14px;
    max-width: 14px;
    min-height: 14px;
    max-height: 14px;
    padding: 0px;
}}
QLineEdit, QComboBox, QPlainTextEdit {{
    background-color: rgba(11, 15, 24, 0.82);
    color: #eef2ff;
    border: 1px solid rgba(96, 114, 155, 0.28);
    border-radius: 9px;
    padding: 7px 9px;
    selection-background-color: #3a4d80;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: rgba(135, 168, 255, 0.52);
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    width: 10px;
    height: 10px;
}}
QPlainTextEdit {{
    min-height: 78px;
}}
QToolTip {{
    background-color: rgba(16, 22, 35, 245);
    color: #eef2ff;
    border: 1px solid rgba(120, 146, 194, 0.40);
    border-radius: 8px;
    padding: 6px 8px;
}}
QFrame#summary_card {{
    background-color: rgba(14, 19, 30, 0.96);
    border: 1px solid rgba(102, 121, 164, 0.20);
    border-radius: 16px;
}}
QLabel#summary_eyebrow {{
    color: #8f99bb;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel#summary_value {{
    color: #f4f5ff;
    font-size: 18px;
    font-weight: 700;
}}
QLabel#summary_copy {{
    color: #a8b2d2;
    font-size: 12px;
}}
"""


def _empty_profile() -> dict:
    return {
        "tag_id": "",
        "identity": {
            "profile_id": "",
            "name": "",
            "description": "",
        },
        "device": {
            "mac_address": "",
            "device_type": DEVICE_TYPES[0],
            "wrist_to_floor_ft": "",
            "arm_to_floor_ft": "",
            "hip_to_floor_ft": "",
            "breast_to_floor_ft": "",
            "description": "",
        },
        "calibration": {
            "equations": {
                "A0": "",
                "A1": "",
                "A2": "",
                "A3": "",
            },
            "last_calibration_date": "",
        },
        "notes": "",
    }


class SectionCard(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("section_card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(0)

        title_lbl = QLabel(title, self)
        title_lbl.setObjectName("section_title")
        outer.addWidget(title_lbl)

        subtitle_lbl = QLabel(subtitle, self)
        subtitle_lbl.setObjectName("section_subtitle")
        subtitle_lbl.setWordWrap(False)
        subtitle_lbl.setFixedHeight(16)
        outer.addSpacing(2)
        outer.addWidget(subtitle_lbl)
        outer.addSpacing(8)

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        outer.addLayout(self.body_layout)
        outer.addStretch(1)


class HoverHelpIcon(QLabel):
    def __init__(self, help_text: str = "", parent=None):
        super().__init__("i", parent)
        self._help_text = help_text.strip()
        self.setObjectName("help_icon")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        if self._help_text:
            self.setToolTip(self._help_text)
            self.setCursor(Qt.CursorShape.WhatsThisCursor)

    def enterEvent(self, event):
        if self._help_text:
            QToolTip.showText(
                self.mapToGlobal(self.rect().bottomLeft()),
                self._help_text,
                self,
                self.rect(),
                8000,
            )
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        if self._help_text:
            QToolTip.showText(
                self.mapToGlobal(event.position().toPoint()) + self.rect().bottomLeft() - self.rect().topLeft(),
                self._help_text,
                self,
                self.rect(),
                8000,
            )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def event(self, event):
        if event.type() == event.Type.ToolTip and self._help_text:
            help_event = event if isinstance(event, QHelpEvent) else None
            if help_event is not None:
                QToolTip.showText(help_event.globalPos(), self._help_text, self, self.rect(), 8000)
            return True
        return super().event(event)


class FieldLabelWidget(QWidget):
    def __init__(self, text: str, help_text: str = "", width: int = 132, parent=None):
        super().__init__(parent)
        self.setFixedWidth(width)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(text, self)
        label.setObjectName("field_label")
        layout.addWidget(label, 1)

        if help_text:
            layout.addWidget(HoverHelpIcon(help_text, self), 0, Qt.AlignmentFlag.AlignTop)
        else:
            spacer = QWidget(self)
            spacer.setFixedWidth(14)
            spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(spacer, 0, Qt.AlignmentFlag.AlignTop)


class TagProfilerWorkspace(QWidget):
    go_home = pyqtSignal()
    LABEL_WIDTH = 132

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tag_profiler_root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(TAG_PROFILER_STYLE)

        self._fields: dict[str, QWidget] = {}
        self._build_ui()
        self.reset_form()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("tag_profiler_header")
        header.setFixedHeight(64)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(12)

        btn_home = QPushButton("🏠 Home", header)
        btn_home.setObjectName("tag_header_button")
        btn_home.clicked.connect(self.go_home.emit)
        header_layout.addWidget(btn_home)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title = QLabel("Tag Profiler", header)
        title.setObjectName("tag_profiler_title")
        subtitle = QLabel("Create a clean tag profile and export it as JSON for downstream RTLS workflows.", header)
        subtitle.setObjectName("tag_profiler_subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)
        header_layout.addStretch(1)

        btn_clear = QPushButton("New Profile", header)
        btn_clear.setObjectName("tag_header_button")
        btn_clear.clicked.connect(self.reset_form)
        header_layout.addWidget(btn_clear)

        btn_export = QPushButton("Export JSON", header)
        btn_export.setObjectName("tag_header_button")
        btn_export.clicked.connect(self.export_json)
        header_layout.addWidget(btn_export)

        outer.addWidget(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("tag_profiler_content")
        scroll.setWidget(content)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 20)
        content_layout.setSpacing(12)

        summary = self._build_summary_card()
        content_layout.addWidget(summary)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        content_layout.addLayout(grid)

        self._identity_card = self._build_identity_card()
        self._device_card = self._build_device_card()
        self._calibration_card = self._build_calibration_card()
        self._notes_card = self._build_notes_card()

        grid.addWidget(self._identity_card, 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self._device_card, 0, 1, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self._calibration_card, 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self._notes_card, 1, 1, Qt.AlignmentFlag.AlignTop)

        content_layout.addStretch(1)
        self._sync_card_heights()

    def _build_summary_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("summary_card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(18)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(4)

        eyebrow = QLabel("PROFILE OVERVIEW", card)
        eyebrow.setObjectName("summary_eyebrow")
        left.addWidget(eyebrow)

        value = QLabel("Tag profile export", card)
        value.setObjectName("summary_value")
        left.addWidget(value)

        copy = QLabel(
            "Fill out the profile once, then export a reusable JSON payload for device setup, lookup, or operational records.",
            card,
        )
        copy.setObjectName("summary_copy")
        copy.setWordWrap(True)
        left.addWidget(copy)
        layout.addLayout(left, 1)

        stats = QVBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(2)

        self._summary_tag = QLabel("Tag ID: --", card)
        self._summary_tag.setObjectName("summary_copy")
        self._summary_name = QLabel("Name: --", card)
        self._summary_name.setObjectName("summary_copy")
        stats.addWidget(self._summary_tag)
        stats.addWidget(self._summary_name)
        layout.addLayout(stats)

        return card

    def _make_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return form

    def _make_field_label(self, label: str, help_text: str = "") -> QWidget:
        return FieldLabelWidget(label, help_text, self.LABEL_WIDTH, self)

    def _add_line(self, form: QFormLayout, key: str, label: str):
        edit = QLineEdit(self)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fields[key] = edit
        help_text = FIELD_HELP.get(key, "")
        lbl = self._make_field_label(label, help_text)
        form.addRow(lbl, edit)
        edit.textChanged.connect(self._update_summary)
        return edit

    def _add_combo(self, form: QFormLayout, key: str, label: str, items: list[str]):
        combo = QComboBox(self)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.addItems(items)
        self._fields[key] = combo
        help_text = FIELD_HELP.get(key, "")
        lbl = self._make_field_label(label, help_text)
        form.addRow(lbl, combo)
        combo.currentTextChanged.connect(self._update_summary)
        return combo

    def _add_text(self, form: QFormLayout, key: str, label: str, height: int = 90):
        text = QPlainTextEdit(self)
        text.setFixedHeight(height)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fields[key] = text
        help_text = FIELD_HELP.get(key, "")
        lbl = self._make_field_label(label, help_text)
        form.addRow(lbl, text)
        text.textChanged.connect(self._update_summary)
        return text

    def _build_identity_card(self) -> QFrame:
        card = SectionCard("Identity", "Core identifying details for the assigned tag.", self)
        form = self._make_form()
        self._add_line(form, "profile_id", "Profile ID")
        self._add_line(form, "name", "Name")
        self._add_line(form, "tag_id", "Tag ID")
        self._add_text(form, "identity_description", "Description", 116)
        card.body_layout.addLayout(form)
        return card

    def _build_device_card(self) -> QFrame:
        card = SectionCard("Device", "Hardware details and common mounting measurements.", self)
        form = self._make_form()
        self._add_line(form, "mac_address", "Device MAC")
        self._add_combo(form, "device_type", "Device Type", DEVICE_TYPES)
        self._add_line(form, "wrist_to_floor_ft", "Wrist-to-floor (ft)")
        self._add_line(form, "arm_to_floor_ft", "Arm-to-floor (ft)")
        self._add_line(form, "hip_to_floor_ft", "Hip-to-floor (ft)")
        self._add_line(form, "breast_to_floor_ft", "Breast-to-floor (ft)")
        self._add_text(form, "device_description", "Description", 82)
        card.body_layout.addLayout(form)
        return card

    def _build_calibration_card(self) -> QFrame:
        card = SectionCard("Calibration", "Per-anchor correction equations and calibration date.", self)
        form = self._make_form()
        self._add_line(form, "eq_a0", "Calibration Equation - A0")
        self._add_line(form, "eq_a1", "Calibration Equation - A1")
        self._add_line(form, "eq_a2", "Calibration Equation - A2")
        self._add_line(form, "eq_a3", "Calibration Equation - A3")
        self._add_line(form, "last_calibration_date", "Last Calibration Date")
        card.body_layout.addLayout(form)
        return card

    def _build_notes_card(self) -> QFrame:
        card = SectionCard("Notes", "", self)
        text = QPlainTextEdit(self)
        text.setFixedHeight(150)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fields["notes"] = text
        text.textChanged.connect(self._update_summary)
        card.body_layout.addWidget(text)
        return card

    def _sync_card_heights(self):
        self.layout().activate()
        row_one_height = max(self._identity_card.sizeHint().height(), self._device_card.sizeHint().height())
        row_two_height = max(self._calibration_card.sizeHint().height(), self._notes_card.sizeHint().height())
        self._identity_card.setFixedHeight(row_one_height)
        self._device_card.setFixedHeight(row_one_height)
        self._calibration_card.setFixedHeight(row_two_height)
        self._notes_card.setFixedHeight(row_two_height)

    def _get_text(self, key: str) -> str:
        widget = self._fields[key]
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        return ""

    def build_profile(self) -> dict:
        payload = _empty_profile()
        payload["tag_id"] = self._get_text("tag_id")
        payload["identity"]["profile_id"] = self._get_text("profile_id")
        payload["identity"]["name"] = self._get_text("name")
        payload["identity"]["description"] = self._get_text("identity_description")
        payload["device"]["mac_address"] = self._get_text("mac_address")
        payload["device"]["device_type"] = self._get_text("device_type") or DEVICE_TYPES[0]
        payload["device"]["wrist_to_floor_ft"] = self._get_text("wrist_to_floor_ft")
        payload["device"]["arm_to_floor_ft"] = self._get_text("arm_to_floor_ft")
        payload["device"]["hip_to_floor_ft"] = self._get_text("hip_to_floor_ft")
        payload["device"]["breast_to_floor_ft"] = self._get_text("breast_to_floor_ft")
        payload["device"]["description"] = self._get_text("device_description")
        payload["calibration"]["equations"]["A0"] = self._get_text("eq_a0")
        payload["calibration"]["equations"]["A1"] = self._get_text("eq_a1")
        payload["calibration"]["equations"]["A2"] = self._get_text("eq_a2")
        payload["calibration"]["equations"]["A3"] = self._get_text("eq_a3")
        payload["calibration"]["last_calibration_date"] = self._get_text("last_calibration_date")
        payload["notes"] = self._get_text("notes")
        return payload

    def reset_form(self):
        payload = _empty_profile()
        for key, widget in self._fields.items():
            value = {
                "tag_id": payload["tag_id"],
                "profile_id": payload["identity"]["profile_id"],
                "name": payload["identity"]["name"],
                "identity_description": payload["identity"]["description"],
                "mac_address": payload["device"]["mac_address"],
                "device_type": payload["device"]["device_type"],
                "wrist_to_floor_ft": payload["device"]["wrist_to_floor_ft"],
                "arm_to_floor_ft": payload["device"]["arm_to_floor_ft"],
                "hip_to_floor_ft": payload["device"]["hip_to_floor_ft"],
                "breast_to_floor_ft": payload["device"]["breast_to_floor_ft"],
                "device_description": payload["device"]["description"],
                "eq_a0": payload["calibration"]["equations"]["A0"],
                "eq_a1": payload["calibration"]["equations"]["A1"],
                "eq_a2": payload["calibration"]["equations"]["A2"],
                "eq_a3": payload["calibration"]["equations"]["A3"],
                "last_calibration_date": payload["calibration"]["last_calibration_date"],
                "notes": payload["notes"],
            }[key]
            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(value)
        self._update_summary()

    def _update_summary(self):
        tag = self._get_text("tag_id") or "--"
        name = self._get_text("name") or "--"
        self._summary_tag.setText(f"Tag ID: {tag}")
        self._summary_name.setText(f"Name: {name}")

    def export_json(self):
        payload = self.build_profile()
        default_stem = payload["identity"]["profile_id"] or payload["identity"]["name"] or payload["tag_id"] or "tag_profile"
        safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in default_stem).strip("_") or "tag_profile"
        os.makedirs(TAG_PROFILE_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Tag Profile",
            os.path.join(TAG_PROFILE_DIR, f"{safe_stem}.json"),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=4)
        except Exception as exc:
            QMessageBox.warning(self, "Export Error", f"Could not export tag profile:\n{exc}")
            return
        QMessageBox.information(self, "Export Complete", f"Tag profile saved to:\n{path}")
