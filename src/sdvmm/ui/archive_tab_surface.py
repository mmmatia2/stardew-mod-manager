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
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        archive_controls_group = QGroupBox("Archive Browser")
        archive_controls_group.setObjectName("archive_controls_group")
        archive_controls_group.setFlat(True)
        archive_controls_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        archive_controls_layout = QGridLayout(archive_controls_group)
        archive_controls_layout.setContentsMargins(8, 6, 8, 6)
        archive_controls_layout.setHorizontalSpacing(8)
        archive_controls_layout.setVerticalSpacing(4)
        archive_controls_layout.addWidget(QLabel("Filter"), 0, 0)
        archive_controls_layout.addWidget(archive_filter_input, 0, 1, 1, 2)
        archive_controls_layout.addWidget(archive_filter_stats_label, 0, 3)
        archive_controls_layout.addWidget(refresh_archives_button, 1, 1)
        archive_controls_layout.addWidget(restore_archived_button, 1, 2)
        archive_controls_layout.addWidget(delete_archived_button, 1, 3)
        layout.addWidget(archive_controls_group)

        archive_results_group = QGroupBox("Archived Entries (real + sandbox)")
        archive_results_group.setObjectName("archive_results_group")
        archive_results_group.setFlat(True)
        archive_results_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        archive_results_layout = QVBoxLayout(archive_results_group)
        archive_results_layout.setContentsMargins(8, 2, 8, 6)
        archive_results_layout.setSpacing(2)
        archive_results_layout.addWidget(archive_table)
        layout.addWidget(archive_results_group, 1)

        self.controls_group = archive_controls_group
        self.results_group = archive_results_group
