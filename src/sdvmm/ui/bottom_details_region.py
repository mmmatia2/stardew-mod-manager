from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout


class BottomDetailsRegion(QGroupBox):
    def __init__(
        self,
        *,
        details_toggle: QCheckBox,
        findings_box: QPlainTextEdit,
        setup_scroll: QScrollArea,
    ) -> None:
        super().__init__("Operational Detail")
        self.setObjectName("bottom_details_group")
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        detail_header_label = QLabel("Detailed output")
        detail_header_label.setObjectName("bottom_detail_identity_label")
        _set_section_label_style(detail_header_label)
        layout.addWidget(detail_header_label)
        layout.addWidget(details_toggle)

        details_group = QGroupBox("Detailed output")
        details_group.setObjectName("bottom_summary_details_group")
        details_group.setFlat(True)
        details_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(6, 4, 6, 4)
        details_layout.addWidget(findings_box)
        details_group.setVisible(False)
        layout.addWidget(details_group, 1)

        setup_group = QGroupBox("Setup")
        setup_group.setObjectName("bottom_setup_group")
        setup_group.setFlat(True)
        setup_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        setup_layout = QVBoxLayout(setup_group)
        setup_layout.setContentsMargins(6, 4, 6, 4)
        setup_layout.setSpacing(4)
        setup_scroll.setObjectName("bottom_setup_tab")
        setup_layout.addWidget(setup_scroll)
        layout.addWidget(setup_group)

        self.details_group = details_group
        self.setup_group = setup_group


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
