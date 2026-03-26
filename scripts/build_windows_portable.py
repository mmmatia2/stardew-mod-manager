from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PUBLIC_DIST_SLUG = "cinderleaf"
PUBLIC_EXE_NAME = "Cinderleaf.exe"


def _archive_dist_folder(dist_path: Path) -> Path:
    zip_path = dist_path.parent / f"{dist_path.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(
        base_name=str(dist_path),
        format="zip",
        root_dir=str(dist_path.parent),
        base_dir=dist_path.name,
    )
    return zip_path


def _write_sha256(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum_path = Path(f"{path}.sha256")
    checksum_path.write_text(f"{digest} *{path.name}\n", encoding="utf-8")
    return checksum_path


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

    # Authenticode signing belongs here, after the EXE exists and before the
    # portable folder is zipped and hashed for release distribution.
    zip_path = _archive_dist_folder(dist_path)
    checksum_path = _write_sha256(zip_path)

    print(packaged_exe)
    print(qwindows_plugin)
    print(dist_path)
    print(zip_path)
    print(checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
