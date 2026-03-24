from __future__ import annotations

from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QTableWidget
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget


class DiscoveryTabSurface(QWidget):
    def __init__(
        self,
        *,
        discovery_query_input: QLineEdit,
        discovery_filter_input: QLineEdit,
        discovery_filter_stats_label: QLabel,
        discovery_table: QTableWidget,
        discovery_search_button: QPushButton,
        open_discovered_button: QPushButton,
    ) -> None:
        super().__init__()
        self.setObjectName("discovery_tab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        discovery_search_group = QGroupBox("Search and Source")
        discovery_search_group.setObjectName("discovery_search_group")
        discovery_search_group.setFlat(True)
        discovery_search_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        discovery_search_layout = QGridLayout(discovery_search_group)
        discovery_search_layout.setContentsMargins(10, 10, 10, 10)
        discovery_search_layout.setHorizontalSpacing(10)
        discovery_search_layout.setVerticalSpacing(6)
        discovery_search_layout.addWidget(QLabel("Search query"), 0, 0)
        discovery_search_layout.addWidget(discovery_query_input, 0, 1, 1, 2)
        discovery_search_layout.addWidget(discovery_search_button, 0, 3)
        discovery_search_layout.addWidget(open_discovered_button, 1, 3)
        discovery_search_layout.setColumnStretch(1, 1)
        layout.addWidget(discovery_search_group)

        discovery_results_group = QGroupBox("Results")
        discovery_results_group.setObjectName("discovery_results_group")
        discovery_results_group.setFlat(True)
        discovery_results_layout = QVBoxLayout(discovery_results_group)
        discovery_results_layout.setContentsMargins(10, 10, 10, 10)
        discovery_results_layout.setSpacing(8)
        discovery_filter_layout = QHBoxLayout()
        discovery_filter_layout.setSpacing(8)
        discovery_filter_layout.addWidget(QLabel("Filter"))
        discovery_filter_layout.addWidget(discovery_filter_input, 1)
        discovery_filter_layout.addWidget(discovery_filter_stats_label)
        discovery_results_layout.addLayout(discovery_filter_layout)
        discovery_results_layout.addWidget(discovery_table)
        layout.addWidget(discovery_results_group)
        layout.setStretch(1, 1)

        self.search_group = discovery_search_group
        self.results_group = discovery_results_group
