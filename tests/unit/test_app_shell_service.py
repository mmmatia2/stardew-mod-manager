from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from typing import Literal

import pytest

import sdvmm.app.shell_service as shell_service_module
from sdvmm.app.shell_service import (
    ARCHIVE_SOURCE_REAL,
    ARCHIVE_SOURCE_SANDBOX,
    INSTALL_TARGET_CONFIGURED_REAL_MODS,
    INSTALL_TARGET_SANDBOX_MODS,
    SCAN_TARGET_CONFIGURED_REAL_MODS,
    SCAN_TARGET_SANDBOX_MODS,
    AppShellError,
    AppShellService,
)
from sdvmm.domain.models import (
    AppConfig,
    ModDiscoveryEntry,
    ModDiscoveryResult,
    ModUpdateReport,
    ModUpdateStatus,
    NexusIntegrationStatus,
    RemoteModLink,
    SmapiUpdateStatus,
)
from sdvmm.domain.update_codes import UpdateState
from sdvmm.services.app_state_store import save_app_config


def test_load_startup_config_returns_none_when_state_absent(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    state = service.load_startup_config()

    assert state.config is None
    assert state.message is not None
    assert "No saved configuration found" in state.message


def test_load_startup_config_reports_invalid_state_file(tmp_path: Path) -> None:
    state_file = tmp_path / "app-state.json"
    state_file.write_text("{invalid", encoding="utf-8")
    service = AppShellService(state_file=state_file)

    state = service.load_startup_config()

    assert state.config is None
    assert state.message is not None
    assert "Could not load saved config" in state.message


def test_save_mods_directory_bootstraps_config_when_missing(tmp_path: Path) -> None:
    mods_path = tmp_path / "Mods"
    mods_path.mkdir()

    state_file = tmp_path / "state" / "app-state.json"
    service = AppShellService(state_file=state_file)

    config = service.save_mods_directory(str(mods_path), existing_config=None)

    assert config.mods_path == mods_path
    assert config.game_path == mods_path.parent
    assert config.app_data_path == state_file.parent


def test_save_mods_directory_preserves_existing_non_mod_paths(tmp_path: Path) -> None:
    first_mods = tmp_path / "ModsA"
    second_mods = tmp_path / "ModsB"
    first_mods.mkdir()
    second_mods.mkdir()

    existing = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=first_mods,
        app_data_path=tmp_path / "AppData",
    )

    state_file = tmp_path / "state" / "app-state.json"
    save_app_config(state_file, existing)

    service = AppShellService(state_file=state_file)
    updated = service.save_mods_directory(str(second_mods), existing_config=existing)

    assert updated.mods_path == second_mods
    assert updated.game_path == existing.game_path
    assert updated.app_data_path == existing.app_data_path


def test_scan_rejects_missing_mods_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    with pytest.raises(AppShellError, match="does not exist"):
        service.scan(str(tmp_path / "missing"))


def test_scan_returns_inventory_for_valid_mods_path(tmp_path: Path, mods_case_path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    inventory = service.scan(str(mods_case_path("valid_manifest")))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.VisibleFish"


def test_scan_with_target_uses_configured_real_mods_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    configured_mods = tmp_path / "ConfiguredMods"
    sandbox_mods = tmp_path / "SandboxMods"
    _create_mod(configured_mods, "ConfiguredMod", "Real.Mod")
    _create_mod(sandbox_mods, "SandboxMod", "Sandbox.Mod")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(configured_mods),
        sandbox_mods_path_text=str(sandbox_mods),
    )

    assert result.target_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert result.scan_path == configured_mods
    assert len(result.inventory.mods) == 1
    assert result.inventory.mods[0].unique_id == "Real.Mod"


def test_scan_with_target_uses_sandbox_mods_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    configured_mods = tmp_path / "ConfiguredMods"
    sandbox_mods = tmp_path / "SandboxMods"
    _create_mod(configured_mods, "ConfiguredMod", "Real.Mod")
    _create_mod(sandbox_mods, "SandboxMod", "Sandbox.Mod")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(configured_mods),
        sandbox_mods_path_text=str(sandbox_mods),
    )

    assert result.target_kind == SCAN_TARGET_SANDBOX_MODS
    assert result.scan_path == sandbox_mods
    assert len(result.inventory.mods) == 1
    assert result.inventory.mods[0].unique_id == "Sandbox.Mod"


def test_launch_game_vanilla_uses_saved_game_path_when_input_empty(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    game_path.mkdir()
    executable = game_path / "Stardew Valley"
    executable.write_text("", encoding="utf-8")
    config = AppConfig(
        game_path=game_path,
        mods_path=tmp_path / "Mods",
        app_data_path=tmp_path / "AppData",
    )
    captured: dict[str, object] = {}

    def _fake_launch(command):
        captured["command"] = command
        return 31337

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "launch_game_process", _fake_launch)
    try:
        result = service.launch_game_vanilla(game_path_text="", existing_config=config)
    finally:
        monkeypatch.undo()

    command = captured.get("command")
    assert command is not None
    assert result.mode == "vanilla"
    assert result.game_path == game_path
    assert result.executable_path == executable
    assert result.pid == 31337


def test_launch_game_smapi_is_blocked_when_not_detected(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")

    with pytest.raises(AppShellError, match="SMAPI launch is unavailable"):
        service.launch_game_smapi(game_path_text=str(game_path), existing_config=None)


def test_check_smapi_update_status_uses_saved_game_path_when_input_empty(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    game_path.mkdir()
    config = AppConfig(
        game_path=game_path,
        mods_path=tmp_path / "Mods",
        app_data_path=tmp_path / "AppData",
    )

    expected = SmapiUpdateStatus(
        state="up_to_date",
        game_path=game_path,
        smapi_path=game_path / "StardewModdingAPI",
        installed_version="4.5.1",
        latest_version="4.5.1",
        update_page_url="https://example.test/smapi",
        message="SMAPI is up to date.",
    )

    captured: dict[str, Path] = {}

    def _fake_check_smapi_update_status(*, game_path: Path) -> SmapiUpdateStatus:
        captured["game_path"] = game_path
        return expected

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        shell_service_module,
        "check_smapi_update_status_service",
        _fake_check_smapi_update_status,
    )
    try:
        result = service.check_smapi_update_status(game_path_text="", existing_config=config)
    finally:
        monkeypatch.undo()

    assert captured["game_path"] == game_path
    assert result == expected


def test_resolve_smapi_update_page_url_uses_status_url_when_available(tmp_path: Path) -> None:
    _ = tmp_path
    status = SmapiUpdateStatus(
        state="update_available",
        game_path=Path("/tmp/game"),
        smapi_path=Path("/tmp/game/StardewModdingAPI"),
        installed_version="4.4.0",
        latest_version="4.5.1",
        update_page_url="https://example.test/releases/latest",
        message="Update available",
    )

    assert AppShellService.resolve_smapi_update_page_url(status) == "https://example.test/releases/latest"


def test_inspect_zip_rejects_missing_package_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    with pytest.raises(AppShellError, match="does not exist"):
        service.inspect_zip(str(tmp_path / "missing.zip"))


def test_inspect_zip_rejects_non_zip_file(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    text_file = tmp_path / "not_zip.txt"
    text_file.write_text("hello", encoding="utf-8")

    with pytest.raises(AppShellError, match="not a .zip package"):
        service.inspect_zip(str(text_file))


def test_inspect_zip_returns_package_result(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    result = service.inspect_zip(str(package))

    assert len(result.mods) == 1
    assert result.mods[0].unique_id == "Pkg.Zip"


def test_inspect_zip_with_inventory_context_resolves_content_pack_for_dependency(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "cp_pack.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "[CP] Pack/manifest.json",
            (
                "{"
                '"Name":"CP Pack",'
                '"UniqueID":"Sample.ContentPack",'
                '"Version":"1.0.0",'
                '"ContentPackFor":{"UniqueID":"Pathoschild.ContentPatcher"}'
                "}"
            ),
        )

    result = service.inspect_zip_with_inventory_context(
        str(package),
        _inventory_with_mod("Pathoschild.ContentPatcher"),
    )

    assert any(
        finding.dependency_unique_id == "Pathoschild.ContentPatcher"
        and finding.state == "satisfied"
        for finding in result.dependency_findings
    )


def test_inspect_zip_with_inventory_context_includes_remote_requirement_guidance(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "simple.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Simple/manifest.json",
            '{"Name":"Simple","UniqueID":"Sample.Simple","Version":"1.0.0"}',
        )

    result = service.inspect_zip_with_inventory_context(str(package), _empty_inventory())

    assert len(result.remote_requirements) == 1
    assert result.remote_requirements[0].unique_id == "Sample.Simple"
    assert result.remote_requirements[0].state == "no_remote_link"


def test_inspect_zip_rejects_invalid_zip_content(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "broken.zip"
    package.write_bytes(b"not a real zip")

    with pytest.raises(AppShellError, match="not a valid zip package"):
        service.inspect_zip(str(package))


def test_build_sandbox_install_plan_rejects_missing_sandbox_dir(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="Sandbox Mods directory does not exist"):
        service.build_sandbox_install_plan(
            str(package),
            str(tmp_path / "missing_sandbox"),
            str(tmp_path / "SandboxArchive"),
            allow_overwrite=False,
        )


def test_build_sandbox_install_plan_blocks_target_matching_configured_real_mods(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    real_mods.mkdir()
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="matches configured real Mods path"):
        service.build_sandbox_install_plan(
            str(package),
            str(real_mods),
            str(tmp_path / "SandboxArchive"),
            allow_overwrite=False,
            configured_real_mods_path=real_mods,
        )


def test_build_sandbox_install_plan_blocks_target_matching_configured_real_mods_via_symlink(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    real_mods.mkdir()

    symlink_target = tmp_path / "AliasMods"
    try:
        symlink_target.symlink_to(real_mods, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlink not available for deterministic path-match test: {exc}")

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="matches configured real Mods path"):
        service.build_sandbox_install_plan(
            str(package),
            str(symlink_target),
            str(tmp_path / "SandboxArchive"),
            allow_overwrite=False,
            configured_real_mods_path=real_mods,
        )


def test_build_sandbox_install_plan_allows_safe_custom_target(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
        configured_real_mods_path=real_mods,
    )

    assert len(plan.entries) == 1
    assert plan.sandbox_mods_path == sandbox
    assert len(plan.remote_requirements) == 1
    assert plan.remote_requirements[0].state == "no_remote_link"


def test_build_install_plan_supports_configured_real_mods_destination(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    plan = service.build_install_plan(
        package_path_text=str(package),
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox),
        real_archive_path_text="",
        sandbox_archive_path_text="",
        allow_overwrite=False,
        configured_real_mods_path=real_mods,
    )

    assert plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert plan.sandbox_mods_path == real_mods
    assert plan.sandbox_archive_path == real_mods.parent / ".sdvmm-real-archive"
    assert len(plan.entries) == 1
    assert plan.entries[0].action == "install_new"


def test_build_install_plan_uses_archive_overwrite_for_real_mods_destination(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox.mkdir()
    (real_mods / "Mod").mkdir()

    package = tmp_path / "update.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"2.0.0"}',
        )

    plan = service.build_install_plan(
        package_path_text=str(package),
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox),
        real_archive_path_text="",
        sandbox_archive_path_text="",
        allow_overwrite=True,
        configured_real_mods_path=real_mods,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].action == "overwrite_with_archive"
    assert plan.entries[0].archive_path is not None
    assert plan.entries[0].archive_path.parent == real_mods.parent / ".sdvmm-real-archive"


def test_execute_real_mods_plan_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )
        archive.writestr("Mod/file.txt", "hello")

    plan = service.build_install_plan(
        package_path_text=str(package),
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox),
        real_archive_path_text="",
        sandbox_archive_path_text="",
        allow_overwrite=False,
        configured_real_mods_path=real_mods,
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_sandbox_install_plan(plan)

    result = service.execute_sandbox_install_plan(
        plan,
        confirm_real_destination=True,
    )
    assert result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert result.scan_context_path == real_mods
    assert (real_mods / "Mod" / "file.txt").read_text(encoding="utf-8") == "hello"


def test_build_mod_removal_plan_for_sandbox_destination(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )

    assert plan.destination_kind == SCAN_TARGET_SANDBOX_MODS
    assert plan.mods_path == sandbox_mods
    assert plan.archive_path == sandbox_archive
    assert plan.target_mod_path == sandbox_mods / "ToRemove"


def test_build_mod_removal_plan_for_real_destination_uses_real_archive_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "ToRemove"),
    )

    assert plan.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert plan.mods_path == real_mods
    assert plan.archive_path == real_archive
    assert plan.target_mod_path == real_mods / "ToRemove"


def test_execute_mod_removal_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_mod_removal(plan, confirm_removal=False)


def test_execute_mod_removal_moves_sandbox_mod_to_archive_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")
    _create_mod(sandbox_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )
    result = service.execute_mod_removal(plan, confirm_removal=True)

    assert result.destination_kind == SCAN_TARGET_SANDBOX_MODS
    assert result.removed_target == sandbox_mods / "ToRemove"
    assert not (sandbox_mods / "ToRemove").exists()
    assert result.archived_target.parent == sandbox_archive
    assert result.archived_target.exists()
    assert (result.archived_target / "manifest.json").exists()
    assert result.scan_context_path == sandbox_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Keep"}


def test_execute_mod_removal_moves_real_mod_to_archive_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "ToRemove", "Sample.Remove")
    _create_mod(real_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "ToRemove"),
    )
    result = service.execute_mod_removal(plan, confirm_removal=True)

    assert result.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert result.removed_target == real_mods / "ToRemove"
    assert not (real_mods / "ToRemove").exists()
    assert result.archived_target.parent == real_archive
    assert result.archived_target.exists()
    assert result.scan_context_path == real_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Keep"}


def test_list_archived_entries_includes_real_archive_entries(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived = real_archive / "RealMod__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Real Mod","UniqueID":"Sample.RealArchived","Version":"2.1.0"}',
        encoding="utf-8",
    )

    entries = service.list_archived_entries(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )

    real_entries = [item for item in entries if item.source_kind == ARCHIVE_SOURCE_REAL]
    assert len(real_entries) == 1
    item = real_entries[0]
    assert item.archived_folder_name == "RealMod__sdvmm_archive_001"
    assert item.target_folder_name == "RealMod"
    assert item.mod_name == "Real Mod"
    assert item.unique_id == "Sample.RealArchived"
    assert item.version == "2.1.0"


def test_list_archived_entries_includes_sandbox_archive_entries(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "SandboxMod__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Sandbox Mod","UniqueID":"Sample.SandboxArchived","Version":"1.2.3"}',
        encoding="utf-8",
    )

    entries = service.list_archived_entries(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )

    sandbox_entries = [item for item in entries if item.source_kind == ARCHIVE_SOURCE_SANDBOX]
    assert len(sandbox_entries) == 1
    item = sandbox_entries[0]
    assert item.archived_folder_name == "SandboxMod__sdvmm_archive_001"
    assert item.target_folder_name == "SandboxMod"
    assert item.mod_name == "Sandbox Mod"
    assert item.unique_id == "Sample.SandboxArchived"
    assert item.version == "1.2.3"


def test_execute_archive_restore_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "RestoreMe__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Me","UniqueID":"Sample.RestoreMe","Version":"1.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_archive_restore(plan, confirm_restore=False)


def test_execute_archive_restore_to_sandbox_moves_entry_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "Keep", "Sample.Keep")
    archived = sandbox_archive / "RestoreMe__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Me","UniqueID":"Sample.RestoreMe","Version":"1.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )
    result = service.execute_archive_restore(plan, confirm_restore=True)

    assert result.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert result.restored_target == sandbox_mods / "RestoreMe"
    assert result.restored_target.exists()
    assert not archived.exists()
    assert result.scan_context_path == sandbox_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {
        "Sample.Keep",
        "Sample.RestoreMe",
    }


def test_execute_archive_restore_to_real_moves_entry_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "Keep", "Sample.Keep")
    archived = real_archive / "RestoreReal__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Real","UniqueID":"Sample.RestoreReal","Version":"3.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_REAL,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )
    result = service.execute_archive_restore(plan, confirm_restore=True)

    assert result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert result.restored_target == real_mods / "RestoreReal"
    assert result.restored_target.exists()
    assert not archived.exists()
    assert result.scan_context_path == real_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {
        "Sample.Keep",
        "Sample.RestoreReal",
    }


def test_build_archive_restore_plan_inferrs_real_destination_even_if_saved_install_target_is_sandbox(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived = real_archive / "RestoreReal__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Real","UniqueID":"Sample.RestoreReal","Version":"3.0.0"}',
        encoding="utf-8",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "appdata",
        sandbox_mods_path=sandbox_mods,
        real_archive_path=real_archive,
        install_target=INSTALL_TARGET_SANDBOX_MODS,
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_REAL,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        existing_config=existing_config,
    )

    assert plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert plan.destination_mods_path == real_mods
    assert plan.destination_target_path == real_mods / "RestoreReal"


def test_build_archive_restore_plan_inferrs_sandbox_destination_even_if_saved_install_target_is_real(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "RestoreSandbox__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Sandbox","UniqueID":"Sample.RestoreSandbox","Version":"1.0.0"}',
        encoding="utf-8",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "appdata",
        sandbox_mods_path=sandbox_mods,
        sandbox_archive_path=sandbox_archive,
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        existing_config=existing_config,
    )

    assert plan.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert plan.destination_mods_path == sandbox_mods
    assert plan.destination_target_path == sandbox_mods / "RestoreSandbox"


def test_build_archive_restore_plan_blocks_when_restore_target_exists(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived = real_archive / "RestoreReal__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Real","UniqueID":"Sample.RestoreReal","Version":"3.0.0"}',
        encoding="utf-8",
    )
    _create_mod(real_mods, "RestoreReal", "Sample.Existing")

    with pytest.raises(AppShellError, match="Restore target already exists"):
        service.build_archive_restore_plan(
            source_kind=ARCHIVE_SOURCE_REAL,
            archived_path_text=str(archived),
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text=str(real_archive),
            sandbox_archive_path_text="",
        )


def test_list_mod_rollback_candidates_matches_real_destination_by_unique_id_and_folder(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()

    _create_mod(real_mods, "SampleMod", "Sample.Mod")
    _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    _create_archived_entry(
        real_archive / "OtherFolder__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="0.9.0",
    )
    _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_002",
        unique_id="Different.Mod",
        version="1.0.0",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "AppData",
        sandbox_mods_path=sandbox_mods,
        install_target=INSTALL_TARGET_SANDBOX_MODS,
    )

    candidates = service.list_mod_rollback_candidates(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "SampleMod"),
        mod_unique_id_text="Sample.Mod",
        existing_config=existing_config,
    )

    assert len(candidates) == 1
    assert candidates[0].archived_path == real_archive / "SampleMod__sdvmm_archive_001"


def test_list_mod_rollback_candidates_matches_sandbox_destination_by_unique_id_and_folder(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()

    _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")
    _create_archived_entry(
        sandbox_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    _create_archived_entry(
        sandbox_archive / "SampleMod__sdvmm_archive_002",
        unique_id="Different.Mod",
        version="1.0.0",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "AppData",
        sandbox_mods_path=sandbox_mods,
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
    )

    candidates = service.list_mod_rollback_candidates(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "SampleMod"),
        mod_unique_id_text="Sample.Mod",
        existing_config=existing_config,
    )

    assert len(candidates) == 1
    assert candidates[0].archived_path == sandbox_archive / "SampleMod__sdvmm_archive_001"


def test_execute_mod_rollback_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "SampleMod", "Sample.Mod")
    candidate = _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )

    plan = service.build_mod_rollback_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "SampleMod"),
        mod_unique_id_text="Sample.Mod",
        mod_version_text="2.0.0",
        archived_candidate_path_text=str(candidate),
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_mod_rollback(plan, confirm_rollback=False)


def test_execute_mod_rollback_archives_current_then_restores_archived_version_and_rescans(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    current = _create_mod(real_mods, "SampleMod", "Sample.Mod")
    (current / "version-marker.txt").write_text("current-2.0.0", encoding="utf-8")
    candidate = _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    (candidate / "version-marker.txt").write_text("archived-1.0.0", encoding="utf-8")
    _create_mod(real_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_rollback_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(current),
        mod_unique_id_text="Sample.Mod",
        mod_version_text="2.0.0",
        archived_candidate_path_text=str(candidate),
    )
    result = service.execute_mod_rollback(plan, confirm_rollback=True)

    assert result.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert result.archived_current_target.parent == real_archive
    assert result.archived_current_target.exists()
    assert (result.archived_current_target / "version-marker.txt").read_text(encoding="utf-8") == "current-2.0.0"
    assert result.restored_target == current
    assert (result.restored_target / "version-marker.txt").read_text(encoding="utf-8") == "archived-1.0.0"
    assert result.scan_context_path == real_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Mod", "Sample.Keep"}


def test_execute_mod_rollback_for_sandbox_destination_rescans_sandbox(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    current = _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")
    candidate = _create_archived_entry(
        sandbox_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    _create_mod(sandbox_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_rollback_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(current),
        mod_unique_id_text="Sample.Mod",
        mod_version_text="2.0.0",
        archived_candidate_path_text=str(candidate),
    )
    result = service.execute_mod_rollback(plan, confirm_rollback=True)

    assert result.destination_kind == SCAN_TARGET_SANDBOX_MODS
    assert result.scan_context_path == sandbox_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Mod", "Sample.Keep"}


def test_build_install_plan_blocks_real_destination_mismatch(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    configured_real_mods = tmp_path / "ConfiguredRealMods"
    different_mods = tmp_path / "DifferentMods"
    sandbox = tmp_path / "SandboxMods"
    configured_real_mods.mkdir()
    different_mods.mkdir()
    sandbox.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="must exactly match the configured real Mods path"):
        service.build_install_plan(
            package_path_text=str(package),
            install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
            configured_mods_path_text=str(different_mods),
            sandbox_mods_path_text=str(sandbox),
            real_archive_path_text="",
            sandbox_archive_path_text="",
            allow_overwrite=False,
            configured_real_mods_path=configured_real_mods,
        )


def test_build_install_plan_blocks_archive_inside_real_mods_tree(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="must be outside the active Mods directory"):
        service.build_install_plan(
            package_path_text=str(package),
            install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text=str(real_mods / ".sdvmm-archive"),
            sandbox_archive_path_text="",
            allow_overwrite=True,
            configured_real_mods_path=real_mods,
        )


def test_build_install_plan_blocks_archive_inside_sandbox_mods_tree(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="must be outside the active Mods directory"):
        service.build_install_plan(
            package_path_text=str(package),
            install_target=INSTALL_TARGET_SANDBOX_MODS,
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text="",
            sandbox_archive_path_text=str(sandbox_mods / ".sdvmm-archive"),
            allow_overwrite=True,
            configured_real_mods_path=real_mods,
        )


def test_scan_with_target_excludes_configured_archive_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    archive_root = real_mods / ".sdvmm-archive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    archive_root.mkdir()
    _create_mod(real_mods, "Visible", "Sample.Visible")
    _create_mod(archive_root, "Archived", "Sample.Archived")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(archive_root),
    )

    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Visible"}


def test_scan_with_target_excludes_legacy_archive_path_by_default(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    archive_root = real_mods / ".sdvmm-archive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    archive_root.mkdir()
    _create_mod(real_mods, "Visible", "Sample.Visible")
    _create_mod(archive_root, "Archived", "Sample.Archived")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
    )

    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Visible"}


def test_scan_with_target_excludes_sandbox_archive_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = sandbox_mods / ".sdvmm-archive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "Visible", "Sample.Visible")
    _create_mod(sandbox_archive, "Archived", "Sample.Archived")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        sandbox_archive_path_text=str(sandbox_archive),
    )

    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Visible"}


def test_build_sandbox_install_plan_includes_dependency_preflight_warnings(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    package = tmp_path / "missing_dep.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "NeedsDep/manifest.json",
            (
                "{"
                '"Name":"NeedsDep",'
                '"UniqueID":"Pkg.NeedsDep",'
                '"Version":"1.0.0",'
                '"Dependencies":[{"UniqueID":"Pkg.Required","IsRequired":true}]'
                "}"
            ),
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].can_install is False
    assert plan.entries[0].action == "blocked"
    assert any("Missing required dependencies" in item for item in plan.entries[0].warnings)
    assert any("missing required dependency" in item.casefold() for item in plan.plan_warnings)
    assert any(
        finding.state == "missing_required_dependency"
        for finding in plan.dependency_findings
    )


def test_build_sandbox_install_plan_satisfies_content_pack_for_when_provider_exists(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    provider = sandbox / "ContentPatcher"
    provider.mkdir()
    (provider / "manifest.json").write_text(
        '{"Name":"Content Patcher","UniqueID":"Pathoschild.ContentPatcher","Version":"2.0.0"}',
        encoding="utf-8",
    )

    package = tmp_path / "cp_pack.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "[CP] Pack/manifest.json",
            (
                "{"
                '"Name":"CP Pack",'
                '"UniqueID":"Sample.ContentPack",'
                '"Version":"1.0.0",'
                '"ContentPackFor":{"UniqueID":"Pathoschild.ContentPatcher"}'
                "}"
            ),
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].can_install is True
    assert not any("Missing required dependencies" in item for item in plan.entries[0].warnings)
    assert any(
        finding.dependency_unique_id == "Pathoschild.ContentPatcher"
        and finding.state == "satisfied"
        for finding in plan.dependency_findings
    )


def test_build_and_execute_sandbox_install_plan(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )
        archive.writestr("Mod/file.txt", "hello")

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )
    result = service.execute_sandbox_install_plan(plan)

    assert len(result.installed_targets) == 1
    assert result.installed_targets[0] == sandbox / "Mod"
    assert result.archived_targets == ()
    assert result.scan_context_path == sandbox
    assert (sandbox / "Mod" / "file.txt").read_text(encoding="utf-8") == "hello"
    assert len(result.inventory.mods) == 1

    follow_up_scan = service.scan_with_target(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(tmp_path / "ConfiguredMods"),
        sandbox_mods_path_text=str(sandbox),
    )
    assert follow_up_scan.scan_path == result.scan_context_path


def test_build_sandbox_plan_defaults_archive_path_when_empty(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    sandbox.mkdir()
    (sandbox / "Mod").mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        "",
        allow_overwrite=True,
    )

    assert plan.sandbox_archive_path == sandbox.parent / ".sdvmm-sandbox-archive"
    assert plan.entries[0].archive_path == (
        sandbox.parent / ".sdvmm-sandbox-archive" / "Mod__sdvmm_archive_001"
    )


def test_check_updates_returns_no_remote_link_for_unlinked_mod(tmp_path: Path, mods_case_path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    inventory = service.scan(str(mods_case_path("valid_manifest")))

    report = service.check_updates(inventory)

    assert len(report.statuses) == 1
    assert report.statuses[0].state == "no_remote_link"
    assert report.statuses[0].remote_link is None


def test_check_updates_marks_metadata_unavailable_for_nexus_link(
    tmp_path: Path,
    mods_case_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SDVMM_NEXUS_API_KEY", raising=False)
    service = AppShellService(state_file=tmp_path / "app-state.json")
    inventory = service.scan(str(mods_case_path("update_keys_manifest")))

    report = service.check_updates(inventory)

    assert len(report.statuses) == 1
    assert report.statuses[0].state == "metadata_unavailable"
    assert report.statuses[0].remote_link is not None
    assert report.statuses[0].remote_link.provider == "nexus"
    assert "[missing_api_key]" in (report.statuses[0].message or "")


def test_check_updates_passes_resolved_nexus_key_to_metadata_service(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    inventory = _empty_inventory()
    captured: dict[str, object] = {}

    def _fake_check_updates_for_inventory(
        incoming_inventory,
        *,
        fetcher=None,
        timeout_seconds: float = 8.0,
        nexus_api_key: str | None = None,
    ) -> ModUpdateReport:
        captured["inventory"] = incoming_inventory
        captured["nexus_api_key"] = nexus_api_key
        return ModUpdateReport(statuses=tuple())

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "check_updates_for_inventory", _fake_check_updates_for_inventory)
    try:
        config = AppConfig(
            game_path=tmp_path,
            mods_path=tmp_path,
            app_data_path=tmp_path,
            nexus_api_key="persisted-nexus-key",
        )
        _ = service.check_updates(
            inventory,
            nexus_api_key_text="",
            existing_config=config,
        )
    finally:
        monkeypatch.undo()

    assert captured["inventory"] is inventory
    assert captured["nexus_api_key"] == "persisted-nexus-key"


def test_search_mod_discovery_delegates_to_discovery_service(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    captured: dict[str, object] = {}
    expected = ModDiscoveryResult(
        query="spacecore",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="SpaceCore",
                unique_id="spacechase0.SpaceCore",
                author="spacechase0",
                provider="smapi_compatibility_list",
                source_provider="nexus",
                source_page_url="https://www.nexusmods.com/stardewvalley/mods/1348",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )

    def _fake_search_discoverable_mods(
        query: str,
        *,
        fetcher=None,
        timeout_seconds: float = 10.0,
        max_results: int = 50,
    ) -> ModDiscoveryResult:
        _ = fetcher
        _ = timeout_seconds
        captured["query"] = query
        captured["max_results"] = max_results
        return expected

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "search_discoverable_mods", _fake_search_discoverable_mods)
    try:
        result = service.search_mod_discovery(query_text="spacecore", max_results=25)
    finally:
        monkeypatch.undo()

    assert captured["query"] == "spacecore"
    assert captured["max_results"] == 25
    assert result == expected


def test_resolve_discovery_source_page_url_requires_url(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    entry_without_url = ModDiscoveryEntry(
        name="No Link",
        unique_id="sample.NoLink",
        author="Sample",
        provider="smapi_compatibility_list",
        source_provider="none",
        source_page_url=None,
        compatibility_state="compatibility_unknown",
        compatibility_status="unknown",
    )

    with pytest.raises(AppShellError, match="No source page URL is available"):
        _ = service.resolve_discovery_source_page_url(entry_without_url)


def test_correlate_discovery_results_marks_installed_update_and_provider_alignment(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    discovery_result = ModDiscoveryResult(
        query="spacecore",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="SpaceCore",
                unique_id="spacechase0.SpaceCore",
                author="spacechase0",
                provider="smapi_compatibility_list",
                source_provider="nexus",
                source_page_url="https://www.nexusmods.com/stardewvalley/mods/1348",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )
    inventory = _inventory_with_mod("spacechase0.SpaceCore")
    update_report = ModUpdateReport(
        statuses=(
            ModUpdateStatus(
                unique_id="spacechase0.SpaceCore",
                name="SpaceCore",
                folder_path=Path("/tmp/SpaceCore"),
                installed_version="1.0.0",
                remote_version="1.1.0",
                state="update_available",
                remote_link=RemoteModLink(
                    provider="nexus",
                    key="stardewvalley:1348",
                    page_url="https://www.nexusmods.com/stardewvalley/mods/1348",
                    metadata_url="https://api.nexusmods.com/v1/games/stardewvalley/mods/1348.json",
                ),
            ),
        )
    )

    correlations = service.correlate_discovery_results(
        discovery_result=discovery_result,
        inventory=inventory,
        update_report=update_report,
    )

    assert len(correlations) == 1
    item = correlations[0]
    assert item.installed_match_unique_id == "spacechase0.SpaceCore"
    assert item.update_state == "update_available"
    assert item.provider_relation == "provider_aligned"
    assert "matches tracked update provider" in (item.provider_relation_note or "")


def test_correlate_discovery_results_marks_provider_mismatch(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="Sample Mod",
                unique_id="sample.Mod",
                author="author",
                provider="smapi_compatibility_list",
                source_provider="nexus",
                source_page_url="https://www.nexusmods.com/stardewvalley/mods/100",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )
    inventory = _inventory_with_mod("sample.Mod")
    update_report = ModUpdateReport(
        statuses=(
            ModUpdateStatus(
                unique_id="sample.Mod",
                name="Sample Mod",
                folder_path=Path("/tmp/SampleMod"),
                installed_version="1.0.0",
                remote_version="1.0.1",
                state="update_available",
                remote_link=RemoteModLink(
                    provider="github",
                    key="owner/repo",
                    page_url="https://github.com/owner/repo",
                    metadata_url="https://api.github.com/repos/owner/repo/releases/latest",
                ),
            ),
        )
    )

    correlations = service.correlate_discovery_results(
        discovery_result=discovery_result,
        inventory=inventory,
        update_report=update_report,
    )

    assert len(correlations) == 1
    item = correlations[0]
    assert item.provider_relation == "provider_mismatch"
    assert "differs from tracked update provider" in (item.provider_relation_note or "")


def test_correlate_discovery_results_marks_installed_without_update_context(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="Sample Mod",
                unique_id="sample.Mod",
                author="author",
                provider="smapi_compatibility_list",
                source_provider="custom_url",
                source_page_url="https://example.test/mod",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )
    inventory = _inventory_with_mod("sample.Mod")

    correlations = service.correlate_discovery_results(
        discovery_result=discovery_result,
        inventory=inventory,
        update_report=None,
    )

    assert len(correlations) == 1
    item = correlations[0]
    assert item.installed_match_unique_id == "sample.Mod"
    assert item.update_state is None
    assert item.provider_relation == "no_update_provider_context"
    assert "Run Check updates" in item.next_step


def test_get_nexus_status_reports_saved_config_state(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    config = AppConfig(
        game_path=tmp_path,
        mods_path=tmp_path,
        app_data_path=tmp_path,
        nexus_api_key="saved-key",
    )

    status = service.get_nexus_integration_status(
        nexus_api_key_text="",
        existing_config=config,
        validate_connection=False,
    )

    assert status.state == "configured"
    assert status.source == "saved_config"
    assert status.masked_key is not None
    assert "saved-key" not in (status.masked_key or "")


def test_get_nexus_status_uses_environment_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDVMM_NEXUS_API_KEY", "env-key-123456")
    service = AppShellService(state_file=tmp_path / "app-state.json")

    status = service.get_nexus_integration_status(
        nexus_api_key_text="",
        existing_config=None,
        validate_connection=False,
    )

    assert status.state == "configured"
    assert status.source == "environment"


def test_get_nexus_status_validation_reports_auth_failure(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        shell_service_module,
        "check_nexus_connection",
        lambda *, nexus_api_key: NexusIntegrationStatus(
            state="invalid_auth_failure",
            source="entered",
            masked_key="abcd...1234",
            message="[auth_failure] HTTP 401",
        ),
    )
    try:
        status = service.get_nexus_integration_status(
            nexus_api_key_text="abcd-1234",
            existing_config=None,
            validate_connection=True,
        )
    finally:
        monkeypatch.undo()

    assert status.state == "invalid_auth_failure"


def test_save_operational_config_persists_paths_and_scan_target(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    mods = tmp_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    archive = tmp_path / "SandboxArchive"
    real_archive = tmp_path / "RealArchive"
    downloads = tmp_path / "Downloads"
    mods.mkdir()
    sandbox.mkdir()
    archive.mkdir()
    real_archive.mkdir()
    downloads.mkdir()

    saved = service.save_operational_config(
        game_path_text=str(mods.parent),
        mods_dir_text=str(mods),
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive),
        watched_downloads_path_text=str(downloads),
        real_archive_path_text=str(real_archive),
        nexus_api_key_text="persisted-key",
        scan_target="sandbox_mods",
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        existing_config=None,
    )

    assert saved.mods_path == mods
    assert saved.sandbox_mods_path == sandbox
    assert saved.sandbox_archive_path == archive
    assert saved.real_archive_path == real_archive
    assert saved.watched_downloads_path == downloads
    assert saved.nexus_api_key == "persisted-key"
    assert saved.scan_target == "sandbox_mods"
    assert saved.install_target == INSTALL_TARGET_CONFIGURED_REAL_MODS

    reloaded = AppShellService(state_file=tmp_path / "app-state.json").load_startup_config()
    assert reloaded.config is not None
    assert reloaded.config.sandbox_mods_path == sandbox
    assert reloaded.config.sandbox_archive_path == archive
    assert reloaded.config.real_archive_path == real_archive
    assert reloaded.config.watched_downloads_path == downloads
    assert reloaded.config.nexus_api_key == "persisted-key"
    assert reloaded.config.scan_target == "sandbox_mods"
    assert reloaded.config.install_target == INSTALL_TARGET_CONFIGURED_REAL_MODS


def test_save_operational_config_can_derive_mods_path_from_game_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    archive = tmp_path / "SandboxArchive"
    downloads = tmp_path / "Downloads"
    game_path.mkdir()
    mods.mkdir()
    sandbox.mkdir()
    archive.mkdir()
    downloads.mkdir()

    saved = service.save_operational_config(
        game_path_text=str(game_path),
        mods_dir_text="",
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive),
        watched_downloads_path_text=str(downloads),
        nexus_api_key_text="",
        scan_target="configured_real_mods",
        existing_config=None,
    )

    assert saved.game_path == game_path
    assert saved.mods_path == mods
    assert saved.install_target == INSTALL_TARGET_SANDBOX_MODS


def test_save_operational_config_defaults_archive_paths_outside_mods_trees(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    downloads = tmp_path / "Downloads"
    game_path.mkdir()
    mods.mkdir()
    sandbox.mkdir()
    downloads.mkdir()

    saved = service.save_operational_config(
        game_path_text=str(game_path),
        mods_dir_text=str(mods),
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text="",
        watched_downloads_path_text=str(downloads),
        real_archive_path_text="",
        nexus_api_key_text="",
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        install_target=INSTALL_TARGET_SANDBOX_MODS,
        existing_config=None,
    )

    assert saved.real_archive_path == mods.parent / ".sdvmm-real-archive"
    assert saved.sandbox_archive_path == sandbox.parent / ".sdvmm-sandbox-archive"


def test_save_operational_config_blocks_archive_inside_active_mods_tree(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    downloads = tmp_path / "Downloads"
    game_path.mkdir()
    mods.mkdir()
    sandbox.mkdir()
    downloads.mkdir()

    with pytest.raises(AppShellError, match="must be outside the active Mods directory"):
        service.save_operational_config(
            game_path_text=str(game_path),
            mods_dir_text=str(mods),
            sandbox_mods_path_text=str(sandbox),
            sandbox_archive_path_text=str(sandbox / ".sdvmm-archive"),
            watched_downloads_path_text=str(downloads),
            real_archive_path_text=str(mods / ".sdvmm-archive"),
            nexus_api_key_text="",
            scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
            install_target=INSTALL_TARGET_SANDBOX_MODS,
            existing_config=None,
        )


def test_detect_game_environment_reports_smapi_states(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("binary", encoding="utf-8")
    mods.mkdir()

    no_smapi_status = service.detect_game_environment(str(game_path))
    assert "smapi_not_detected" in no_smapi_status.state_codes

    smapi = game_path / "StardewModdingAPI"
    smapi.write_text("x", encoding="utf-8")
    smapi_status = service.detect_game_environment(str(game_path))
    assert "smapi_detected" in smapi_status.state_codes
    assert smapi_status.smapi_path == smapi


def test_detect_game_environment_reports_invalid_game_path_state(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    status = service.detect_game_environment(str(tmp_path / "missing-game-path"))

    assert status.state_codes == ("invalid_game_path",)


def test_detect_game_environment_marks_existing_non_game_directory_as_invalid(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    fake_game_path = tmp_path / "NotStardew"
    fake_game_path.mkdir()
    (fake_game_path / "Mods").mkdir()

    status = service.detect_game_environment(str(fake_game_path))

    assert "invalid_game_path" in status.state_codes
    assert "mods_path_detected" in status.state_codes
    assert "game_path_detected" not in status.state_codes


def test_initialize_and_poll_downloads_watch_detects_new_zip(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    downloads.mkdir()

    known = service.initialize_downloads_watch(str(downloads))
    assert known == ()

    package = downloads / "candidate.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )
    assert len(result.intakes) == 1
    assert result.intakes[0].classification == "new_install_candidate"
    assert len(result.intakes[0].remote_requirements) == 1
    assert result.intakes[0].remote_requirements[0].state == "no_remote_link"


def test_select_intake_result_returns_selected_entry(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    package = downloads / "candidate.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_empty_inventory(),
    )

    selected = service.select_intake_result(intakes=result.intakes, selected_index=0)
    assert selected.package_path == package


def test_select_intake_result_rejects_invalid_index(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    with pytest.raises(AppShellError, match="Select a detected package first"):
        service.select_intake_result(intakes=tuple(), selected_index=0)


def test_build_sandbox_install_plan_from_intake_new_install_candidate(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    downloads.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()

    package = downloads / "new_mod.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "NewMod/manifest.json",
            '{"Name":"New Mod","UniqueID":"Pkg.NewMod","Version":"1.0.0"}',
        )

    poll_result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_empty_inventory(),
    )
    intake = service.select_intake_result(intakes=poll_result.intakes, selected_index=0)

    plan = service.build_sandbox_install_plan_from_intake(
        intake=intake,
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive_root),
        allow_overwrite=False,
    )

    assert plan.package_path == package
    assert len(plan.entries) == 1
    assert plan.entries[0].action == "install_new"
    assert plan.entries[0].can_install is True


def test_build_sandbox_install_plan_from_intake_update_replace_candidate(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    downloads.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()
    (sandbox / "Existing").mkdir()

    package = downloads / "update_mod.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Existing/manifest.json",
            '{"Name":"Existing","UniqueID":"Sample.Exists","Version":"2.0.0"}',
        )

    poll_result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_inventory_with_mod("Sample.Exists"),
    )
    intake = service.select_intake_result(intakes=poll_result.intakes, selected_index=0)
    assert intake.classification == "update_replace_candidate"

    plan = service.build_sandbox_install_plan_from_intake(
        intake=intake,
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive_root),
        allow_overwrite=True,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].action == "overwrite_with_archive"
    assert plan.entries[0].can_install is True


def test_build_sandbox_install_plan_from_intake_rejects_unusable_package(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    downloads.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()

    package = downloads / "broken.zip"
    package.write_bytes(b"not zip")

    poll_result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_empty_inventory(),
    )
    intake = service.select_intake_result(intakes=poll_result.intakes, selected_index=0)
    assert intake.classification == "unusable_package"

    with pytest.raises(AppShellError, match="not actionable for install planning"):
        service.build_sandbox_install_plan_from_intake(
            intake=intake,
            sandbox_mods_path_text=str(sandbox),
            sandbox_archive_path_text=str(archive_root),
            allow_overwrite=False,
        )


def test_correlate_intake_with_updates_marks_update_available_match(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    intake = _intake_result(
        package_path=tmp_path / "update.zip",
        classification="update_replace_candidate",
        matched_installed_unique_ids=("Sample.Exists",),
    )
    report = _update_report(
        _update_status(unique_id="Sample.Exists", state="update_available"),
    )

    correlation = service.correlate_intake_with_updates(
        intake=intake,
        update_report=report,
        guided_update_unique_ids=tuple(),
    )

    assert correlation.actionable is True
    assert correlation.matched_update_available_unique_ids == ("Sample.Exists",)
    assert "update available" in correlation.summary.casefold()
    assert "plan selected intake" in correlation.next_step.casefold()


def test_correlate_intake_with_updates_prefers_guided_update_match(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    intake = _intake_result(
        package_path=tmp_path / "guided_update.zip",
        classification="update_replace_candidate",
        matched_installed_unique_ids=("Sample.Exists",),
    )
    report = _update_report(
        _update_status(unique_id="Sample.Exists", state="update_available"),
    )

    correlation = service.correlate_intake_with_updates(
        intake=intake,
        update_report=report,
        guided_update_unique_ids=("Sample.Exists",),
    )

    assert correlation.matched_guided_update_unique_ids == ("Sample.Exists",)
    assert "guided update target" in correlation.summary.casefold()
    assert correlation.actionable is True


def test_correlate_intake_with_updates_keeps_unusable_non_actionable(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    intake = _intake_result(
        package_path=tmp_path / "broken.zip",
        classification="unusable_package",
        matched_installed_unique_ids=("Sample.Exists",),
    )

    correlation = service.correlate_intake_with_updates(
        intake=intake,
        update_report=None,
        guided_update_unique_ids=tuple(),
    )

    assert correlation.actionable is False
    assert correlation.matched_update_available_unique_ids == ()
    assert "unusable" in correlation.summary.casefold()


def _empty_inventory():
    from sdvmm.domain.models import ModsInventory

    return ModsInventory(
        mods=tuple(),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _inventory_with_mod(unique_id: str):
    from sdvmm.domain.models import InstalledMod, ModsInventory

    mod = InstalledMod(
        unique_id=unique_id,
        name=unique_id,
        version="1.0.0",
        folder_path=Path("/tmp") / unique_id,
        manifest_path=Path("/tmp") / unique_id / "manifest.json",
        dependencies=tuple(),
        update_keys=tuple(),
    )
    return ModsInventory(
        mods=(mod,),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _intake_result(
    *,
    package_path: Path,
    classification: Literal[
        "new_install_candidate",
        "update_replace_candidate",
        "multi_mod_package",
        "unusable_package",
    ],
    matched_installed_unique_ids: tuple[str, ...],
):
    from sdvmm.domain.models import DownloadsIntakeResult

    return DownloadsIntakeResult(
        package_path=package_path,
        classification=classification,
        message="test",
        mods=tuple(),
        matched_installed_unique_ids=matched_installed_unique_ids,
        warnings=tuple(),
        findings=tuple(),
    )


def _update_status(*, unique_id: str, state: UpdateState) -> ModUpdateStatus:
    return ModUpdateStatus(
        unique_id=unique_id,
        name=unique_id,
        folder_path=Path("/tmp") / unique_id,
        installed_version="1.0.0",
        remote_version="2.0.0",
        state=state,
        remote_link=None,
        message=None,
    )


def _update_report(*statuses: ModUpdateStatus) -> ModUpdateReport:
    return ModUpdateReport(statuses=tuple(statuses))


def _create_mod(mods_root: Path, folder_name: str, unique_id: str) -> Path:
    mod_path = mods_root / folder_name
    mod_path.mkdir(parents=True, exist_ok=True)
    (mod_path / "manifest.json").write_text(
        (
            "{"
            f'"Name":"{folder_name}",'
            f'"UniqueID":"{unique_id}",'
            '"Version":"1.0.0"'
            "}"
        ),
        encoding="utf-8",
    )
    return mod_path


def _create_archived_entry(archived_path: Path, *, unique_id: str, version: str) -> Path:
    archived_path.mkdir(parents=True, exist_ok=True)
    (archived_path / "manifest.json").write_text(
        (
            "{"
            f'"Name":"{archived_path.name}",'
            f'"UniqueID":"{unique_id}",'
            f'"Version":"{version}"'
            "}"
        ),
        encoding="utf-8",
    )
    return archived_path
