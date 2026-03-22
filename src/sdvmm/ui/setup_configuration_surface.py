from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget


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
        steam_auto_start_checkbox: QCheckBox,
        browse_game_button: QPushButton,
        browse_mods_button: QPushButton,
        open_mods_button: QPushButton,
        browse_sandbox_button: QPushButton,
        open_sandbox_button: QPushButton,
        browse_sandbox_archive_button: QPushButton,
        open_sandbox_archive_button: QPushButton,
        browse_real_archive_button: QPushButton,
        open_real_archive_button: QPushButton,
        check_nexus_button: QPushButton,
        save_button: QPushButton,
        detect_environment_button: QPushButton,
        export_backup_button: QPushButton,
        inspect_backup_button: QPushButton,
        plan_restore_import_button: QPushButton,
        execute_restore_import_button: QPushButton,
        active_backup_bundle_label: QLabel,
        backup_bundle_inspection_summary_label: QLabel,
        restore_import_planning_summary_label: QLabel,
        setup_output_box: QPlainTextEdit,
    ) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        setup_group = QGroupBox("Essential folders")
        setup_group.setObjectName("setup_surface_group")
        setup_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        setup_layout = QGridLayout(setup_group)
        setup_layout.setContentsMargins(6, 4, 6, 4)
        setup_layout.setHorizontalSpacing(8)
        setup_layout.setVerticalSpacing(3)
        setup_intro_label = QLabel(
            "Start with the live game folder plus your real and sandbox Mods folders. "
            "Saving setup or detecting folders here does not change installed mods."
        )
        setup_intro_label.setObjectName("setup_local_setup_intro_label")
        setup_intro_label.setWordWrap(True)
        setup_layout.addWidget(setup_intro_label, 0, 0, 1, 4)

        setup_layout.addWidget(QLabel("Game folder (live install)"), 1, 0)
        setup_layout.addWidget(game_path_input, 1, 1)
        setup_layout.addWidget(browse_game_button, 1, 2)

        setup_layout.addWidget(QLabel("Real Mods folder"), 2, 0)
        setup_layout.addWidget(mods_path_input, 2, 1)
        setup_layout.addWidget(browse_mods_button, 2, 2)
        setup_layout.addWidget(open_mods_button, 2, 3)

        setup_layout.addWidget(QLabel("Sandbox Mods folder"), 3, 0)
        setup_layout.addWidget(sandbox_mods_path_input, 3, 1)
        setup_layout.addWidget(browse_sandbox_button, 3, 2)
        setup_layout.addWidget(open_sandbox_button, 3, 3)

        setup_layout.setColumnStretch(1, 1)

        advanced_group = QGroupBox("Advanced and safety options")
        advanced_group.setObjectName("setup_advanced_group")
        advanced_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        advanced_layout = QGridLayout(advanced_group)
        advanced_layout.setContentsMargins(6, 4, 6, 4)
        advanced_layout.setHorizontalSpacing(8)
        advanced_layout.setVerticalSpacing(3)
        advanced_intro_label = QLabel(
            "Archive folders protect live and sandbox workflows. Nexus and Steam options are optional helpers."
        )
        advanced_intro_label.setObjectName("setup_advanced_intro_label")
        advanced_intro_label.setWordWrap(True)
        advanced_layout.addWidget(advanced_intro_label, 0, 0, 1, 4)

        advanced_layout.addWidget(QLabel("Sandbox archive folder"), 1, 0)
        advanced_layout.addWidget(sandbox_archive_path_input, 1, 1)
        advanced_layout.addWidget(browse_sandbox_archive_button, 1, 2)
        advanced_layout.addWidget(open_sandbox_archive_button, 1, 3)

        advanced_layout.addWidget(QLabel("Real Mods archive folder"), 2, 0)
        advanced_layout.addWidget(real_archive_path_input, 2, 1)
        advanced_layout.addWidget(browse_real_archive_button, 2, 2)
        advanced_layout.addWidget(open_real_archive_button, 2, 3)

        advanced_layout.addWidget(QLabel("Nexus API key"), 3, 0)
        advanced_layout.addWidget(nexus_api_key_input, 3, 1)
        advanced_layout.addWidget(check_nexus_button, 3, 2)
        advanced_layout.addWidget(steam_auto_start_checkbox, 4, 0, 1, 4)
        advanced_layout.setColumnStretch(1, 1)

        setup_actions_widget = QWidget()
        setup_actions_widget.setObjectName("setup_actions_widget")
        setup_actions_layout = QGridLayout(setup_actions_widget)
        setup_actions_layout.setContentsMargins(0, 0, 0, 0)
        setup_actions_layout.setHorizontalSpacing(6)
        setup_actions_layout.setVerticalSpacing(4)
        action_buttons = (
            save_button,
            detect_environment_button,
            export_backup_button,
            inspect_backup_button,
            plan_restore_import_button,
            execute_restore_import_button,
        )
        for index, button in enumerate(action_buttons):
            setup_actions_layout.addWidget(button, index // 3, index % 3)
        for column in range(3):
            setup_actions_layout.setColumnStretch(column, 1)

        backup_group = QGroupBox("Back Up, Inspect, and Restore")
        backup_group.setObjectName("setup_backup_restore_group")
        backup_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setContentsMargins(6, 4, 6, 6)
        backup_layout.setSpacing(4)

        backup_intro_label = QLabel(
            "Export creates a backup bundle. Inspect and Plan are read-only. "
            "Execute restore/import writes only into the current configured folders."
        )
        backup_intro_label.setObjectName("setup_backup_restore_intro_label")
        backup_intro_label.setWordWrap(True)
        backup_layout.addWidget(backup_intro_label)
        backup_layout.addWidget(setup_actions_widget)
        backup_layout.addWidget(active_backup_bundle_label)
        backup_layout.addWidget(backup_bundle_inspection_summary_label)
        backup_layout.addWidget(restore_import_planning_summary_label)

        setup_output_group = QGroupBox("Setup and migration details")
        setup_output_group.setObjectName("setup_output_group")
        setup_output_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        setup_output_layout = QVBoxLayout(setup_output_group)
        setup_output_layout.setContentsMargins(6, 4, 6, 6)
        setup_output_layout.setSpacing(4)
        setup_output_layout.addWidget(setup_output_box)

        content_widget = QWidget()
        content_widget.setObjectName("setup_surface_content_widget")
        content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        content_layout.addWidget(setup_group)
        content_layout.addWidget(advanced_group)
        content_layout.addWidget(backup_group)
        content_layout.addWidget(setup_output_group)
        content_layout.addStretch(1)

        self.setWidget(content_widget)
        self.content_widget = content_widget
        self.setup_group = setup_group
        self.advanced_group = advanced_group
        self.backup_group = backup_group
        self.setup_output_group = setup_output_group
