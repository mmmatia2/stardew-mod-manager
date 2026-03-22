from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout


class BottomDetailsRegion(QGroupBox):
    def __init__(
        self,
        *,
        findings_box: QPlainTextEdit,
    ) -> None:
        super().__init__("Current detail")
        self.setObjectName("bottom_details_group")
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        detail_header_label = QLabel("Latest workflow detail")
        detail_header_label.setObjectName("bottom_detail_identity_label")
        _set_section_label_style(detail_header_label)
        layout.addWidget(detail_header_label)

        detail_help_label = QLabel(
            "Read-only detail from the latest scan, compare, install, backup, or restore step."
        )
        detail_help_label.setObjectName("bottom_detail_help_label")
        detail_help_label.setWordWrap(True)
        _set_auxiliary_label_style(detail_help_label)
        layout.addWidget(detail_help_label)

        details_group = QGroupBox("Latest result")
        details_group.setObjectName("bottom_summary_details_group")
        details_group.setFlat(True)
        details_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(6, 4, 6, 4)
        details_layout.addWidget(findings_box)
        layout.addWidget(details_group, 1)

        self.details_group = details_group


def _set_label_font_weight(label: QLabel, *, bold: bool = False) -> None:
    font = QFont(label.font())
    font.setBold(bold)
    label.setFont(font)


def _apply_label_palette_role(label: QLabel, role: QPalette.ColorRole) -> None:
    palette = label.palette()
    palette.setColor(QPalette.ColorRole.WindowText, palette.color(role))
    label.setPalette(palette)


def _set_auxiliary_label_style(label: QLabel, *, bold: bool = False) -> None:
    _set_label_font_weight(label, bold=bold)
    _apply_label_palette_role(label, QPalette.ColorRole.WindowText)


def _set_section_label_style(label: QLabel) -> None:
    _set_label_font_weight(label, bold=True)
    _apply_label_palette_role(label, QPalette.ColorRole.WindowText)
