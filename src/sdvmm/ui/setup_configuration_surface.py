from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QSizePolicy


class SetupConfigurationSurface(QScrollArea):
    def __init__(
        self,
        *,
        game_path_input: QLineEdit,
        mods_path_input: QLineEdit,
        sandbox_mods_path_input: QLineEdit,
        sandbox_archive_path_input: QLineEdit,
        real_archive_path_input: QLineEdit,
        nexus_api_key_input: QLineEdit,
        browse_game_button: QPushButton,
        browse_mods_button: QPushButton,
        browse_sandbox_button: QPushButton,
        browse_sandbox_archive_button: QPushButton,
        browse_real_archive_button: QPushButton,
        check_nexus_button: QPushButton,
        save_button: QPushButton,
        detect_environment_button: QPushButton,
        export_backup_button: QPushButton,
    ) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        setup_group = QGroupBox("Setup and Configuration")
        setup_group.setObjectName("setup_surface_group")
        setup_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        setup_layout = QGridLayout(setup_group)
        setup_layout.setContentsMargins(6, 4, 6, 4)
        setup_layout.setHorizontalSpacing(8)
        setup_layout.setVerticalSpacing(3)
        setup_layout.addWidget(QLabel("Game directory (real install)"), 0, 0)
        setup_layout.addWidget(game_path_input, 0, 1)
        setup_layout.addWidget(browse_game_button, 0, 2)

        setup_layout.addWidget(QLabel("Mods directory (real path)"), 1, 0)
        setup_layout.addWidget(mods_path_input, 1, 1)
        setup_layout.addWidget(browse_mods_button, 1, 2)

        setup_layout.addWidget(QLabel("Sandbox Mods target"), 2, 0)
        setup_layout.addWidget(sandbox_mods_path_input, 2, 1)
        setup_layout.addWidget(browse_sandbox_button, 2, 2)

        setup_layout.addWidget(QLabel("Sandbox archive path"), 3, 0)
        setup_layout.addWidget(sandbox_archive_path_input, 3, 1)
        setup_layout.addWidget(browse_sandbox_archive_button, 3, 2)

        setup_layout.addWidget(QLabel("Real Mods archive path"), 4, 0)
        setup_layout.addWidget(real_archive_path_input, 4, 1)
        setup_layout.addWidget(browse_real_archive_button, 4, 2)

        setup_layout.addWidget(QLabel("Nexus API key"), 5, 0)
        setup_layout.addWidget(nexus_api_key_input, 5, 1)
        setup_layout.addWidget(check_nexus_button, 5, 2)

        setup_actions = QHBoxLayout()
        setup_actions.addWidget(save_button)
        setup_actions.addWidget(detect_environment_button)
        setup_actions.addWidget(export_backup_button)
        setup_actions.addStretch(1)
        setup_layout.addLayout(setup_actions, 6, 0, 1, 3)

        self.setWidget(setup_group)
        self.setup_group = setup_group
