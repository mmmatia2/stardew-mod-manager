from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QHBoxLayout
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
        sandbox_launch_status_label: QLabel,
        scan_context_label: QLabel,
        install_context_label: QLabel,
    ) -> None:
        super().__init__("")
        self.setObjectName("top_context_surface_group")
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        for value_label in (
            environment_status_label,
            smapi_update_status_label,
            smapi_log_status_label,
            nexus_status_label,
            watch_status_label,
            operation_state_label,
            sandbox_launch_status_label,
            scan_context_label,
            install_context_label,
        ):
            _prepare_context_value_label(value_label)

        context_layout = QHBoxLayout(self)
        context_layout.setContentsMargins(8, 8, 8, 8)
        context_layout.setSpacing(10)

        brand_panel = QWidget()
        brand_panel.setObjectName("top_context_brand_panel")
        brand_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(12, 10, 12, 10)
        brand_layout.setSpacing(5)

        brand_eyebrow = QLabel("Session context")
        brand_eyebrow.setObjectName("top_context_brand_eyebrow")
        brand_title = QLabel("Live, sandbox, and write destinations")
        brand_title.setObjectName("top_context_brand_title")
        brand_subtitle = QLabel(
            "Check the current scan source and install destination before you compare, review, restore, or write files."
        )
        brand_subtitle.setObjectName("top_context_brand_subtitle")
        brand_subtitle.setWordWrap(True)

        active_context_group = QWidget()
        active_context_group.setObjectName("top_context_active_context_panel")
        active_context_group.setProperty("panelVariant", "inline")
        active_context_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        active_context_container_layout = QVBoxLayout(active_context_group)
        active_context_container_layout.setContentsMargins(0, 2, 0, 0)
        active_context_container_layout.setSpacing(4)
        active_context_container_layout.addWidget(_section_label("Active Context"))
        active_context_layout = QGridLayout()
        active_context_layout.setContentsMargins(0, 0, 0, 0)
        active_context_layout.setHorizontalSpacing(8)
        active_context_layout.setVerticalSpacing(4)
        active_context_layout.addWidget(_context_caption("Scan source"), 0, 0)
        active_context_layout.addWidget(scan_context_label, 0, 1)
        active_context_layout.addWidget(_context_caption("Install destination"), 1, 0)
        active_context_layout.addWidget(install_context_label, 1, 1)
        active_context_layout.setColumnMinimumWidth(0, 104)
        active_context_layout.setColumnStretch(1, 1)
        active_context_container_layout.addLayout(active_context_layout)

        brand_layout.addWidget(brand_eyebrow)
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_subtitle)
        brand_layout.addWidget(active_context_group)
        brand_layout.addStretch(1)

        operations_group = QWidget()
        operations_group.setObjectName("top_context_operational_panel")
        operations_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        operations_container_layout = QVBoxLayout(operations_group)
        operations_container_layout.setContentsMargins(12, 10, 12, 10)
        operations_container_layout.setSpacing(6)
        operations_container_layout.addWidget(_section_label("Operational status"))

        environment_group = QWidget()
        environment_group.setObjectName("top_context_environment_panel")
        environment_group.setProperty("panelVariant", "inline")
        environment_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        environment_container_layout = QVBoxLayout(environment_group)
        environment_container_layout.setContentsMargins(0, 0, 0, 0)
        environment_container_layout.setSpacing(4)
        environment_container_layout.addWidget(_section_label("Environment"))
        environment_layout = QGridLayout()
        environment_layout.setContentsMargins(0, 0, 0, 0)
        environment_layout.setHorizontalSpacing(8)
        environment_layout.setVerticalSpacing(5)
        environment_layout.addWidget(_context_caption("Game"), 0, 0)
        environment_layout.addWidget(environment_status_label, 0, 1)
        environment_layout.addWidget(_context_caption("SMAPI update"), 1, 0)
        environment_layout.addWidget(smapi_update_status_label, 1, 1)
        environment_layout.addWidget(_context_caption("SMAPI log"), 2, 0)
        environment_layout.addWidget(smapi_log_status_label, 2, 1)
        environment_layout.setColumnMinimumWidth(0, 94)
        environment_layout.setColumnStretch(1, 1)
        environment_container_layout.addLayout(environment_layout)

        runtime_group = QWidget()
        runtime_group.setObjectName("top_context_runtime_panel")
        runtime_group.setProperty("panelVariant", "inline")
        runtime_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        runtime_container_layout = QVBoxLayout(runtime_group)
        runtime_container_layout.setContentsMargins(0, 0, 0, 0)
        runtime_container_layout.setSpacing(4)
        runtime_container_layout.addWidget(_section_label("Runtime"))
        runtime_layout = QGridLayout()
        runtime_layout.setContentsMargins(0, 0, 0, 0)
        runtime_layout.setHorizontalSpacing(8)
        runtime_layout.setVerticalSpacing(5)
        runtime_layout.addWidget(_context_caption("Nexus"), 0, 0)
        runtime_layout.addWidget(nexus_status_label, 0, 1)
        runtime_layout.addWidget(_context_caption("Watcher"), 1, 0)
        runtime_layout.addWidget(watch_status_label, 1, 1)
        runtime_layout.addWidget(_context_caption("Operation"), 2, 0)
        runtime_layout.addWidget(operation_state_label, 2, 1)
        runtime_layout.addWidget(_context_caption("Sandbox launch"), 3, 0)
        runtime_layout.addWidget(sandbox_launch_status_label, 3, 1)
        runtime_layout.setColumnMinimumWidth(0, 104)
        runtime_layout.setColumnStretch(1, 1)
        runtime_container_layout.addLayout(runtime_layout)

        operations_columns_layout = QHBoxLayout()
        operations_columns_layout.setContentsMargins(0, 0, 0, 0)
        operations_columns_layout.setSpacing(14)
        operations_columns_layout.addWidget(environment_group, 1)
        operations_columns_layout.addWidget(runtime_group, 1)
        operations_container_layout.addLayout(operations_columns_layout)

        context_layout.addWidget(brand_panel, 11)
        context_layout.addWidget(operations_group, 12)

        self.brand_panel = brand_panel
        self.operations_group = operations_group
        self.environment_group = environment_group
        self.runtime_group = runtime_group
        self.active_context_group = active_context_group


def _context_caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    label.setProperty("contextRole", "caption")
    label.setWordWrap(True)
    _set_auxiliary_label_style(label)
    return label


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("top_context_section_title")
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


def _prepare_context_value_label(label: QLabel) -> None:
    label.setProperty("contextRole", "value")
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
