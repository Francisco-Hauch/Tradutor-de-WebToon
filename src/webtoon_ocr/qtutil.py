"""Pequenos utilitarios de Qt usados pelo seletor e pelo overlay."""

from __future__ import annotations

from PIL import Image

from . import winenv

# O ajuste de DPI precisa valer antes de o Qt ser importado, nao so antes de
# o QApplication ser criado -- o Qt le as variaveis de ambiente no import.
winenv.setup()

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def ensure_app() -> QApplication:
    """Devolve o QApplication da sessao, criando um se ainda nao existir."""
    return QApplication.instance() or QApplication([])


def to_qimage(image: Image.Image) -> QImage:
    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    # `copy()` porque o QImage nao assume a posse do buffer: sem isso o
    # bytes() e coletado e a imagem passa a apontar para memoria liberada.
    return QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()
