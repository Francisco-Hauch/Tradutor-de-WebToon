"""Imagens de diagnostico -- o unico jeito honesto de avaliar qualidade de OCR.

Numero desenhado na imagem casa com o indice impresso no console, entao da
para conferir linha a linha o que o modelo leu e de onde.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .types import Block, TextBox

_LINE_COLOR = (255, 40, 40)
_BLOCK_COLOR = (40, 140, 255)


def _label_font(size: int = 14) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def draw_boxes(
    image: Image.Image,
    boxes: list[TextBox],
    blocks: list[Block] | None = None,
) -> Image.Image:
    """Vermelho = linha detectada pelo OCR. Azul = balao apos o agrupamento."""
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    font = _label_font()

    for block in blocks or []:
        x, y, w, h = block.rect
        draw.rectangle([x, y, x + w, y + h], outline=_BLOCK_COLOR, width=3)

    for i, box in enumerate(boxes):
        draw.polygon(box.quad, outline=_LINE_COLOR)
        x, y, _, _ = box.rect
        tag = str(i)
        tw = draw.textlength(tag, font=font)
        draw.rectangle([x, y - 16, x + tw + 6, y], fill=_LINE_COLOR)
        draw.text((x + 3, y - 15), tag, fill=(255, 255, 255), font=font)

    return canvas
