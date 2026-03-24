from __future__ import annotations


def build_stitch_compact_widgets_stylesheet() -> str:
    return """
QWidget#app_shell_root {
    background: #141516;
}

QMainWindow {
    background: #141516;
}

QWidget {
    color: #e7e3dd;
    font-size: 10pt;
}

QLabel {
    color: #e7e3dd;
}

QGroupBox {
    background: #1b1d1f;
    border: none;
    border-radius: 12px;
    margin-top: 10px;
    padding-top: 3px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: -1px;
    padding: 0 2px;
    color: #beaa96;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.02em;
}

QWidget#workspace_page,
QWidget#mods_workspace_page,
QWidget#discovery_workspace_page,
QWidget#archive_workspace_page,
QWidget#compare_tab,
QWidget#recovery_tab,
QWidget#packages_workspace_page,
QWidget#review_workspace_page,
QWidget#setup_workspace_page {
    background: #17191b;
}

QWidget#plan_install_tab_content,
QWidget#setup_surface_content_widget,
QWidget#setup_scroll_viewport,
QWidget#plan_install_scroll_viewport {
    background: #17191b;
}

QWidget#setup_surface_workspace_band,
QWidget#setup_surface_main_column,
QWidget#setup_surface_secondary_column,
QWidget#setup_surface_primary_actions {
    background: transparent;
}

QFrame#workspace_page_header {
    background: transparent;
    border-radius: 0px;
}

QLabel#workspace_page_eyebrow {
    color: #9cc38f;
    font-size: 7pt;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
}

QLabel#workspace_page_title {
    color: #f4f1eb;
    font-size: 17pt;
    font-weight: 700;
}

QLabel#workspace_page_subtitle {
    color: #aba095;
    font-size: 9pt;
}

QGroupBox#top_context_surface_group,
QGroupBox#global_status_strip_group {
    background: #151718;
    border-radius: 10px;
}

QWidget#top_context_brand_panel,
QWidget#top_context_operational_panel,
QFrame#global_status_panel,
QWidget#top_context_environment_panel,
QWidget#top_context_runtime_panel,
QWidget#top_context_active_context_panel {
    background: #1a1d1f;
    border-radius: 8px;
}

QWidget#top_context_environment_panel[panelVariant="inline"],
QWidget#top_context_runtime_panel[panelVariant="inline"],
QWidget#top_context_active_context_panel[panelVariant="inline"] {
    background: transparent;
    border-radius: 0px;
}

QGroupBox#discovery_output_group,
QGroupBox#compare_output_group,
QGroupBox#packages_output_group,
QGroupBox#plan_install_output_group,
QGroupBox#recovery_output_group,
QGroupBox#archive_output_group,
QGroupBox#setup_output_group {
    background: #17191b;
}

QGroupBox#setup_surface_group,
QGroupBox#setup_advanced_group {
    background: #1b1d1f;
}

QGroupBox#setup_backup_restore_group {
    background: #191b1d;
}

QLabel[setupFieldLabel="true"] {
    color: #c9b7a5;
    font-size: 7.75pt;
    font-weight: 700;
}

QLabel#top_context_brand_eyebrow {
    color: #9cc38f;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
}

QLabel#top_context_brand_title {
    color: #f4f1eb;
    font-size: 11.75pt;
    font-weight: 700;
}

QLabel#top_context_brand_subtitle,
QLabel#global_status_panel_title,
QLabel#top_context_section_title {
    color: #b29d89;
    font-size: 8.25pt;
    font-weight: 700;
    letter-spacing: 0.05em;
}

QLabel#global_status_summary_label {
    color: #8ea983;
    font-size: 7.75pt;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}

QLabel[contextRole="value"] {
    color: #f0ece6;
    font-size: 9.75pt;
    font-weight: 600;
}

QLabel[contextRole="caption"],
QLabel[statusRole="value"] {
    color: #bdb2a6;
    font-size: 8.75pt;
}

QFrame#workspace_shell_frame {
    background: transparent;
}

QFrame#workspace_nav_rail {
    background: #17191b;
    border-radius: 16px;
}

QFrame#workspace_nav_brand_panel,
QFrame#workspace_nav_footer_panel {
    background: #1d2022;
    border-radius: 12px;
}

QLabel#workspace_nav_brand_eyebrow {
    color: #9cc38f;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
}

QLabel#workspace_nav_brand_title {
    color: #f4f1eb;
    font-size: 13pt;
    font-weight: 700;
}

QLabel#workspace_nav_brand_version,
QLabel#workspace_nav_section_label,
QLabel#workspace_nav_footer_label {
    color: #b8ac9f;
    font-size: 8pt;
}

QLabel#workspace_nav_brand_subtitle {
    color: #d8cabd;
    font-size: 8.75pt;
    font-weight: 600;
}

QLabel#workspace_nav_brand_version {
    color: #d6c7b8;
    font-size: 8.25pt;
    font-weight: 600;
}

QLabel#workspace_nav_section_label {
    color: #9a8d7f;
    font-size: 7pt;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
}

QPushButton[navRole="workspace"] {
    min-height: 30px;
    padding: 6px 10px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: #cfbeaf;
    text-align: left;
    font-size: 8.75pt;
    font-weight: 600;
}

QPushButton[navRole="workspace"]:hover {
    background: #1f2325;
    color: #f0e5d8;
}

QPushButton[navRole="workspace"]:checked {
    background: #253126;
    color: #edf5ea;
}

QTabWidget#workspace_nav_tabs::pane {
    border: none;
    background: #17191b;
    left: -1px;
}

QTabBar#workspace_nav_tabbar {
    background: transparent;
    max-width: 0px;
    width: 0px;
    min-width: 0px;
    margin: 0px;
    padding: 0px;
}

QTabBar#workspace_nav_tabbar::tab {
    max-width: 0px;
    width: 0px;
    min-width: 0px;
    min-height: 0px;
    margin: 0px;
    padding: 0px;
    border: none;
    background: transparent;
    color: transparent;
}

QTabBar#workspace_nav_tabbar::tab:selected {
    background: transparent;
}

QTabBar#workspace_nav_tabbar::tab:hover:!selected {
    background: transparent;
}

QTabBar#workspace_nav_tabbar::tab:first {
    margin-top: 0px;
}

QTabWidget#mods_workspace_mode_tabs::pane {
    border: none;
    background: transparent;
    top: -1px;
}

QTabBar#mods_workspace_mode_tabbar::tab {
    min-height: 28px;
    padding: 5px 12px;
    margin-right: 6px;
    background: #202326;
    color: #bca894;
    border: none;
    border-radius: 8px;
    font-weight: 600;
}

QTabBar#mods_workspace_mode_tabbar::tab:selected {
    background: #2a3a27;
    color: #eef5e9;
}

QPushButton {
    min-height: 22px;
    padding: 4px 9px;
    border: none;
    border-radius: 7px;
    background: #2a2d30;
    color: #efe9e2;
}

QPushButton:hover {
    background: #35383b;
}

QPushButton:disabled {
    background: #232527;
    color: #7d7770;
}

QPushButton[buttonRole="primary"] {
    background: #f1bb39;
    color: #3d2a00;
    font-weight: 700;
    padding: 5px 10px;
}

QPushButton[buttonRole="primary"]:hover {
    background: #f6c64f;
}

QPushButton[buttonRole="secondary"] {
    background: #262f25;
    color: #d2e4cb;
    padding: 4px 9px;
}

QPushButton[buttonRole="secondary"]:hover {
    background: #2d392c;
}

QPushButton[buttonRole="utility"] {
    background: #1d2022;
    color: #bcad9d;
    padding: 3px 8px;
    font-size: 8.5pt;
}

QPushButton[buttonRole="utility"]:hover {
    background: #24292c;
}

QPushButton[buttonRole="danger"] {
    background: #633032;
    color: #ffd9d9;
    font-weight: 700;
}

QPushButton[buttonRole="danger"]:hover {
    background: #7b3b3e;
}

QLabel#compact_hint_label,
QLabel#packages_intake_review_flow_label,
QLabel#packages_watcher_scope_label,
QLabel#plan_install_execute_help_label,
QLabel#plan_install_overwrite_help_label,
QLabel#archive_empty_state_label,
QLabel#discovery_intro_label,
QLabel#archive_intro_label {
    color: #b5aa9c;
    font-size: 8.75pt;
}

QLineEdit,
QComboBox,
QPlainTextEdit {
    background: #101113;
    border: 1px solid rgba(155, 142, 134, 0.14);
    border-radius: 8px;
    padding: 4px 8px;
    color: #eee9e2;
    selection-background-color: #305128;
}

QLineEdit:focus,
QComboBox:focus,
QPlainTextEdit:focus {
    border: 1px solid rgba(246, 190, 57, 0.55);
}

QComboBox::drop-down {
    border: none;
    width: 18px;
}

QComboBox QAbstractItemView {
    background: #1d1f21;
    color: #eee9e2;
    border: 1px solid rgba(155, 142, 134, 0.14);
    selection-background-color: #305128;
}

QTableWidget {
    background: #141617;
    alternate-background-color: #171a1b;
    gridline-color: transparent;
    border: none;
    border-radius: 10px;
    selection-background-color: rgba(67, 106, 58, 0.52);
    selection-color: #f3f0ea;
    outline: 0;
}

QHeaderView::section {
    background: #1a1d1f;
    color: #b6a393;
    border: none;
    border-bottom: 1px solid rgba(155, 142, 134, 0.12);
    padding: 4px 8px;
    font-size: 8pt;
    font-weight: 700;
}

QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid rgba(155, 142, 134, 0.04);
}

QTableWidget::item:selected {
    color: #f3f0ea;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #323538;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #3d4144;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar:horizontal,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    border: none;
    height: 0;
    width: 0;
}

QCheckBox {
    spacing: 6px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1px solid rgba(155, 142, 134, 0.3);
    background: #101113;
}

QCheckBox::indicator:checked {
    background: #305128;
    border-color: #9cc38f;
}

QSplitter::handle {
    background: #1b1d1f;
}

QLabel#compact_hint_label {
    color: #bdb2a6;
    font-size: 9pt;
}
"""
