from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from sdvmm.services.package_inspector import inspect_zip_package


def test_direct_single_mod_package_is_detected(tmp_path: Path) -> None:
    package = _build_zip(
        tmp_path / "direct.zip",
        {
            "DirectMod/manifest.json": '{"Name":"Direct","UniqueID":"Pkg.Direct","Version":"1.0.0"}',
        },
    )

    result = inspect_zip_package(package)

    assert len(result.mods) == 1
    assert result.mods[0].unique_id == "Pkg.Direct"
    assert result.findings[0].kind == "direct_single_mod_package"


def test_nested_single_mod_package_is_detected(tmp_path: Path) -> None:
    package = _build_zip(
        tmp_path / "nested.zip",
        {
            "Wrapper/NestedMod/manifest.json": '{"Name":"Nested","UniqueID":"Pkg.Nested","Version":"1.0.0"}',
        },
    )

    result = inspect_zip_package(package)

    assert len(result.mods) == 1
    assert result.mods[0].unique_id == "Pkg.Nested"
    assert result.findings[0].kind == "nested_single_mod_package"


def test_multi_mod_package_is_detected(tmp_path: Path) -> None:
    package = _build_zip(
        tmp_path / "multi.zip",
        {
            "Pack/ModA/manifest.json": '{"Name":"A","UniqueID":"Pkg.A","Version":"1.0.0"}',
            "Pack/ModB/manifest.json": '{"Name":"B","UniqueID":"Pkg.B","Version":"1.0.0"}',
        },
    )

    result = inspect_zip_package(package)

    assert len(result.mods) == 2
    assert result.findings[0].kind == "multi_mod_package"


def test_invalid_manifest_package_is_detected(tmp_path: Path) -> None:
    package = _build_zip(
        tmp_path / "invalid.zip",
        {
            "Broken/manifest.json": '{"Name":"Broken","UniqueID":,"Version":"1.0.0"}',
        },
    )

    result = inspect_zip_package(package)

    assert result.mods == ()
    assert result.findings[0].kind == "invalid_manifest_package"
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "malformed_manifest"


def test_no_manifest_package_is_detected(tmp_path: Path) -> None:
    package = _build_zip(
        tmp_path / "no_manifest.zip",
        {
            "README.txt": "Not a mod",
            "assets/file.png": "x",
        },
    )

    result = inspect_zip_package(package)

    assert result.mods == ()
    assert result.findings[0].kind == "no_usable_manifest_found"


def test_too_deep_package_is_detected(tmp_path: Path) -> None:
    package = _build_zip(
        tmp_path / "too_deep.zip",
        {
            "A/B/C/D/manifest.json": '{"Name":"Deep","UniqueID":"Pkg.Deep","Version":"1.0.0"}',
        },
    )

    result = inspect_zip_package(package)

    assert result.mods == ()
    assert result.findings[0].kind == "too_deep_unsupported_package"


def test_relaxed_manifest_parsing_is_applied_in_zip_inspection(tmp_path: Path) -> None:
    package = _build_zip(
        tmp_path / "relaxed.zip",
        {
            "Relaxed/manifest.json": (
                "\ufeff{\n"
                "  /* comment */\n"
                "  \"Name\": \"Relaxed\",\n"
                "  \"UniqueId\": \"Pkg.Relaxed\",\n"
                "  \"Version\": \"1.0.0\",\n"
                "}\n"
            )
        },
    )

    result = inspect_zip_package(package)

    assert len(result.mods) == 1
    assert result.mods[0].unique_id == "Pkg.Relaxed"
    assert result.warnings == ()


def test_package_inspection_exposes_dependency_preflight_without_inventory_context(
    tmp_path: Path,
) -> None:
    package = _build_zip(
        tmp_path / "dep.zip",
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

    result = inspect_zip_package(package)

    assert len(result.dependency_findings) == 1
    assert result.dependency_findings[0].state == "unresolved_dependency_context"


def test_package_inspection_preserves_update_keys_for_remote_awareness(tmp_path: Path) -> None:
    package_path = tmp_path / "package.zip"
    _build_zip(
        package_path,
        {
            "ModA/manifest.json": (
                "{"
                '"Name":"Mod A",'
                '"UniqueID":"Sample.ModA",'
                '"Version":"1.0.0",'
                '"UpdateKeys":["Nexus:12345"]'
                "}"
            )
        },
    )

    result = inspect_zip_package(package_path)

    assert len(result.mods) == 1
    assert result.mods[0].update_keys == ("Nexus:12345",)


def test_package_inspection_surfaces_content_pack_for_dependency_without_inventory_context(
    tmp_path: Path,
) -> None:
    package = _build_zip(
        tmp_path / "cp_pack.zip",
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

    result = inspect_zip_package(package)

    assert len(result.dependency_findings) == 1
    finding = result.dependency_findings[0]
    assert finding.dependency_unique_id == "Pathoschild.ContentPatcher"
    assert finding.required is True
    assert finding.state == "unresolved_dependency_context"


def _build_zip(zip_path: Path, files: dict[str, str]) -> Path:
    with ZipFile(zip_path, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)

    return zip_path
