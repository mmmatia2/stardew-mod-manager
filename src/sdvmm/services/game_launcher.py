from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable, Literal

from sdvmm.domain.environment_codes import GAME_PATH_DETECTED, INVALID_GAME_PATH, SMAPI_DETECTED
from sdvmm.services.environment_detection import detect_game_environment

LaunchMode = Literal["vanilla", "smapi"]

_VANILLA_EXECUTABLE_CANDIDATES = (
    "Stardew Valley",
    "StardewValley",
    "Stardew Valley.exe",
    "StardewValley.exe",
)


class GameLaunchError(ValueError):
    """Raised when local launch command resolution or start fails."""


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    mode: LaunchMode
    executable_path: Path
    argv: tuple[str, ...]


def resolve_launch_command(*, game_path: Path, mode: LaunchMode) -> LaunchCommand:
    status = detect_game_environment(game_path)
    if INVALID_GAME_PATH in status.state_codes or GAME_PATH_DETECTED not in status.state_codes:
        raise GameLaunchError(
            "Game path is invalid or does not contain deterministic Stardew Valley installation evidence."
        )

    if mode == "vanilla":
        executable_path = _resolve_vanilla_executable(status.game_path)
        return LaunchCommand(
            mode="vanilla",
            executable_path=executable_path,
            argv=(str(executable_path),),
        )

    if mode == "smapi":
        if SMAPI_DETECTED not in status.state_codes or status.smapi_path is None:
            raise GameLaunchError("SMAPI launch is unavailable: SMAPI was not detected for this game path.")
        executable_path = status.smapi_path
        if executable_path.suffix.casefold() == ".dll":
            raise GameLaunchError(
                f"SMAPI launch is unavailable: unsupported entrypoint type '{executable_path.name}'."
            )
        if executable_path.suffix.casefold() == ".sh":
            return LaunchCommand(
                mode="smapi",
                executable_path=executable_path,
                argv=("bash", str(executable_path)),
            )
        return LaunchCommand(
            mode="smapi",
            executable_path=executable_path,
            argv=(str(executable_path),),
        )

    raise GameLaunchError(f"Unknown launch mode: {mode}")


def launch_game_process(
    command: LaunchCommand,
    *,
    popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> int:
    try:
        process = popen_factory(
            command.argv,
            cwd=str(command.executable_path.parent),
        )
    except OSError as exc:
        raise GameLaunchError(
            f"Could not start {command.mode} launch command '{' '.join(command.argv)}': {exc}"
        ) from exc

    if process.pid is None:
        return -1
    return int(process.pid)


def _resolve_vanilla_executable(game_path: Path) -> Path:
    for name in _VANILLA_EXECUTABLE_CANDIDATES:
        candidate = game_path / name
        if candidate.exists() and candidate.is_file():
            return candidate
    raise GameLaunchError(
        f"Vanilla launch is unavailable: no launchable Stardew executable was found in {game_path}."
    )
