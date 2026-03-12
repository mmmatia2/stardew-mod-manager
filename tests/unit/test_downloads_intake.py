from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from sdvmm.domain.models import InstalledMod, ModsInventory
from sdvmm.services.downloads_intake import initialize_known_zip_paths, poll_watched_directory


def test_initialize_known_zip_paths_returns_existing_zip_files(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    watched.mkdir()
    _build_zip(watched / "a.zip", {"A/manifest.json": _manifest("A", "Pkg.A", "1.0.0")})
    _build_zip(watched / "b.zip", {"B/manifest.json": _manifest("B", "Pkg.B", "1.0.0")})
    (watched / "note.txt").write_text("x", encoding="utf-8")

    known = initialize_known_zip_paths(watched)

    assert [path.name for path in known] == ["a.zip", "b.zip"]


def test_initialize_known_zip_paths_includes_nested_zip_files(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    nested = watched / "Nexus" / "Collections"
    nested.mkdir(parents=True)
    _build_zip(
        nested / "nested.zip",
        {"Nested/manifest.json": _manifest("Nested", "Pkg.Nested", "1.0.0")},
    )

    known = initialize_known_zip_paths(watched)

    assert len(known) == 1
    assert known[0].name == "nested.zip"
    assert known[0].parent == nested


def test_poll_detects_new_valid_package_and_classifies_new_install(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    watched.mkdir()

    known = initialize_known_zip_paths(watched)
    _build_zip(
        watched / "new_mod.zip",
        {"NewMod/manifest.json": _manifest("New Mod", "Pkg.NewMod", "1.0.0")},
    )

    result = poll_watched_directory(
        watched_path=watched,
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )

    assert len(result.intakes) == 1
    intake = result.intakes[0]
    assert intake.package_path.name == "new_mod.zip"
    assert intake.classification == "new_install_candidate"


def test_poll_detects_new_valid_package_in_nested_subdirectory(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    nested = watched / "Nexus"
    nested.mkdir(parents=True)

    known = initialize_known_zip_paths(watched)
    _build_zip(
        nested / "new_mod_nested.zip",
        {"NewMod/manifest.json": _manifest("New Mod", "Pkg.NewMod", "1.0.0")},
    )

    result = poll_watched_directory(
        watched_path=watched,
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )

    assert len(result.intakes) == 1
    intake = result.intakes[0]
    assert intake.package_path.name == "new_mod_nested.zip"
    assert intake.classification == "new_install_candidate"


def test_poll_ignores_non_zip_files(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    watched.mkdir()

    known = initialize_known_zip_paths(watched)
    (watched / "file.txt").write_text("not zip", encoding="utf-8")

    result = poll_watched_directory(
        watched_path=watched,
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )

    assert result.intakes == ()


def test_poll_handles_invalid_zip_as_unusable_package(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    watched.mkdir()

    known = initialize_known_zip_paths(watched)
    (watched / "broken.zip").write_bytes(b"not a zip")

    result = poll_watched_directory(
        watched_path=watched,
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )

    assert len(result.intakes) == 1
    assert result.intakes[0].classification == "unusable_package"


def test_poll_correlates_package_with_installed_mod_by_unique_id(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    watched.mkdir()

    known = initialize_known_zip_paths(watched)
    _build_zip(
        watched / "update_candidate.zip",
        {"Existing/manifest.json": _manifest("Existing", "Sample.Exists", "2.0.0")},
    )

    inventory = _inventory_with_mod("Sample.Exists")

    result = poll_watched_directory(
        watched_path=watched,
        known_zip_paths=known,
        inventory=inventory,
    )

    assert len(result.intakes) == 1
    intake = result.intakes[0]
    assert intake.classification == "update_replace_candidate"
    assert intake.matched_installed_unique_ids == ("Sample.Exists",)


def test_poll_exposes_missing_required_dependency_for_detected_package(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    watched.mkdir()

    known = initialize_known_zip_paths(watched)
    _build_zip(
        watched / "missing_dep.zip",
        {
            "NeedsDep/manifest.json": (
                "{"
                '"Name":"NeedsDep",'
                '"UniqueID":"Pkg.NeedsDep",'
                '"Version":"1.0.0",'
                '"Dependencies":[{"UniqueID":"Pkg.Required","IsRequired":true}]'
                "}"
            )
        },
    )

    result = poll_watched_directory(
        watched_path=watched,
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )

    assert len(result.intakes) == 1
    intake = result.intakes[0]
    assert any(
        finding.state == "missing_required_dependency"
        for finding in intake.dependency_findings
    )


def test_poll_exposes_content_pack_for_required_dependency(tmp_path: Path) -> None:
    watched = tmp_path / "Downloads"
    watched.mkdir()

    known = initialize_known_zip_paths(watched)
    _build_zip(
        watched / "cp_pack.zip",
        {
            "[CP] Pack/manifest.json": (
                "{"
                '"Name":"CP Pack",'
                '"UniqueID":"Sample.ContentPack",'
                '"Version":"1.0.0",'
                '"ContentPackFor":{"UniqueID":"Pathoschild.ContentPatcher"}'
                "}"
            )
        },
    )

    result = poll_watched_directory(
        watched_path=watched,
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )

    assert len(result.intakes) == 1
    intake = result.intakes[0]
    assert any(
        finding.dependency_unique_id == "Pathoschild.ContentPatcher"
        and finding.state == "missing_required_dependency"
        for finding in intake.dependency_findings
    )


def _empty_inventory() -> ModsInventory:
    return ModsInventory(
        mods=tuple(),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _inventory_with_mod(unique_id: str) -> ModsInventory:
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


def _build_zip(zip_path: Path, files: dict[str, str]) -> None:
    with ZipFile(zip_path, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)


def _manifest(name: str, unique_id: str, version: str) -> str:
    return (
        "{"
        f'"Name":"{name}",'
        f'"UniqueID":"{unique_id}",'
        f'"Version":"{version}"'
        "}"
    )
