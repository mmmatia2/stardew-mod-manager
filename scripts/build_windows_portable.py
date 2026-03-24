from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

PUBLIC_DIST_SLUG = "cinderleaf"
PUBLIC_EXE_NAME = "Cinderleaf.exe"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject_path = repo_root / "pyproject.toml"
    spec_path = repo_root / "packaging" / "sdvmm_windows_portable.spec"

    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
    version = project["version"]
    dist_path = repo_root / "dist" / f"{PUBLIC_DIST_SLUG}-{version}-windows-portable"
    work_path = repo_root / "build" / "pyinstaller"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--distpath={repo_root / 'dist'}",
        f"--workpath={work_path}",
        str(spec_path),
    ]
    subprocess.run(command, cwd=repo_root, check=True)
    packaged_exe = dist_path / PUBLIC_EXE_NAME
    qwindows_plugin = (
        dist_path
        / "_internal"
        / "PySide6"
        / "plugins"
        / "platforms"
        / "qwindows.dll"
    )
    if not packaged_exe.exists():
        raise RuntimeError(f"Packaged executable not found: {packaged_exe}")
    if not qwindows_plugin.exists():
        raise RuntimeError(
            "Qt Windows platform plugin is missing from packaged output: "
            f"{qwindows_plugin}"
        )

    print(packaged_exe)
    print(qwindows_plugin)
    print(dist_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
