#!/usr/bin/env python3
"""
build.py - Crea l'eseguibile autonomo con PyInstaller.

    pip install pyinstaller
    python build.py

Il risultato finisce in dist/:
    Windows -> dist/DXRotator.exe
    macOS   -> dist/DXRotator.app  (e dist/DXRotator)
    Linux   -> dist/DXRotator
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller non installato:  pip install pyinstaller")
        return 1

    for d in ("build", "dist"):
        shutil.rmtree(os.path.join(HERE, d), ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "DXRotator",
        "--windowed",
        "--onefile",
        "--paths", HERE,
        "--hidden-import", "serial.tools.list_ports",
    ]
    icon = os.path.join(HERE, "icon.ico" if sys.platform.startswith("win")
                        else "icon.icns")
    if os.path.exists(icon):
        cmd += ["--icon", icon]
    cmd.append(os.path.join(HERE, "run_dxrotator.py"))

    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)


if __name__ == "__main__":
    raise SystemExit(main())
