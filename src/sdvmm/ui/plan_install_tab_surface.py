from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QComboBox
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget


class PlanInstallTabSurface(QWidget):
    def __init__(
        self,
        *,
        install_target_combo: QComboBox,
        overwrite_checkbox: QCheckBox,
        install_archive_label: QLabel,
        plan_install_button: QPushButton,
        run_install_button: QPushButton,
    ) -> None:
        super().__init__()
        self.setObjectName("plan_install_tab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("plan_install_scroll_area")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("plan_install_tab_content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(6)

        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        destination_group = QGroupBox("Destination and Safety Context")
        destination_group.setObjectName("plan_install_destination_group")
        destination_group.setFlat(True)
        destination_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        destination_layout = QGridLayout(destination_group)
        destination_layout.setContentsMargins(8, 6, 8, 6)
        destination_layout.setHorizontalSpacing(8)
        destination_layout.setVerticalSpacing(4)
        destination_layout.setColumnStretch(1, 1)
        destination_layout.setColumnStretch(2, 0)
        destination_layout.addWidget(QLabel("Install destination"), 0, 0)
        destination_layout.addWidget(install_target_combo, 0, 1, 1, 2)
        destination_layout.addWidget(QLabel("Replace existing"), 1, 0)
        destination_layout.addWidget(overwrite_checkbox, 1, 1, 1, 2)
        overwrite_help_label = QLabel(
            "Use archive-aware replace when planning into an existing target."
        )
        overwrite_help_label.setObjectName("plan_install_overwrite_help_label")
        overwrite_help_label.setWordWrap(True)
        _set_auxiliary_label_style(overwrite_help_label)
        destination_layout.addWidget(overwrite_help_label, 2, 0, 1, 3)
        destination_layout.addWidget(install_archive_label, 3, 0, 1, 3)
        content_layout.addWidget(destination_group)

        execute_group = QGroupBox("Plan and Execute")
        execute_group.setObjectName("plan_install_execute_group")
        execute_group.setFlat(True)
        execute_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        execute_layout = QVBoxLayout(execute_group)
        execute_layout.setContentsMargins(8, 6, 8, 6)
        execute_layout.setSpacing(5)

        plan_actions = QHBoxLayout()
        plan_actions.setSpacing(6)
        plan_actions.addWidget(plan_install_button)
        plan_actions.addWidget(run_install_button)
        plan_actions.addStretch(1)
        execute_layout.addLayout(plan_actions)

        caution_label = QLabel(
            "No automatic install: review plan details and warnings before running install."
        )
        caution_label.setWordWrap(True)
        _set_auxiliary_label_style(caution_label)
        execute_layout.addWidget(caution_label)

        content_layout.addWidget(execute_group)
        content_layout.addStretch(1)

        self.destination_group = destination_group
        self.execute_group = execute_group
        self.scroll_area = scroll_area
        self.content_widget = content
        self.content_layout = content_layout


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
