from __future__ import annotations


def build_stitch_compact_widgets_stylesheet() -> str:
    return """
QWidget#app_shell_root {
    background: #121416;
}

QMainWindow {
    background: #121416;
}

QWidget {
    color: #ece7df;
    font-size: 10pt;
}

QLabel {
    color: #ece7df;
}

QGroupBox {
    background: #1b1f23;
    border: 1px solid rgba(224, 216, 203, 0.07);
    border-radius: 12px;
    margin-top: 8px;
    padding-top: 3px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    top: -1px;
    padding: 0 2px;
    color: #bda893;
    font-size: 7.6pt;
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
    background: #16191d;
}

QWidget#plan_install_tab_content,
QWidget#setup_surface_content_widget,
QWidget#setup_scroll_viewport,
QWidget#plan_install_scroll_viewport {
    background: #16191d;
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
    color: #f5f1ea;
    font-size: 16pt;
    font-weight: 700;
}

QLabel#workspace_page_subtitle {
    color: #b6ab9f;
    font-size: 9pt;
}

QGroupBox#top_context_surface_group,
QGroupBox#global_status_strip_group {
    background: #131619;
    border: 1px solid rgba(224, 216, 203, 0.06);
    border-radius: 10px;
}

QWidget#top_context_brand_panel,
QWidget#top_context_operational_panel,
QWidget#top_context_environment_panel,
QWidget#top_context_runtime_panel,
QWidget#top_context_active_context_panel {
    background: #181c20;
    border-radius: 8px;
}

QWidget#global_status_panel {
    background: #171b1e;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 7px;
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
    background: #191c20;
    border: 1px solid rgba(224, 216, 203, 0.05);
}

QGroupBox#setup_surface_group,
QGroupBox#setup_advanced_group {
    background: #1d2024;
}

QGroupBox#setup_backup_restore_group {
    background: #171a1d;
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
    color: #f4efe8;
    font-size: 11pt;
    font-weight: 700;
}

QLabel#top_context_brand_subtitle,
QLabel#global_status_panel_title,
QLabel#top_context_section_title {
    color: #bba792;
    font-size: 8pt;
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
    color: #f2eee8;
    font-size: 9.35pt;
    font-weight: 600;
}

QLabel[contextRole="caption"],
QLabel[statusRole="value"] {
    color: #c1b7ac;
    font-size: 8.5pt;
}

QFrame#workspace_shell_frame {
    background: transparent;
}

QFrame#workspace_nav_rail {
    background: #14171a;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 15px;
}

QFrame#workspace_nav_brand_panel,
QFrame#workspace_nav_footer_panel {
    background: #1b1f23;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 11px;
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
    font-size: 12.25pt;
    font-weight: 700;
}

QLabel#workspace_nav_brand_version,
QLabel#workspace_nav_section_label,
QLabel#workspace_nav_footer_label {
    color: #bcaea1;
    font-size: 8pt;
}

QLabel#workspace_nav_brand_subtitle {
    color: #d5c7bb;
    font-size: 8.4pt;
    font-weight: 500;
}

QLabel#workspace_nav_brand_version {
    color: #d6c7b8;
    font-size: 8pt;
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
    min-height: 28px;
    padding: 5px 9px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: #cfbeaf;
    text-align: left;
    font-size: 8.55pt;
    font-weight: 600;
}

QPushButton[navRole="workspace"]:hover {
    background: #1d2428;
    border-color: rgba(156, 195, 143, 0.14);
    color: #f0e5d8;
}

QPushButton[navRole="workspace"]:checked {
    background: #22342b;
    border-color: rgba(156, 195, 143, 0.22);
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

QTabBar#mods_workspace_mode_tabbar {
    background: transparent;
}

QTabBar#mods_workspace_mode_tabbar::tab {
    min-height: 26px;
    padding: 4px 11px;
    margin-right: 6px;
    background: #1e2326;
    color: #c6b19b;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 8px;
    font-weight: 600;
}

QTabBar#mods_workspace_mode_tabbar::tab:selected {
    background: #25352b;
    border-color: rgba(156, 195, 143, 0.2);
    color: #eef5e9;
}

QPushButton {
    min-height: 21px;
    padding: 4px 8px;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 7px;
    background: #24282c;
    color: #efe9e2;
}

QPushButton:hover {
    background: #2e3337;
    border-color: rgba(224, 216, 203, 0.09);
}

QPushButton:focus {
    border-color: rgba(241, 187, 57, 0.36);
}

QPushButton:disabled {
    background: #1c1f22;
    color: #6f6a63;
    border-color: rgba(224, 216, 203, 0.03);
}

QPushButton[buttonRole="primary"] {
    background: #f1bb39;
    color: #3d2a00;
    font-weight: 700;
    padding: 5px 10px;
    border-color: rgba(255, 238, 194, 0.18);
}

QPushButton[buttonRole="primary"]:hover {
    background: #f6c64f;
}

QPushButton[buttonRole="primary"]:disabled {
    background: #252620;
    color: #807665;
    border-color: rgba(224, 216, 203, 0.03);
}

QPushButton[buttonRole="secondary"] {
    background: #233027;
    color: #d4e6ce;
    padding: 4px 9px;
    border-color: rgba(156, 195, 143, 0.12);
}

QPushButton[buttonRole="secondary"]:hover {
    background: #2d392c;
}

QPushButton[buttonRole="secondary"]:disabled {
    background: #1d211f;
    color: #727a71;
    border-color: rgba(224, 216, 203, 0.03);
}

QPushButton[buttonRole="utility"] {
    background: #1a1e21;
    color: #c2b3a4;
    padding: 3px 7px;
    font-size: 8.35pt;
}

QPushButton[buttonRole="utility"]:hover {
    background: #24292c;
}

QPushButton[buttonRole="utility"]:disabled {
    background: #181a1c;
    color: #6a6661;
    border-color: rgba(224, 216, 203, 0.03);
}

QPushButton[buttonRole="danger"] {
    background: #633032;
    color: #ffd9d9;
    font-weight: 700;
}

QPushButton[buttonRole="danger"]:hover {
    background: #7b3b3e;
}

QPushButton[buttonRole="danger"]:disabled {
    background: #2a2324;
    color: #927b7b;
    border-color: rgba(224, 216, 203, 0.03);
}

QLabel#compact_hint_label,
QLabel#packages_intake_review_flow_label,
QLabel#packages_watcher_scope_label,
QLabel#plan_install_execute_help_label,
QLabel#plan_install_overwrite_help_label,
QLabel#archive_empty_state_label,
QLabel#discovery_intro_label,
QLabel#archive_intro_label {
    color: #bdb2a6;
    font-size: 8.9pt;
}

QLineEdit,
QComboBox,
QPlainTextEdit {
    background: #0f1214;
    border: 1px solid rgba(224, 216, 203, 0.11);
    border-radius: 8px;
    padding: 4px 8px;
    color: #eee9e2;
    selection-background-color: #305128;
}

QLineEdit:focus,
QComboBox:focus,
QPlainTextEdit:focus {
    border: 1px solid rgba(246, 190, 57, 0.5);
}

QLineEdit:disabled,
QComboBox:disabled,
QPlainTextEdit:disabled {
    background: #16191b;
    color: #888177;
    border-color: rgba(224, 216, 203, 0.05);
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
    background: #171b1f;
    alternate-background-color: #1a1e22;
    gridline-color: transparent;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 10px;
    selection-background-color: rgba(67, 106, 58, 0.58);
    selection-color: #f3f0ea;
    outline: 0;
}

QHeaderView::section {
    background: #1d2226;
    color: #b9a693;
    border: none;
    border-bottom: 1px solid rgba(224, 216, 203, 0.08);
    padding: 4px 8px;
    font-size: 8pt;
    font-weight: 700;
}

QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid rgba(224, 216, 203, 0.035);
}

QTableWidget::item:hover {
    background: rgba(255, 255, 255, 0.025);
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
    background: #3a3f43;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #474d52;
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
    background: #181b1e;
}

QLabel#compact_hint_label {
    color: #bdb2a6;
    font-size: 9pt;
}
"""
