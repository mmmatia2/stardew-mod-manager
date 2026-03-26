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

QWidget#archive_state_panel {
    background: #171b1e;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 10px;
}

QFrame#setup_secondary_panel {
    background: #14181b;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 12px;
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

QLabel#mods_inventory_state_label,
QLabel#discovery_results_state_label,
QLabel#packages_workspace_state_label,
QLabel#plan_install_state_label,
QLabel#archive_empty_state_label,
QLabel#archive_state_hint_label,
QLabel#compare_summary_label {
    background: #171b1e;
    border: 1px solid rgba(224, 216, 203, 0.05);
    border-radius: 8px;
    padding: 6px 9px;
    color: #cabfb3;
    font-size: 8.8pt;
}

QLabel#mods_inventory_state_label[feedbackTone="empty"],
QLabel#discovery_results_state_label[feedbackTone="empty"],
QLabel#packages_workspace_state_label[feedbackTone="empty"],
QLabel#plan_install_state_label[feedbackTone="empty"],
QLabel#archive_empty_state_label[feedbackTone="empty"],
QLabel#compare_summary_label[feedbackTone="empty"] {
    background: #171b1e;
    border-color: rgba(224, 216, 203, 0.05);
    color: #c5b8aa;
}

QLabel#mods_inventory_state_label[feedbackTone="muted"],
QLabel#discovery_results_state_label[feedbackTone="muted"],
QLabel#packages_workspace_state_label[feedbackTone="muted"],
QLabel#plan_install_state_label[feedbackTone="muted"],
QLabel#archive_state_hint_label[feedbackTone="muted"],
QLabel#compare_summary_label[feedbackTone="muted"] {
    background: #191d21;
    border-color: rgba(224, 216, 203, 0.07);
    color: #d1c4b8;
}

QLabel#mods_inventory_state_label[feedbackTone="ready"],
QLabel#discovery_results_state_label[feedbackTone="ready"],
QLabel#packages_workspace_state_label[feedbackTone="ready"],
QLabel#plan_install_state_label[feedbackTone="ready"],
QLabel#archive_state_hint_label[feedbackTone="ready"],
QLabel#compare_summary_label[feedbackTone="ready"] {
    background: #1a231d;
    border-color: rgba(156, 195, 143, 0.16);
    color: #dbe8d5;
}

QLabel#mods_inventory_state_label[feedbackTone="active"],
QLabel#discovery_results_state_label[feedbackTone="active"],
QLabel#packages_workspace_state_label[feedbackTone="active"],
QLabel#plan_install_state_label[feedbackTone="active"],
QLabel#archive_empty_state_label[feedbackTone="active"],
QLabel#archive_state_hint_label[feedbackTone="active"],
QLabel#compare_summary_label[feedbackTone="active"] {
    background: #252014;
    border-color: rgba(241, 187, 57, 0.14);
    color: #f0dfb8;
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
    background: #1e2328;
}

QGroupBox#setup_backup_restore_group {
    background: #181c20;
}

QGroupBox#setup_output_group {
    background: #161a1d;
}

QGroupBox#setup_backup_restore_group::title,
QGroupBox#setup_output_group::title {
    color: #ab9888;
}

QLabel#setup_main_column_intro_label {
    color: #c3b7ab;
    font-size: 8.85pt;
}

QLabel#setup_secondary_section_label {
    color: #9cc38f;
    font-size: 7.1pt;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
}

QLabel#setup_local_setup_intro_label,
QLabel#setup_advanced_intro_label,
QLabel#setup_backup_restore_intro_label,
QLabel#setup_secondary_intro_label {
    color: #b4a89c;
    font-size: 8.6pt;
}

QLabel#setup_secondary_intro_label {
    color: #a79b8e;
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
    font-size: 7.8pt;
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
    background: #1b2327;
    border-color: rgba(156, 195, 143, 0.16);
    color: #f0e5d8;
}

QPushButton[navRole="workspace"]:checked {
    background: #23362c;
    border-color: rgba(156, 195, 143, 0.24);
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
    background: #1c2125;
    color: #c6b19b;
    border: 1px solid rgba(224, 216, 203, 0.06);
    border-radius: 8px;
    font-weight: 600;
}

QTabBar#mods_workspace_mode_tabbar::tab:hover:!selected {
    background: #23282d;
    border-color: rgba(224, 216, 203, 0.1);
    color: #e6dacd;
}

QTabBar#mods_workspace_mode_tabbar::tab:selected {
    background: #24372b;
    border-color: rgba(156, 195, 143, 0.22);
    color: #eef5e9;
}

QPushButton {
    min-height: 21px;
    padding: 4px 8px;
    border: 1px solid rgba(224, 216, 203, 0.06);
    border-radius: 8px;
    background: #23282d;
    color: #efe9e2;
}

QPushButton:hover {
    background: #2b3136;
    border-color: rgba(224, 216, 203, 0.12);
}

QPushButton:pressed {
    background: #1b1f23;
    border-color: rgba(224, 216, 203, 0.16);
}

QPushButton:focus {
    border-color: rgba(241, 187, 57, 0.42);
}

QPushButton:disabled {
    background: #191c1f;
    color: #625d56;
    border-color: rgba(224, 216, 203, 0.025);
}

QPushButton[buttonRole="primary"] {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 #f5c95b,
        stop: 1 #e8ae28
    );
    color: #362500;
    font-weight: 700;
    padding: 5px 11px;
    border-color: rgba(255, 238, 194, 0.22);
}

QPushButton[buttonRole="primary"]:hover {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 #f8cf66,
        stop: 1 #ebb534
    );
}

QPushButton[buttonRole="primary"]:pressed {
    background: #d8a122;
    color: #2f1f00;
}

QPushButton[buttonRole="primary"]:disabled {
    background: #23241f;
    color: #7a715f;
    border-color: rgba(224, 216, 203, 0.025);
}

QPushButton[buttonRole="secondary"] {
    background: #202a23;
    color: #d0e1ca;
    padding: 4px 9px;
    border-color: rgba(156, 195, 143, 0.13);
}

QPushButton[buttonRole="secondary"]:hover {
    background: #283329;
    border-color: rgba(156, 195, 143, 0.18);
}

QPushButton[buttonRole="secondary"]:pressed {
    background: #1b241e;
}

QPushButton[buttonRole="secondary"]:disabled {
    background: #1a1e1b;
    color: #6b726b;
    border-color: rgba(224, 216, 203, 0.025);
}

QPushButton[buttonRole="utility"] {
    background: #171b1e;
    color: #c3b7ab;
    padding: 3px 7px;
    font-size: 8.35pt;
    border-color: rgba(224, 216, 203, 0.045);
}

QPushButton[buttonRole="utility"]:hover {
    background: #21262a;
    border-color: rgba(224, 216, 203, 0.085);
}

QPushButton[buttonRole="utility"]:pressed {
    background: #15181b;
}

QPushButton[buttonRole="utility"]:disabled {
    background: #17191b;
    color: #64605b;
    border-color: rgba(224, 216, 203, 0.025);
}

QWidget#setup_surface_primary_actions QPushButton[buttonRole="primary"] {
    padding-left: 12px;
    padding-right: 12px;
}

QWidget#setup_surface_primary_actions QPushButton[buttonRole="utility"] {
    padding-left: 10px;
    padding-right: 10px;
}

QPushButton[buttonRole="danger"] {
    background: #5f2d30;
    color: #ffd9d9;
    font-weight: 700;
}

QPushButton[buttonRole="danger"]:hover {
    background: #75383b;
}

QPushButton[buttonRole="danger"]:pressed {
    background: #522629;
}

QPushButton[buttonRole="danger"]:disabled {
    background: #241f20;
    color: #8b7676;
    border-color: rgba(224, 216, 203, 0.025);
}

QGroupBox#discovery_search_group,
QGroupBox#discovery_results_group,
QGroupBox#compare_results_group,
QGroupBox#packages_import_group,
QGroupBox#packages_watcher_group,
QGroupBox#packages_review_target_group,
QGroupBox#archive_controls_group,
QGroupBox#archive_results_group,
QGroupBox#plan_install_destination_group,
QGroupBox#plan_install_execute_group,
QGroupBox#plan_install_safety_panel_group,
QGroupBox#plan_install_staged_package_group,
QGroupBox#plan_install_review_summary_group,
QGroupBox#plan_install_facts_group {
    background: #1b2024;
    border: 1px solid rgba(224, 216, 203, 0.06);
    border-radius: 12px;
}

QGroupBox#packages_review_target_group,
QGroupBox#plan_install_execute_group,
QGroupBox#plan_install_staged_package_group {
    background: #1a2023;
    border-color: rgba(156, 195, 143, 0.09);
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
    background: #0e1113;
    border: 1px solid rgba(224, 216, 203, 0.12);
    border-radius: 8px;
    padding: 4px 8px;
    color: #eee9e2;
    selection-background-color: #3d6233;
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
    selection-background-color: #3d6233;
}

QTableWidget {
    background: #171c20;
    alternate-background-color: #1b2025;
    gridline-color: transparent;
    border: 1px solid rgba(224, 216, 203, 0.06);
    border-radius: 11px;
    selection-background-color: rgba(85, 125, 69, 0.74);
    selection-color: #f8f4ed;
    outline: 0;
}

QHeaderView::section {
    background: #20262b;
    color: #c5b3a0;
    border: none;
    border-bottom: 1px solid rgba(224, 216, 203, 0.09);
    border-right: 1px solid rgba(224, 216, 203, 0.03);
    padding: 5px 8px;
    font-size: 8.05pt;
    font-weight: 700;
}

QTableCornerButton::section {
    background: #20262b;
    border: none;
    border-bottom: 1px solid rgba(224, 216, 203, 0.09);
    border-right: 1px solid rgba(224, 216, 203, 0.03);
}

QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid rgba(224, 216, 203, 0.045);
}

QTableWidget::item:hover {
    background: rgba(255, 255, 255, 0.04);
}

QTableWidget::item:selected {
    background: rgba(85, 125, 69, 0.78);
    color: #f8f4ed;
    border-top: 1px solid rgba(255, 255, 255, 0.035);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

QTableWidget::item:selected:hover {
    background: rgba(97, 140, 79, 0.84);
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
