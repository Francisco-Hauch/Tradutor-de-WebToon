"""Contrato que todo motor de OCR precisa cumprir.

Manter isso como Protocol e o que permite trocar PaddleOCR por EasyOCR
mexendo so no `config.toml`, sem tocar no resto do pipeline.
"""

from __future__ import annotations

from typing import Protocol

from PIL import Image

from ..types import TextBox


class OcrEngine(Protocol):
    """Le uma imagem e devolve uma `TextBox` por linha de texto encontrada.

    As coordenadas devolvidas sao SEMPRE no espaco da imagem original recebida
    -- qualquer upscale interno ja vem desfeito.
    """

    def read(self, image: Image.Image) -> list[TextBox]: ...
