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
        self.viewport().setObjectName("setup_scroll_viewport")

        def _build_path_row(
            *,
            object_name: str,
            label_text: str,
            field_widget: QWidget,
            primary_button: QPushButton,
            secondary_button: QPushButton | None = None,
        ) -> QWidget:
            row_widget = QWidget()
            row_widget.setObjectName(object_name)
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)

            row_label = QLabel(label_text)
            row_label.setProperty("setupFieldLabel", True)
            row_layout.addWidget(row_label)

            field_row = QHBoxLayout()
            field_row.setContentsMargins(0, 0, 0, 0)
            field_row.setSpacing(8)
            field_row.addWidget(field_widget, 1)
            field_row.addWidget(primary_button)
            if secondary_button is not None:
                field_row.addWidget(secondary_button)
            row_layout.addLayout(field_row)
            return row_widget

        primary_actions_widget = QWidget()
        primary_actions_widget.setObjectName("setup_surface_primary_actions")
        primary_actions_layout = QHBoxLayout(primary_actions_widget)
        primary_actions_layout.setContentsMargins(0, 0, 0, 0)
        primary_actions_layout.setSpacing(8)
        primary_actions_layout.addWidget(save_button)
        primary_actions_layout.addWidget(detect_environment_button)
        primary_actions_layout.addStretch(1)

        setup_group = QGroupBox("Essential folders")
        setup_group.setObjectName("setup_surface_group")
        setup_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        setup_layout = QVBoxLayout(setup_group)
        setup_layout.setContentsMargins(14, 14, 14, 14)
        setup_layout.setSpacing(12)
        setup_intro_label = QLabel(
            "Start with the live game folder plus your real and sandbox Mods folders. "
            "Saving setup or detecting folders here does not change installed mods."
        )
        setup_intro_label.setObjectName("setup_local_setup_intro_label")
        setup_intro_label.setWordWrap(True)
        setup_layout.addWidget(primary_actions_widget)
        setup_layout.addWidget(setup_intro_label)
        setup_layout.addWidget(
            _build_path_row(
                object_name="setup_game_path_row",
                label_text="Game folder (live install)",
                field_widget=game_path_input,
                primary_button=browse_game_button,
            )
        )
        setup_layout.addWidget(
            _build_path_row(
                object_name="setup_real_mods_path_row",
                label_text="Real Mods folder",
                field_widget=mods_path_input,
                primary_button=browse_mods_button,
                secondary_button=open_mods_button,
            )
        )
        setup_layout.addWidget(
            _build_path_row(
                object_name="setup_sandbox_mods_path_row",
                label_text="Sandbox Mods folder",
                field_widget=sandbox_mods_path_input,
                primary_button=browse_sandbox_button,
                secondary_button=open_sandbox_button,
            )
        )

        advanced_group = QGroupBox("Advanced and safety options")
        advanced_group.setObjectName("setup_advanced_group")
        advanced_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setContentsMargins(14, 14, 14, 14)
        advanced_layout.setSpacing(12)
        advanced_intro_label = QLabel(
            "Archive folders protect live and sandbox workflows. Nexus and Steam options are optional helpers."
        )
        advanced_intro_label.setObjectName("setup_advanced_intro_label")
        advanced_intro_label.setWordWrap(True)
        advanced_layout.addWidget(advanced_intro_label)
        advanced_layout.addWidget(
            _build_path_row(
                object_name="setup_sandbox_archive_path_row",
                label_text="Sandbox archive folder",
                field_widget=sandbox_archive_path_input,
                primary_button=browse_sandbox_archive_button,
                secondary_button=open_sandbox_archive_button,
            )
        )
        advanced_layout.addWidget(
            _build_path_row(
                object_name="setup_real_archive_path_row",
                label_text="Real Mods archive folder",
                field_widget=real_archive_path_input,
                primary_button=browse_real_archive_button,
                secondary_button=open_real_archive_button,
            )
        )

        nexus_row = QWidget()
        nexus_row.setObjectName("setup_nexus_api_key_row")
        nexus_row_layout = QVBoxLayout(nexus_row)
        nexus_row_layout.setContentsMargins(0, 0, 0, 0)
        nexus_row_layout.setSpacing(5)
        nexus_label = QLabel("Nexus API key")
        nexus_label.setProperty("setupFieldLabel", True)
        nexus_row_layout.addWidget(nexus_label)
        nexus_field_row = QHBoxLayout()
        nexus_field_row.setContentsMargins(0, 0, 0, 0)
        nexus_field_row.setSpacing(8)
        nexus_field_row.addWidget(nexus_api_key_input, 1)
        nexus_field_row.addWidget(check_nexus_button)
        nexus_row_layout.addLayout(nexus_field_row)
        advanced_layout.addWidget(nexus_row)
        advanced_layout.addWidget(steam_auto_start_checkbox)

        setup_actions_widget = QWidget()
        setup_actions_widget.setObjectName("setup_actions_widget")
        setup_actions_layout = QGridLayout(setup_actions_widget)
        setup_actions_layout.setContentsMargins(0, 0, 0, 0)
        setup_actions_layout.setHorizontalSpacing(8)
        setup_actions_layout.setVerticalSpacing(6)
        action_buttons = (
            export_backup_button,
            inspect_backup_button,
            plan_restore_import_button,
            execute_restore_import_button,
        )
        for index, button in enumerate(action_buttons):
            setup_actions_layout.addWidget(button, index // 2, index % 2)
        for column in range(2):
            setup_actions_layout.setColumnStretch(column, 1)

        backup_group = QGroupBox("Back Up, Inspect, and Restore")
        backup_group.setObjectName("setup_backup_restore_group")
        backup_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setContentsMargins(14, 14, 14, 14)
        backup_layout.setSpacing(10)

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
        setup_output_layout.setContentsMargins(14, 14, 14, 14)
        setup_output_layout.setSpacing(8)
        setup_output_layout.addWidget(setup_output_box)

        content_widget = QWidget()
        content_widget.setObjectName("setup_surface_content_widget")
        content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        workspace_band = QWidget()
        workspace_band.setObjectName("setup_surface_workspace_band")
        workspace_band.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        workspace_layout = QHBoxLayout(workspace_band)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(18)

        main_column = QWidget()
        main_column.setObjectName("setup_surface_main_column")
        main_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        main_layout = QVBoxLayout(main_column)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(14)
        main_layout.addWidget(setup_group)
        main_layout.addWidget(advanced_group)
        main_layout.addStretch(1)

        secondary_column = QWidget()
        secondary_column.setObjectName("setup_surface_secondary_column")
        secondary_column.setMinimumWidth(340)
        secondary_column.setMaximumWidth(440)
        secondary_column.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        secondary_layout = QVBoxLayout(secondary_column)
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        secondary_layout.setSpacing(14)
        secondary_layout.addWidget(backup_group)
        secondary_layout.addWidget(setup_output_group)
        secondary_layout.addStretch(1)

        workspace_layout.addWidget(main_column, 7)
        workspace_layout.addWidget(secondary_column, 4)
        content_layout.addWidget(workspace_band)

        self.setWidget(content_widget)
        self.content_widget = content_widget
        self.workspace_band = workspace_band
        self.main_column = main_column
        self.secondary_column = secondary_column
        self.setup_group = setup_group
        self.advanced_group = advanced_group
        self.backup_group = backup_group
        self.setup_output_group = setup_output_group
