"""Ponto de entrada do executavel.

O PyInstaller precisa de um script de topo para empacotar; ele so chama o
`main` do app. Em dev, prefira `uv run wt-app` -- este arquivo existe para o
build.
"""

from __future__ import annotations

import sys

from webtoon_ocr.app import main

if __name__ == "__main__":
    sys.exit(main())
