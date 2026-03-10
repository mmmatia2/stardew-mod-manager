from __future__ import annotations

from sdvmm.services.mod_scanner import scan_mods_directory


def test_valid_manifest_is_loaded(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("valid_manifest"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.VisibleFish"
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "direct_mod"
    assert inventory.scan_entry_findings[0].entry_path.name == "VisibleFish"
    assert inventory.parse_warnings == ()
    assert inventory.duplicate_unique_ids == ()
    assert inventory.missing_required_dependencies == ()


def test_missing_manifest_produces_warning(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("missing_manifest"))

    assert inventory.mods == ()
    assert len(inventory.parse_warnings) == 1
    assert inventory.parse_warnings[0].code == "missing_manifest"
    assert inventory.parse_warnings[0].mod_path.name == "NoManifestMod"
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "missing_manifest"


def test_malformed_manifest_produces_warning(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("malformed_manifest"))

    assert inventory.mods == ()
    assert len(inventory.parse_warnings) == 1
    assert inventory.parse_warnings[0].code == "malformed_manifest"
    assert inventory.parse_warnings[0].mod_path.name == "BrokenJson"
    assert "line" in inventory.parse_warnings[0].message
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "invalid_manifest"


def test_duplicate_unique_id_is_reported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("duplicate_unique_id"))

    assert len(inventory.mods) == 2
    assert len(inventory.duplicate_unique_ids) == 1

    duplicate = inventory.duplicate_unique_ids[0]
    assert duplicate.unique_id == "Sample.Duplicate"
    assert [path.name for path in duplicate.folder_paths] == ["FirstCopy", "SecondCopy"]


def test_duplicate_unique_id_case_difference_is_reported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("duplicate_unique_id_case"))

    assert len(inventory.mods) == 2
    assert len(inventory.duplicate_unique_ids) == 1

    duplicate = inventory.duplicate_unique_ids[0]
    assert duplicate.unique_id == "sample.casesensitive"
    assert [path.name for path in duplicate.folder_paths] == ["LowerCaseMod", "UpperCaseMod"]


def test_missing_dependency_is_visible(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("missing_dependency"))

    assert len(inventory.mods) == 2
    assert len(inventory.missing_required_dependencies) == 1

    finding = inventory.missing_required_dependencies[0]
    assert finding.required_by_unique_id == "Sample.Consumer"
    assert finding.missing_unique_id == "Sample.MissingRequired"
    assert finding.required_by_folder.name == "ConsumerMod"


def test_content_pack_for_dependency_is_visible_in_inventory(tmp_path) -> None:
    mods_root = tmp_path / "Mods"
    mods_root.mkdir()
    content_pack = mods_root / "ContentPack"
    content_pack.mkdir()
    (content_pack / "manifest.json").write_text(
        (
            "{"
            '"Name":"CP Pack",'
            '"UniqueID":"Sample.ContentPack",'
            '"Version":"1.0.0",'
            '"ContentPackFor":{"UniqueID":"Pathoschild.ContentPatcher"}'
            "}"
        ),
        encoding="utf-8",
    )

    inventory = scan_mods_directory(mods_root)

    assert len(inventory.mods) == 1
    assert len(inventory.missing_required_dependencies) == 1
    assert inventory.missing_required_dependencies[0].required_by_unique_id == "Sample.ContentPack"
    assert inventory.missing_required_dependencies[0].missing_unique_id == "Pathoschild.ContentPatcher"


def test_dependency_match_is_case_insensitive(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("dependency_case_match"))

    assert len(inventory.mods) == 2
    assert inventory.missing_required_dependencies == ()


def test_manifest_with_utf8_bom_is_loaded(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("bom_manifest"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.BomMod"
    assert inventory.parse_warnings == ()


def test_manifest_with_comments_and_trailing_commas_is_loaded(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("jsonc_manifest"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.JsoncMod"
    assert inventory.parse_warnings == ()


def test_manifest_with_uniqueid_alias_is_loaded(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("uniqueid_alias_manifest"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.UniqueIdAlias"
    assert inventory.parse_warnings == ()


def test_manifest_update_keys_are_loaded(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("update_keys_manifest"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.UpdateKeys"
    assert inventory.mods[0].update_keys == ("Nexus:12345",)


def test_nested_single_mod_container_is_supported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("nested_single_container"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.NestedSingle"
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "nested_mod_container"
    assert inventory.scan_entry_findings[0].entry_path.name == "DownloadedFolder"


def test_nested_multi_mod_container_is_supported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("nested_multi_container"))

    assert len(inventory.mods) == 2
    assert sorted(mod.unique_id for mod in inventory.mods) == ["Sample.PackA", "Sample.PackB"]
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "multi_mod_container"
    assert inventory.scan_entry_findings[0].entry_path.name == "PackFolder"


def test_nested_two_level_container_is_supported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("nested_two_level_container"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.DeepNested"
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "nested_mod_container"
    assert inventory.scan_entry_findings[0].entry_path.name == "OuterContainer"


def test_top_level_and_nested_mix_is_supported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("top_level_nested_mix"))

    assert len(inventory.mods) == 2
    assert sorted(mod.unique_id for mod in inventory.mods) == [
        "Sample.Direct",
        "Sample.NestedInMix",
    ]
    assert len(inventory.scan_entry_findings) == 2
    assert {finding.kind for finding in inventory.scan_entry_findings} == {
        "direct_mod",
        "nested_mod_container",
    }


def test_no_manifest_in_allowed_depth_is_reported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("no_manifest_allowed_depth"))

    assert inventory.mods == ()
    assert len(inventory.parse_warnings) == 1
    assert inventory.parse_warnings[0].code == "missing_manifest"
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "missing_manifest"
    assert inventory.scan_entry_findings[0].entry_path.name == "NoManifestRoot"


def test_manifest_deeper_than_two_nested_levels_is_not_loaded(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("too_deep_nested_manifest"))

    assert inventory.mods == ()
    assert len(inventory.parse_warnings) == 1
    assert inventory.parse_warnings[0].code == "missing_manifest"
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "missing_manifest"
    assert inventory.scan_entry_findings[0].entry_path.name == "DeepWrapper"


def test_invalid_manifest_in_nested_location_is_reported(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("invalid_manifest_nested"))

    assert inventory.mods == ()
    assert len(inventory.parse_warnings) == 1
    assert inventory.parse_warnings[0].code == "invalid_manifest"
    assert "UniqueID must be a non-empty string" in inventory.parse_warnings[0].message
    assert len(inventory.scan_entry_findings) == 1
    assert inventory.scan_entry_findings[0].kind == "invalid_manifest"
    assert "invalid_manifest" in inventory.scan_entry_findings[0].message


def test_non_mod_files_are_ignored_safely(mods_case_path) -> None:
    inventory = scan_mods_directory(mods_case_path("non_mod_ignored"))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.RealMod"
    assert [path.name for path in inventory.ignored_entries] == ["notes.txt"]
    assert inventory.parse_warnings == ()


def test_scan_excludes_archive_root_from_active_results(tmp_path) -> None:
    mods_root = tmp_path / "Mods"
    mods_root.mkdir()
    archive_root = mods_root / ".sdvmm-archive"
    archive_root.mkdir()

    active_mod = mods_root / "ActiveMod"
    active_mod.mkdir()
    (active_mod / "manifest.json").write_text(
        '{"Name":"Active","UniqueID":"Sample.Active","Version":"1.0.0"}',
        encoding="utf-8",
    )

    archived_mod = archive_root / "ArchivedMod"
    archived_mod.mkdir()
    (archived_mod / "manifest.json").write_text(
        '{"Name":"Archived","UniqueID":"Sample.Archived","Version":"1.0.0"}',
        encoding="utf-8",
    )

    inventory = scan_mods_directory(mods_root, excluded_paths=(archive_root,))

    assert {mod.unique_id for mod in inventory.mods} == {"Sample.Active"}
    assert any(path.name == ".sdvmm-archive" for path in inventory.ignored_entries)
