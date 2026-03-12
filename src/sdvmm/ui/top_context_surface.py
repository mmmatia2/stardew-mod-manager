from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget


class TopContextSurface(QGroupBox):
    def __init__(
        self,
        *,
        environment_status_label: QLabel,
        smapi_update_status_label: QLabel,
        smapi_log_status_label: QLabel,
        nexus_status_label: QLabel,
        watch_status_label: QLabel,
        operation_state_label: QLabel,
        scan_context_label: QLabel,
        install_context_label: QLabel,
    ) -> None:
        super().__init__("Context")
        self.setObjectName("top_context_surface_group")
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        context_layout = QGridLayout(self)
        context_layout.setContentsMargins(6, 3, 6, 3)
        context_layout.setHorizontalSpacing(10)
        context_layout.setVerticalSpacing(2)

        environment_group = QWidget()
        environment_group.setObjectName("top_context_environment_panel")
        environment_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        environment_container_layout = QVBoxLayout(environment_group)
        environment_container_layout.setContentsMargins(4, 2, 4, 2)
        environment_container_layout.setSpacing(2)
        environment_container_layout.addWidget(_section_label("Environment"))
        environment_layout = QGridLayout()
        environment_layout.setContentsMargins(0, 0, 0, 0)
        environment_layout.setHorizontalSpacing(8)
        environment_layout.setVerticalSpacing(2)
        environment_layout.addWidget(_context_caption("Game"), 0, 0)
        environment_layout.addWidget(environment_status_label, 0, 1)
        environment_layout.addWidget(_context_caption("SMAPI update"), 1, 0)
        environment_layout.addWidget(smapi_update_status_label, 1, 1)
        environment_layout.addWidget(_context_caption("SMAPI log"), 2, 0)
        environment_layout.addWidget(smapi_log_status_label, 2, 1)
        environment_layout.setColumnStretch(1, 1)
        environment_container_layout.addLayout(environment_layout)

        runtime_group = QWidget()
        runtime_group.setObjectName("top_context_runtime_panel")
        runtime_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        runtime_container_layout = QVBoxLayout(runtime_group)
        runtime_container_layout.setContentsMargins(4, 2, 4, 2)
        runtime_container_layout.setSpacing(2)
        runtime_container_layout.addWidget(_section_label("Runtime"))
        runtime_layout = QGridLayout()
        runtime_layout.setContentsMargins(0, 0, 0, 0)
        runtime_layout.setHorizontalSpacing(8)
        runtime_layout.setVerticalSpacing(2)
        runtime_layout.addWidget(_context_caption("Nexus"), 0, 0)
        runtime_layout.addWidget(nexus_status_label, 0, 1)
        runtime_layout.addWidget(_context_caption("Watcher"), 1, 0)
        runtime_layout.addWidget(watch_status_label, 1, 1)
        runtime_layout.addWidget(_context_caption("Operation"), 2, 0)
        runtime_layout.addWidget(operation_state_label, 2, 1)
        runtime_layout.setColumnStretch(1, 1)
        runtime_container_layout.addLayout(runtime_layout)

        active_context_group = QWidget()
        active_context_group.setObjectName("top_context_active_context_panel")
        active_context_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        active_context_container_layout = QVBoxLayout(active_context_group)
        active_context_container_layout.setContentsMargins(4, 2, 4, 2)
        active_context_container_layout.setSpacing(2)
        active_context_container_layout.addWidget(_section_label("Active Context"))
        active_context_layout = QGridLayout()
        active_context_layout.setContentsMargins(0, 0, 0, 0)
        active_context_layout.setHorizontalSpacing(8)
        active_context_layout.setVerticalSpacing(2)
        active_context_layout.addWidget(_context_caption("Scan source"), 0, 0)
        active_context_layout.addWidget(scan_context_label, 0, 1)
        active_context_layout.addWidget(_context_caption("Install destination"), 1, 0)
        active_context_layout.addWidget(install_context_label, 1, 1)
        active_context_layout.setColumnStretch(1, 1)
        active_context_container_layout.addLayout(active_context_layout)

        context_layout.addWidget(environment_group, 0, 0)
        context_layout.addWidget(runtime_group, 0, 1)
        context_layout.addWidget(active_context_group, 0, 2)
        context_layout.setColumnStretch(0, 1)
        context_layout.setColumnStretch(1, 1)
        context_layout.setColumnStretch(2, 2)


def _context_caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    _set_auxiliary_label_style(label)
    return label


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    _set_section_label_style(label)
    return label


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
