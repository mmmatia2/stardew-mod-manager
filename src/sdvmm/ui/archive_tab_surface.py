from __future__ import annotations

from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QTableWidget
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget


class ArchiveTabSurface(QWidget):
    def __init__(
        self,
        *,
        archive_filter_input: QLineEdit,
        archive_filter_stats_label: QLabel,
        archive_table: QTableWidget,
        refresh_archives_button: QPushButton,
        restore_archived_button: QPushButton,
        delete_archived_button: QPushButton,
    ) -> None:
        super().__init__()
        self.setObjectName("archive_tab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        archive_controls_group = QGroupBox("Archive Browser")
        archive_controls_group.setObjectName("archive_controls_group")
        archive_controls_group.setFlat(True)
        archive_controls_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        archive_controls_layout = QVBoxLayout(archive_controls_group)
        archive_controls_layout.setContentsMargins(10, 10, 10, 10)
        archive_controls_layout.setSpacing(8)

        archive_filter_row = QWidget()
        archive_filter_row.setObjectName("archive_filter_row")
        archive_filter_row_layout = QGridLayout(archive_filter_row)
        archive_filter_row_layout.setContentsMargins(0, 0, 0, 0)
        archive_filter_row_layout.setHorizontalSpacing(10)
        archive_filter_row_layout.setVerticalSpacing(4)
        archive_filter_row_layout.setColumnStretch(1, 1)
        archive_filter_row_layout.addWidget(QLabel("Filter"), 0, 0)
        archive_filter_row_layout.addWidget(archive_filter_input, 0, 1)
        archive_filter_row_layout.addWidget(archive_filter_stats_label, 0, 2)
        archive_controls_layout.addWidget(archive_filter_row)

        archive_actions_row = QWidget()
        archive_actions_row.setObjectName("archive_actions_row")
        archive_actions_row_layout = QGridLayout(archive_actions_row)
        archive_actions_row_layout.setContentsMargins(0, 0, 0, 0)
        archive_actions_row_layout.setHorizontalSpacing(8)
        archive_actions_row_layout.setVerticalSpacing(0)
        archive_actions_row_layout.addWidget(refresh_archives_button, 0, 0)
        archive_actions_row_layout.addWidget(restore_archived_button, 0, 1)
        archive_actions_row_layout.addWidget(delete_archived_button, 0, 2)
        archive_actions_row_layout.setColumnStretch(3, 1)
        archive_controls_layout.addWidget(archive_actions_row)

        archive_empty_state_label = QLabel(
            "Refresh archive list to browse archived entries from real and sandbox workflows."
        )
        archive_empty_state_label.setObjectName("archive_empty_state_label")
        archive_empty_state_label.setWordWrap(True)
        archive_empty_state_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        archive_state_panel = QWidget()
        archive_state_panel.setObjectName("archive_state_panel")
        archive_state_panel_layout = QVBoxLayout(archive_state_panel)
        archive_state_panel_layout.setContentsMargins(0, 0, 0, 0)
        archive_state_panel_layout.setSpacing(0)
        archive_state_panel_layout.addWidget(archive_empty_state_label)
        archive_controls_layout.addWidget(archive_state_panel)

        layout.addWidget(archive_controls_group)

        archive_results_group = QGroupBox("Archived Entries (real + sandbox)")
        archive_results_group.setObjectName("archive_results_group")
        archive_results_group.setFlat(True)
        archive_results_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        archive_results_layout = QVBoxLayout(archive_results_group)
        archive_results_layout.setContentsMargins(10, 10, 10, 10)
        archive_results_layout.setSpacing(6)
        archive_results_layout.addWidget(archive_table)
        layout.addWidget(archive_results_group)
        archive_results_group.setVisible(False)
        layout.addStretch(1)

        self.controls_group = archive_controls_group
        self.empty_state_label = archive_empty_state_label
        self.results_group = archive_results_group
