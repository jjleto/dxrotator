#!/usr/bin/env python3
"""
build.py - Crea l'applicazione autonoma con PyInstaller.

    pip install pyinstaller
    python build.py

Risultato in dist/:

    macOS    dist/DXRotator.app     da trascinare in Applicazioni
    Windows  dist/DXRotator.exe     eseguibile singolo
    Linux    dist/DXRotator         eseguibile singolo

Opzioni:
    --onefile     forza l'eseguibile singolo anche su macOS (avvio piu' lento)
    --console     mantiene la finestra di terminale, utile per vedere gli errori
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "DXRotator"
BUNDLE_ID = "org.iw5dnz.dxrotator"


def _version() -> str:
    sys.path.insert(0, HERE)
    try:
        from dxrotator import __version__
        return __version__
    except Exception:
        return "0.0.0"


def _icon() -> str | None:
    """Percorso dell'icona adatta al sistema, se presente."""
    if sys.platform == "darwin":
        icns = os.path.join(HERE, "icon.icns")
        iconset = os.path.join(HERE, "icon.iconset")
        # su macOS il .icns si assembla dall'iconset con lo strumento di sistema
        if not os.path.exists(icns) and os.path.isdir(iconset):
            try:
                subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns],
                               check=True)
                print("icon.icns generato da icon.iconset")
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        return icns if os.path.exists(icns) else None

    name = "icon.ico" if sys.platform.startswith("win") else "icon.png"
    path = os.path.join(HERE, name)
    return path if os.path.exists(path) else None


def _fix_macos_bundle(app: str) -> None:
    """Completa l'Info.plist del bundle e lo rifirma.

    - NSAppSleepDisabled: macOS non mette DXRotator in App Nap quando non è
      in primo piano (timer rallentati = rotazione che parte in ritardo).
    - Versione reale al posto dello 0.0.0 lasciato da PyInstaller.

    Cambiare l'Info.plist invalida la firma ad hoc di PyInstaller: su Apple
    Silicon un bundle con firma non valida non parte, quindi si rifirma.
    """
    plist = os.path.join(app, "Contents", "Info.plist")
    with open(plist, "rb") as fh:
        info = plistlib.load(fh)
    info["NSAppSleepDisabled"] = True
    info["CFBundleShortVersionString"] = _version()
    info["CFBundleVersion"] = _version()
    with open(plist, "wb") as fh:
        plistlib.dump(info, fh)
    print(f"Info.plist: NSAppSleepDisabled, versione {_version()}")
    try:
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app],
                       check=True)
        print("Bundle rifirmato (firma ad hoc)")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"ATTENZIONE: rifirma non riuscita ({exc}).")
        print(f"  Esegui a mano:  codesign --force --deep --sign - '{app}'")


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller non installato:  pip install pyinstaller")
        return 1

    args = sys.argv[1:]
    force_onefile = "--onefile" in args
    console = "--console" in args

    for d in ("build", "dist"):
        shutil.rmtree(os.path.join(HERE, d), ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", APP_NAME,
        "--paths", HERE,
        "--hidden-import", "serial.tools.list_ports",
        # moduli Qt che non servono: tolti, il pacchetto dimagrisce parecchio
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "tkinter",
    ]

    cmd.append("--console" if console else "--windowed")

    # Su macOS il bundle .app in forma di cartella parte subito; con --onefile
    # l'archivio va scompattato a ogni avvio e l'attesa si sente.
    if sys.platform == "darwin" and not force_onefile:
        cmd += ["--osx-bundle-identifier", BUNDLE_ID]
    else:
        cmd.append("--onefile")

    icon = _icon()
    if icon:
        cmd += ["--icon", icon]
    else:
        print("Nessuna icona trovata: genera con  python tools/make_icon.py")

    cmd.append(os.path.join(HERE, "run_dxrotator.py"))

    print(f"{APP_NAME} {_version()} — {' '.join(cmd[2:])}\n")
    rc = subprocess.call(cmd, cwd=HERE)
    if rc != 0:
        return rc

    print()
    if sys.platform == "darwin" and not force_onefile:
        app = os.path.join(HERE, "dist", f"{APP_NAME}.app")
        _fix_macos_bundle(app)
        print(f"Fatto: {app}")
        print("Trascinala in Applicazioni. Al primo avvio, se macOS la blocca,")
        print("aprila con tasto destro → Apri, oppure esegui:")
        print(f"  xattr -dr com.apple.quarantine '{app}'")
        print()
        print("Se non arrivano i dati da WSJT-X, autorizza DXRotator in")
        print("Impostazioni di Sistema → Privacy e sicurezza → Rete locale.")
    else:
        print("Fatto: cartella dist/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
