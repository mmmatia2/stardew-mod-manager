from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt


class GlobalStatusStrip(QGroupBox):
    def __init__(self) -> None:
        super().__init__("")
        self.setObjectName("global_status_strip_group")
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.current_status_label = QLabel("Waiting for action.")
        self.current_status_label.setObjectName("global_status_current_label")
        self.current_status_label.setWordWrap(True)
        _set_status_label_style(self.current_status_label)

        self.blocking_issues_label = QLabel("No blocking issues detected.")
        self.blocking_issues_label.setObjectName("global_status_blocking_label")
        self.blocking_issues_label.setWordWrap(True)
        _set_status_label_style(self.blocking_issues_label, bold=True)

        self.next_step_label = QLabel("Run Scan to refresh installed inventory.")
        self.next_step_label.setObjectName("global_status_next_step_label")
        self.next_step_label.setWordWrap(True)
        _set_status_label_style(self.next_step_label, bold=True)

        summary_label = QLabel("Workflow guidance")
        summary_label.setObjectName("global_status_summary_label")
        _set_status_label_style(summary_label, bold=True)
        summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        summary_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        status_strip_layout = QHBoxLayout(self)
        status_strip_layout.setContentsMargins(6, 4, 6, 4)
        status_strip_layout.setSpacing(6)
        status_strip_layout.addWidget(summary_label, 0)
        status_strip_layout.addWidget(
            _build_status_panel("Current status", self.current_status_label),
            1,
        )
        status_strip_layout.addWidget(
            _build_status_panel("Blocking issues", self.blocking_issues_label),
            1,
        )
        status_strip_layout.addWidget(
            _build_status_panel("Recommended next step", self.next_step_label),
            1,
        )


def _build_status_panel(title: str, value_label: QLabel) -> QWidget:
    panel = QWidget()
    panel.setObjectName("global_status_panel")
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.setSpacing(1)
    title_label = QLabel(title)
    title_label.setObjectName("global_status_panel_title")
    _set_status_label_style(title_label, bold=True)
    title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    value_label.setProperty("statusRole", "value")
    value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    value_label.setWordWrap(True)
    value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    return panel


def _set_status_label_style(label: QLabel, *, bold: bool = False) -> None:
    font = QFont(label.font())
    font.setBold(bold)
    label.setFont(font)

    palette = label.palette()
    palette.setColor(QPalette.ColorRole.WindowText, palette.color(QPalette.ColorRole.WindowText))
    label.setPalette(palette)
