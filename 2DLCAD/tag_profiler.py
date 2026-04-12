from __future__ import annotations

from datetime import date
import json
import os

import numpy as np

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import (
    QCheckBox,
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
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calibration_utils import FIT_MODES, build_eval_func
from serial_reader import RawDistanceReaderThread
from tag_profile_utils import DEVICE_HEIGHT_FIELD_MAP
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
QTabWidget::pane {{
    border: 1px solid rgba(102, 121, 164, 0.20);
    border-radius: 14px;
    background-color: rgba(13, 18, 29, 0.72);
    top: -1px;
}}
QTabBar::tab {{
    background-color: rgba(20, 26, 40, 0.82);
    color: #aeb8d8;
    border: 1px solid rgba(102, 121, 164, 0.16);
    padding: 8px 14px;
    margin-right: 6px;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    font-size: 11px;
    font-weight: 700;
}}
QTabBar::tab:selected {{
    background-color: rgba(32, 42, 68, 0.96);
    color: #f4f5ff;
    border-color: rgba(135, 168, 255, 0.36);
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
QProgressBar {{
    background: rgba(11, 15, 24, 0.82);
    border: 1px solid rgba(96, 114, 155, 0.28);
    border-radius: 6px;
    min-height: 8px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    background: rgba(135, 168, 255, 0.78);
    border-radius: 6px;
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
        self._generated_equations: dict[str, str] = {}
        self._lab_points_inputs: dict[str, QPlainTextEdit] = {}
        self._lab_eq_outputs: dict[str, QLineEdit] = {}
        self._lab_fit_combos: dict[str, QComboBox] = {}
        self._lab_auto_checks: dict[str, QCheckBox] = {}
        self._lab_degree_combos: dict[str, QComboBox] = {}
        self._lab_ref_floor_edits: dict[str, QLineEdit] = {}
        self._lab_ref_anchor_height_edits: dict[str, QLineEdit] = {}
        self._lab_ref_locked_labels: dict[str, QLineEdit] = {}
        self._lab_capture_progress: dict[str, QProgressBar] = {}
        self._lab_capture_progress_labels: dict[str, QLabel] = {}
        self._lab_live_reader = None
        self._lab_live_status = None
        self._lab_target_label = None
        self._lab_port_combo = None
        self._lab_connect_btn = None
        self._lab_capture_btn = None
        self._lab_sample_combo = None
        self._lab_tag_height_edit = None
        self._lab_capture_buf: dict[str, list[float]] = {}
        self._lab_capture_true: dict[str, float] = {}
        self._lab_capture_target = 0
        self._lab_capture_tag_id = ""
        self._lab_is_capturing = False
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

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        content_layout.addWidget(self._tabs)

        profile_tab = QWidget(self)
        profile_layout = QVBoxLayout(profile_tab)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(12)

        summary = self._build_summary_card()
        profile_layout.addWidget(summary)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        profile_layout.addLayout(grid)

        self._identity_card = self._build_identity_card()
        self._device_card = self._build_device_card()
        self._calibration_card = self._build_calibration_card()
        self._notes_card = self._build_notes_card()

        grid.addWidget(self._identity_card, 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self._device_card, 0, 1, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self._calibration_card, 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self._notes_card, 1, 1, Qt.AlignmentFlag.AlignTop)
        profile_layout.addStretch(1)

        calibration_tab = self._build_calibration_lab_tab()

        self._tabs.addTab(profile_tab, "Profile")
        self._tabs.addTab(calibration_tab, "Calibration Lab")
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
        if key == "tag_id":
            edit.textChanged.connect(self._sync_calibration_target)
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
        if key == "device_type":
            combo.currentTextChanged.connect(self._sync_profile_height_hint)
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

    def _build_calibration_lab_tab(self) -> QWidget:
        tab = QWidget(self)
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(12)

        intro = QLabel(
            "Build calibration equations from captured raw/reference distance pairs, then push the generated results back into the profile fields.",
            tab,
        )
        intro.setObjectName("summary_copy")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        setup_grid = QGridLayout()
        setup_grid.setContentsMargins(0, 0, 0, 0)
        setup_grid.setHorizontalSpacing(12)
        setup_grid.setVerticalSpacing(12)
        outer.addLayout(setup_grid)

        live_card = SectionCard(
            "Live Capture",
            "Connect to a module, target the current tag, and capture a burst of raw distances just like the original workflow.",
            self,
        )
        live_body = live_card.body_layout

        port_row = QHBoxLayout()
        port_row.setContentsMargins(0, 0, 0, 0)
        port_row.setSpacing(8)
        port_label = QLabel("BLE Module", live_card)
        port_label.setObjectName("field_label")
        self._lab_port_combo = QComboBox(live_card)
        self._lab_port_combo.addItems(self._list_serial_ports())
        self._lab_connect_btn = QPushButton("Connect", live_card)
        self._lab_connect_btn.setObjectName("tag_header_button")
        self._lab_connect_btn.setCheckable(True)
        self._lab_connect_btn.toggled.connect(self._toggle_live_capture_source)
        port_row.addWidget(port_label)
        port_row.addWidget(self._lab_port_combo, 1)
        port_row.addWidget(self._lab_connect_btn)
        live_body.addLayout(port_row)

        target_row = QHBoxLayout()
        target_row.setContentsMargins(0, 0, 0, 0)
        target_row.setSpacing(8)
        target_label = QLabel("Capture Tag", live_card)
        target_label.setObjectName("field_label")
        self._lab_target_label = QLabel("--", live_card)
        self._lab_target_label.setObjectName("summary_copy")
        target_row.addWidget(target_label)
        target_row.addWidget(self._lab_target_label, 1)
        live_body.addLayout(target_row)

        sample_row = QHBoxLayout()
        sample_row.setContentsMargins(0, 0, 0, 0)
        sample_row.setSpacing(8)
        sample_label = QLabel("Sample Count", live_card)
        sample_label.setObjectName("field_label")
        self._lab_sample_combo = QComboBox(live_card)
        self._lab_sample_combo.addItems(["1", "5", "10", "20", "50", "100"])
        self._lab_sample_combo.setCurrentText("20")
        self._lab_capture_btn = QPushButton("Capture", live_card)
        self._lab_capture_btn.setObjectName("tag_header_button")
        self._lab_capture_btn.clicked.connect(self._start_live_capture)
        sample_row.addWidget(sample_label)
        sample_row.addWidget(self._lab_sample_combo, 1)
        sample_row.addWidget(self._lab_capture_btn)
        live_body.addLayout(sample_row)

        for aid in ("A0", "A1", "A2", "A3"):
            prog_row = QHBoxLayout()
            prog_row.setContentsMargins(0, 0, 0, 0)
            prog_row.setSpacing(8)
            dot = QLabel("●", live_card)
            dot.setStyleSheet("color: #9fb4e6; font-size: 11px;")
            dot.setFixedWidth(12)
            aid_lbl = QLabel(aid, live_card)
            aid_lbl.setObjectName("field_label")
            aid_lbl.setFixedWidth(24)
            prog = QProgressBar(live_card)
            prog.setRange(0, 1)
            prog.setValue(0)
            prog.setTextVisible(False)
            prog_lbl = QLabel("0/0", live_card)
            prog_lbl.setObjectName("summary_copy")
            prog_lbl.setFixedWidth(36)
            prog_row.addWidget(dot)
            prog_row.addWidget(aid_lbl)
            prog_row.addWidget(prog, 1)
            prog_row.addWidget(prog_lbl)
            live_body.addLayout(prog_row)
            self._lab_capture_progress[aid] = prog
            self._lab_capture_progress_labels[aid] = prog_lbl

        self._lab_live_status = QLabel("Disconnected. Fill Tag ID in the profile tab, then connect to a module.", live_card)
        self._lab_live_status.setObjectName("summary_copy")
        self._lab_live_status.setWordWrap(True)
        live_body.addWidget(self._lab_live_status)
        setup_grid.addWidget(live_card, 0, 0, Qt.AlignmentFlag.AlignTop)

        reference_card = SectionCard(
            "Reference Distance",
            "Enter the true floor distance X to each anchor and per-anchor testing heights, then calculate the reference slant distance used for capture.",
            self,
        )
        ref_body = reference_card.body_layout
        ref_form = self._make_form()
        for aid in ("A0", "A1", "A2", "A3"):
            floor_edit = QLineEdit(reference_card)
            floor_edit.setPlaceholderText("Floor X")
            anchor_height_edit = QLineEdit(reference_card)
            anchor_height_edit.setPlaceholderText("Anchor Height")
            locked = QLineEdit(reference_card)
            locked.setReadOnly(True)
            locked.setPlaceholderText("---")
            self._lab_ref_floor_edits[aid] = floor_edit
            self._lab_ref_anchor_height_edits[aid] = anchor_height_edit
            self._lab_ref_locked_labels[aid] = locked
            row = QWidget(reference_card)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(floor_edit, 1)
            row_layout.addWidget(anchor_height_edit, 1)
            row_layout.addWidget(locked, 1)
            ref_form.addRow(
                self._make_field_label(
                    f"{aid} X / H / Ref",
                    f"True floor distance X to {aid}, the anchor test height, and the calculated slant reference used for capture.",
                ),
                row,
            )
        self._lab_tag_height_edit = QLineEdit(reference_card)
        self._lab_tag_height_edit.setPlaceholderText("Tag Height")
        ref_form.addRow(
            self._make_field_label(
                "Tag Height (ft)",
                "Tag height from the floor used to compute the vertical difference against each anchor height.",
            ),
            self._lab_tag_height_edit,
        )
        ref_body.addLayout(ref_form)

        ref_actions = QHBoxLayout()
        ref_actions.setContentsMargins(0, 0, 0, 0)
        ref_actions.setSpacing(8)
        use_height_btn = QPushButton("Use Profile Height", reference_card)
        use_height_btn.setObjectName("tag_header_button")
        use_height_btn.clicked.connect(self._use_profile_height_for_reference)
        calc_ref_btn = QPushButton("Calculate Reference", reference_card)
        calc_ref_btn.setObjectName("tag_header_button")
        calc_ref_btn.clicked.connect(self._calculate_reference_distances)
        ref_actions.addWidget(use_height_btn)
        ref_actions.addWidget(calc_ref_btn)
        ref_actions.addStretch(1)
        ref_body.addLayout(ref_actions)
        setup_grid.addWidget(reference_card, 0, 1, Qt.AlignmentFlag.AlignTop)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        outer.addLayout(grid)

        for idx, aid in enumerate(("A0", "A1", "A2", "A3")):
            card = SectionCard(f"{aid} Equation Builder", "Captured bursts are appended here as raw, reference pairs.", self)
            body = card.body_layout

            auto_chk = QCheckBox("Auto-fit best model", card)
            auto_chk.setChecked(True)
            body.addWidget(auto_chk)
            self._lab_auto_checks[aid] = auto_chk

            fit_row = QHBoxLayout()
            fit_row.setContentsMargins(0, 0, 0, 0)
            fit_row.setSpacing(8)
            fit_label = QLabel("Fit Mode", card)
            fit_label.setObjectName("field_label")
            fit_combo = QComboBox(card)
            fit_combo.addItems(FIT_MODES)
            fit_combo.setCurrentText("Polynomial")
            fit_row.addWidget(fit_label)
            fit_row.addWidget(fit_combo, 1)
            body.addLayout(fit_row)
            self._lab_fit_combos[aid] = fit_combo

            degree_row = QHBoxLayout()
            degree_row.setContentsMargins(0, 0, 0, 0)
            degree_row.setSpacing(8)
            degree_label = QLabel("Polynomial Degree", card)
            degree_label.setObjectName("field_label")
            degree_combo = QComboBox(card)
            degree_combo.addItems([str(i) for i in range(1, 11)])
            degree_combo.setCurrentText("4")
            degree_row.addWidget(degree_label)
            degree_row.addWidget(degree_combo, 1)
            body.addLayout(degree_row)
            self._lab_degree_combos[aid] = degree_combo

            points = QPlainTextEdit(card)
            points.setFixedHeight(120)
            points.setPlaceholderText("raw, reference\n11.37, 10.80\n12.12, 11.45")
            body.addWidget(points)
            self._lab_points_inputs[aid] = points

            eq_output = QLineEdit(card)
            eq_output.setReadOnly(True)
            eq_output.setPlaceholderText("Generated equation will appear here")
            body.addWidget(eq_output)
            self._lab_eq_outputs[aid] = eq_output

            auto_chk.toggled.connect(fit_combo.setDisabled)
            auto_chk.toggled.connect(degree_combo.setDisabled)
            fit_combo.setDisabled(auto_chk.isChecked())
            degree_combo.setDisabled(auto_chk.isChecked())

            grid.addWidget(card, idx // 2, idx % 2, Qt.AlignmentFlag.AlignTop)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(10)

        gen_btn = QPushButton("Generate Equations", tab)
        gen_btn.setObjectName("tag_header_button")
        gen_btn.clicked.connect(self._generate_calibration_equations)
        action_row.addWidget(gen_btn)

        apply_btn = QPushButton("Apply To Profile", tab)
        apply_btn.setObjectName("tag_header_button")
        apply_btn.clicked.connect(self._apply_generated_calibration)
        action_row.addWidget(apply_btn)

        action_row.addStretch(1)
        outer.addLayout(action_row)

        self._lab_status = QLabel("No calibration equations generated yet.", tab)
        self._lab_status.setObjectName("summary_copy")
        outer.addWidget(self._lab_status)
        outer.addStretch(1)
        return tab

    def _list_serial_ports(self) -> list[str]:
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        return ports or [""]

    def _sync_calibration_target(self):
        if self._lab_target_label is None:
            return
        target = self._get_text("tag_id") or "--"
        self._lab_target_label.setText(target)

    def _sync_profile_height_hint(self):
        if not self._lab_tag_height_edit or self._lab_tag_height_edit.text().strip():
            return
        self._use_profile_height_for_reference()

    def _use_profile_height_for_reference(self):
        device_type = self._get_text("device_type") or DEVICE_TYPES[0]
        field_key = DEVICE_HEIGHT_FIELD_MAP.get(device_type)
        if not field_key:
            return
        value = self._get_text(field_key)
        if value and self._lab_tag_height_edit is not None:
            self._lab_tag_height_edit.setText(value)

    def _calculate_reference_distances(self):
        y_text = self._lab_tag_height_edit.text().strip() if self._lab_tag_height_edit else ""
        try:
            tag_height = float(y_text)
        except Exception:
            QMessageBox.warning(self, "Missing Tag Height", "Enter the tag height before calculating reference values.")
            return False

        for aid in ("A0", "A1", "A2", "A3"):
            x_text = self._lab_ref_floor_edits[aid].text().strip()
            if not x_text:
                continue
            anchor_height_text = self._lab_ref_anchor_height_edits[aid].text().strip()
            try:
                x_val = float(x_text)
            except Exception:
                QMessageBox.warning(self, "Invalid Distance", f"{aid} floor distance must be numeric.")
                return False
            try:
                anchor_height = float(anchor_height_text)
            except Exception:
                QMessageBox.warning(self, "Invalid Anchor Height", f"{aid} anchor height must be numeric.")
                return False
            slant = float(np.hypot(x_val, abs(anchor_height - tag_height)))
            self._lab_ref_locked_labels[aid].setText(f"{slant:.4f}")
        self._lab_live_status.setText("Reference distances updated. You can capture live raw bursts now.")
        return True

    def _toggle_live_capture_source(self, checked: bool):
        if checked:
            port = self._lab_port_combo.currentText().strip() if self._lab_port_combo else ""
            if not port:
                QMessageBox.warning(self, "No Module Selected", "Select a BLE module port before connecting.")
                self._lab_connect_btn.blockSignals(True)
                self._lab_connect_btn.setChecked(False)
                self._lab_connect_btn.blockSignals(False)
                return
            self._disconnect_live_capture_source()
            reader = RawDistanceReaderThread(port)
            reader.distances_update.connect(self._on_live_distances_update)
            reader.connection_error.connect(self._on_live_capture_error)
            reader.raw_line.connect(self._on_live_capture_line)
            reader.start()
            self._lab_live_reader = reader
            self._lab_connect_btn.setText("Disconnect")
            self._lab_live_status.setText(f"Connected to {port}. Waiting for live distance packets.")
            if self._lab_port_combo:
                self._lab_port_combo.setEnabled(False)
        else:
            self._disconnect_live_capture_source()

    def _disconnect_live_capture_source(self):
        previous_port = self._lab_port_combo.currentText().strip() if self._lab_port_combo is not None else ""
        if self._lab_live_reader is not None:
            self._lab_live_reader.stop()
            self._lab_live_reader = None
        if self._lab_connect_btn is not None:
            self._lab_connect_btn.blockSignals(True)
            self._lab_connect_btn.setChecked(False)
            self._lab_connect_btn.setText("Connect")
            self._lab_connect_btn.blockSignals(False)
        if self._lab_port_combo is not None:
            self._lab_port_combo.setEnabled(True)
            refreshed_ports = self._list_serial_ports()
            self._lab_port_combo.blockSignals(True)
            self._lab_port_combo.clear()
            self._lab_port_combo.addItems(refreshed_ports)
            if previous_port:
                if previous_port not in refreshed_ports:
                    self._lab_port_combo.addItem(previous_port)
                self._lab_port_combo.setCurrentText(previous_port)
            self._lab_port_combo.blockSignals(False)
        self._lab_is_capturing = False
        if self._lab_capture_btn is not None:
            self._lab_capture_btn.setEnabled(True)
            self._lab_capture_btn.setText("Capture")
        if self._lab_live_status is not None:
            self._lab_live_status.setText("Disconnected. Select a module to reconnect or switch BLE sources.")

    def _on_live_capture_error(self, message: str):
        self._disconnect_live_capture_source()
        if self._lab_live_status is not None:
            self._lab_live_status.setText(message)

    def _on_live_capture_line(self, _line: str):
        # Keep this hook in place for future debugging without cluttering the UI.
        return

    def _start_live_capture(self):
        if self._lab_live_reader is None:
            QMessageBox.warning(self, "Not Connected", "Connect to a BLE module before capturing calibration samples.")
            return
        target_tag = self._get_text("tag_id")
        if not target_tag:
            QMessageBox.warning(self, "Missing Tag ID", "Enter the Tag ID in the profile tab before capturing live calibration data.")
            return
        if not self._calculate_reference_distances():
            return
        true_values = {}
        for aid in ("A0", "A1", "A2", "A3"):
            text = self._lab_ref_locked_labels[aid].text().strip()
            try:
                value = float(text)
            except Exception:
                continue
            if value > 0:
                true_values[aid] = value
        if not true_values:
            QMessageBox.warning(self, "No Reference Values", "Enter reference distances first, then calculate them before capturing.")
            return
        try:
            sample_count = int(self._lab_sample_combo.currentText())
        except Exception:
            sample_count = 20

        self._lab_capture_buf = {aid: [] for aid in true_values}
        self._lab_capture_true = true_values
        self._lab_capture_target = sample_count
        self._lab_capture_tag_id = target_tag
        self._lab_is_capturing = True
        self._lab_capture_btn.setEnabled(False)
        self._lab_capture_btn.setText("Capturing...")
        for aid in ("A0", "A1", "A2", "A3"):
            bar = self._lab_capture_progress[aid]
            label = self._lab_capture_progress_labels[aid]
            bar.setRange(0, sample_count)
            bar.setValue(0)
            label.setText(f"0/{sample_count}")
        self._lab_live_status.setText(f"Capturing {sample_count} live samples for {target_tag}...")

    def _on_live_distances_update(self, tag_id: str, distances: dict):
        if not self._lab_is_capturing or tag_id != self._lab_capture_tag_id:
            return

        all_done = True
        for aid in self._lab_capture_true:
            samples = self._lab_capture_buf.setdefault(aid, [])
            if len(samples) < self._lab_capture_target:
                raw = distances.get(aid, -1)
                if raw and raw > 0:
                    samples.append(float(raw))
            count = len(samples)
            self._lab_capture_progress[aid].setValue(count)
            self._lab_capture_progress_labels[aid].setText(f"{count}/{self._lab_capture_target}")
            if count < self._lab_capture_target:
                all_done = False

        if all_done:
            self._finish_live_capture()

    def _finish_live_capture(self):
        self._lab_is_capturing = False
        self._lab_capture_btn.setEnabled(True)
        self._lab_capture_btn.setText("Capture")

        added_pairs = 0
        for aid, samples in self._lab_capture_buf.items():
            if not samples:
                continue
            mean_raw = sum(samples) / len(samples)
            reference = self._lab_capture_true.get(aid)
            if reference is None:
                continue
            text_box = self._lab_points_inputs[aid]
            existing = text_box.toPlainText().strip()
            line = f"{mean_raw:.4f}, {reference:.4f}"
            text_box.setPlainText(f"{existing}\n{line}".strip())
            added_pairs += 1

        if added_pairs:
            self._lab_live_status.setText(
                f"Captured and fused live burst for {self._lab_capture_tag_id}. Added {added_pairs} anchor pair(s)."
            )
            self._generate_calibration_equations()
        else:
            self._lab_live_status.setText("No valid live samples were captured for the selected tag.")

    def _parse_calibration_points(self, text: str):
        points = []
        for line in text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            parts = [part.strip() for part in raw.split(",")]
            if len(parts) != 2:
                raise ValueError(f"Expected 'raw, reference' pairs, got: {raw}")
            points.append((float(parts[0]), float(parts[1])))
        return points

    def _generate_calibration_equations(self):
        generated: dict[str, str] = {}
        try:
            for aid in ("A0", "A1", "A2", "A3"):
                points = self._parse_calibration_points(self._lab_points_inputs[aid].toPlainText())
                if not points:
                    equation = "Raw (no data)"
                elif len(points) == 1:
                    offset = points[0][1] - points[0][0]
                    equation = f"Raw + {offset:.4f}"
                else:
                    X = np.array([p[0] for p in points], dtype=float)
                    Y = np.array([p[1] for p in points], dtype=float)
                    degree = int(self._lab_degree_combos[aid].currentText())
                    if self._lab_auto_checks[aid].isChecked():
                        best_error = float("inf")
                        best_equation = "Raw"
                        for mode in ("Linear", "Polynomial", "Logarithmic", "Power Series", "Exponential"):
                            func, eq = build_eval_func(mode, X, Y, poly_deg=degree)
                            error = sum(abs(func(x) - y) for x, y in points) / len(points)
                            if error < best_error:
                                best_error = error
                                best_equation = f"[Auto:{mode}] {eq}"
                        equation = best_equation
                    else:
                        mode = self._lab_fit_combos[aid].currentText()
                        _, equation = build_eval_func(mode, X, Y, poly_deg=degree)
                self._lab_eq_outputs[aid].setText(equation)
                generated[aid] = equation
        except Exception as exc:
            QMessageBox.warning(self, "Calibration Error", str(exc))
            return

        self._generated_equations = generated
        self._lab_status.setText("Calibration equations generated. Review them, then apply them into the profile.")

    def _apply_generated_calibration(self):
        if not self._generated_equations:
            self._generate_calibration_equations()
            if not self._generated_equations:
                return

        for aid, key in (("A0", "eq_a0"), ("A1", "eq_a1"), ("A2", "eq_a2"), ("A3", "eq_a3")):
            widget = self._fields.get(key)
            if isinstance(widget, QLineEdit):
                widget.setText(self._generated_equations.get(aid, ""))

        date_widget = self._fields.get("last_calibration_date")
        if isinstance(date_widget, QLineEdit):
            date_widget.setText(date.today().isoformat())

        self._tabs.setCurrentIndex(0)
        self._lab_status.setText("Applied generated equations into the profile calibration section.")

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
        self._disconnect_live_capture_source()
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
        self._generated_equations.clear()
        for aid in ("A0", "A1", "A2", "A3"):
            if aid in self._lab_points_inputs:
                self._lab_points_inputs[aid].setPlainText("")
            if aid in self._lab_eq_outputs:
                self._lab_eq_outputs[aid].clear()
            if aid in self._lab_ref_floor_edits:
                self._lab_ref_floor_edits[aid].clear()
            if aid in self._lab_ref_anchor_height_edits:
                self._lab_ref_anchor_height_edits[aid].clear()
            if aid in self._lab_ref_locked_labels:
                self._lab_ref_locked_labels[aid].clear()
            if aid in self._lab_capture_progress:
                self._lab_capture_progress[aid].setRange(0, 1)
                self._lab_capture_progress[aid].setValue(0)
            if aid in self._lab_capture_progress_labels:
                self._lab_capture_progress_labels[aid].setText("0/0")
        if self._lab_tag_height_edit is not None:
            self._lab_tag_height_edit.clear()
        if self._lab_live_status is not None:
            self._lab_live_status.setText("Disconnected. Fill Tag ID in the profile tab, then connect to a module.")
        if hasattr(self, "_lab_status") and self._lab_status is not None:
            self._lab_status.setText("No calibration equations generated yet.")
        self._update_summary()
        self._sync_calibration_target()
        self._sync_profile_height_hint()

    def closeEvent(self, event):
        self._disconnect_live_capture_source()
        super().closeEvent(event)

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
