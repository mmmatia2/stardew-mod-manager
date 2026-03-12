from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QTabWidget
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget


class BottomDetailsRegion(QGroupBox):
    def __init__(
        self,
        *,
        details_toggle: QCheckBox,
        findings_box: QPlainTextEdit,
        setup_scroll: QScrollArea,
    ) -> None:
        super().__init__("Details")
        self.setObjectName("bottom_details_group")
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        summary_tab = QWidget()
        summary_tab.setObjectName("bottom_summary_tab")
        summary_tab_layout = QVBoxLayout(summary_tab)
        summary_tab_layout.setContentsMargins(6, 4, 6, 4)
        summary_tab_layout.setSpacing(4)

        summary_header_label = QLabel("Operational Detail")
        _set_section_label_style(summary_header_label)
        summary_tab_layout.addWidget(summary_header_label)

        summary_help_label = QLabel(
            "Use this tab for the full narrative output of the last operation. The Global Status strip above stays visible for quick status reading."
        )
        summary_help_label.setWordWrap(True)
        _set_auxiliary_label_style(summary_help_label)
        summary_tab_layout.addWidget(summary_help_label)
        summary_tab_layout.addWidget(details_toggle)

        details_group = QGroupBox("Detailed output")
        details_group.setObjectName("bottom_summary_details_group")
        details_group.setFlat(True)
        details_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(6, 4, 6, 4)
        details_layout.addWidget(findings_box)
        details_group.setVisible(False)
        summary_tab_layout.addWidget(details_group, 1)

        tabs = QTabWidget()
        tabs.setObjectName("bottom_details_tabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        summary_tab_index = tabs.addTab(summary_tab, "Summary")
        setup_scroll.setObjectName("bottom_setup_tab")
        setup_tab_index = tabs.addTab(setup_scroll, "Setup")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        layout.addWidget(tabs)

        self.details_group = details_group
        self.tabs = tabs
        self.summary_tab_index = summary_tab_index
        self.setup_tab_index = setup_tab_index


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
