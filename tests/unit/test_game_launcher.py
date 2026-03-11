from __future__ import annotations

from pathlib import Path

import pytest

from sdvmm.services.game_launcher import (
    GameLaunchError,
    launch_game_process,
    resolve_launch_command,
)


def test_resolve_launch_command_blocks_invalid_game_path(tmp_path: Path) -> None:
    with pytest.raises(GameLaunchError, match="Game path is invalid"):
        resolve_launch_command(game_path=tmp_path / "missing", mode="vanilla")


def test_resolve_launch_command_resolves_vanilla_entrypoint(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    executable = game_path / "Stardew Valley"
    executable.write_text("", encoding="utf-8")

    command = resolve_launch_command(game_path=game_path, mode="vanilla")

    assert command.mode == "vanilla"
    assert command.executable_path == executable
    assert command.argv == (str(executable),)


def test_resolve_launch_command_blocks_smapi_when_not_detected(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")

    with pytest.raises(GameLaunchError, match="SMAPI launch is unavailable"):
        resolve_launch_command(game_path=game_path, mode="smapi")


def test_resolve_launch_command_resolves_smapi_shell_script(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")
    smapi = game_path / "StardewModdingAPI.sh"
    smapi.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    command = resolve_launch_command(game_path=game_path, mode="smapi")

    assert command.mode == "smapi"
    assert command.executable_path == smapi
    assert command.argv == ("bash", str(smapi))


def test_launch_game_process_returns_pid_and_sets_working_dir(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    executable = game_path / "Stardew Valley"
    executable.write_text("", encoding="utf-8")
    command = resolve_launch_command(game_path=game_path, mode="vanilla")
    captured: dict[str, object] = {}

    class _FakeProcess:
        pid = 4242

    def _fake_popen(argv, cwd):
        captured["argv"] = argv
        captured["cwd"] = cwd
        return _FakeProcess()

    pid = launch_game_process(command, popen_factory=_fake_popen)

    assert pid == 4242
    assert captured["argv"] == command.argv
    assert captured["cwd"] == str(game_path)


def test_launch_game_process_wraps_oserror(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    executable = game_path / "Stardew Valley"
    executable.write_text("", encoding="utf-8")
    command = resolve_launch_command(game_path=game_path, mode="vanilla")

    def _failing_popen(argv, cwd):
        _ = argv
        _ = cwd
        raise OSError("no execute permission")

    with pytest.raises(GameLaunchError, match="Could not start vanilla launch command"):
        launch_game_process(command, popen_factory=_failing_popen)
