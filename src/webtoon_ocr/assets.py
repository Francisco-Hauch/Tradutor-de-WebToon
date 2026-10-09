"""Onde estao os arquivos de asset, em dev e dentro do executavel.

O PyInstaller descompacta os dados em `sys._MEIPASS` em tempo de execucao;
em dev os assets ficam em `assets/` na raiz do repo. `asset_path` acha o
arquivo nos dois casos, e as funcoes devolvem um QIcon ja pronto (com um
fallback desenhado em codigo, para o app nunca depender de o arquivo existir).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def _base_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    # src/webtoon_ocr/assets.py -> raiz do repo
    return Path(__file__).resolve().parents[2]


def asset_path(name: str) -> Path:
    """Caminho de um asset, procurando em `assets/` e na raiz do bundle."""
    base = _base_dir()
    for candidate in (base / "assets" / name, base / name):
        if candidate.exists():
            return candidate
    return base / "assets" / name  # inexistente; quem chama trata


def _drawn_icon() -> QIcon:
    """Fallback: o mesmo balaozinho azul, desenhado sem arquivo."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(40, 120, 220))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 8, 56, 40, 10, 10)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawRoundedRect(16, 24, 32, 6, 3, 3)
    painter.drawRoundedRect(16, 34, 20, 6, 3, 3)
    painter.end()
    return QIcon(pixmap)


def app_icon() -> QIcon:
    """Icone do app: o .ico/.png versionado, ou o desenho se nao houver arquivo."""
    for name in ("app.ico", "icon.png"):
        path = asset_path(name)
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return _drawn_icon()
