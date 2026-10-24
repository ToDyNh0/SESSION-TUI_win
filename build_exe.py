"""Monta o executavel unico com o PyInstaller.

Chamado por build.bat / build.sh e pelos Dockerfiles. Fica num script, e nao
direto na linha de comando, porque:

* o separador do --add-data muda entre Windows (;) e Linux (:);
* o Python 3.15 no Windows carrega `python3t.dll` (usada por extensoes abi3t,
  como a do `cryptography`) da pasta `abi3t-compat`, que o PyInstaller ainda
  nao conhece -- sem ela dentro do pacote o .exe nem abre.

    python build_exe.py      ->  dist/session-tui(.exe)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import PyInstaller.__main__

RAIZ = Path(__file__).resolve().parent


def argumentos() -> list[str]:
    args = [
        "--noconfirm",
        "--clean",
        "--log-level", "WARN",
        "--onefile",
        "--console",
        "--noupx",  # executavel comprimido com UPX e falso positivo classico de antivirus
        "--name", "session-tui",
        "--distpath", str(RAIZ / "dist"),
        "--workpath", str(RAIZ / "build"),
        "--specpath", str(RAIZ / "build"),
        "--add-data", f"{RAIZ / 'session_native' / 'wordlist_english.json'}{os.pathsep}session_native",
    ]  # fmt: skip
    for pacote in ("textual", "rich", "textual_image"):
        args += ["--collect-all", pacote]

    icone = RAIZ / "assets" / "session-tui.ico"
    if sys.platform == "win32" and icone.is_file():
        args += ["--icon", str(icone)]

    compat = Path(sys.base_prefix) / "abi3t-compat" / "python3t.dll"
    if compat.is_file():
        args += ["--add-binary", f"{compat}{os.pathsep}."]

    return args + [str(RAIZ / "main.py")]


if __name__ == "__main__":
    PyInstaller.__main__.run(argumentos())
