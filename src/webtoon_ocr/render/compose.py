"""Desenha a traducao sobre a imagem: caixa branca por cima, texto por cima dela.

Esta e a versao em PNG. O overlay na tela desenha exatamente os mesmos
`Block` com a mesma logica de ajuste de fonte -- por isso da para avaliar o
resultado final salvando arquivos, muito antes de existir qualquer janela.

A caixa branca e o jeito simples de "apagar" o coreano. Preserva zero do
desenho debaixo, mas e previsivel e nunca deixa residuo do texto original.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import RenderConfig
from ..types import Block
from . import fonts
from .textfit import fit

_BOX_FILL = (255, 255, 255)
_BOX_EDGE = (170, 170, 170)
_TEXT = (10, 10, 10)


def compose(image: Image.Image, blocks: list[Block], cfg: RenderConfig) -> Image.Image:
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    measure = fonts.measurer(cfg.font_family)

    for block in blocks:
        text = (block.translated or "").strip()
        if not text:
            continue

        x, y, w, h = block.rect
        pad = cfg.box_padding
        box = (x - pad, y - pad, x + w + pad, y + h + pad)
        draw.rounded_rectangle(box, radius=cfg.corner_radius, fill=_BOX_FILL, outline=_BOX_EDGE, width=1)

        # O texto e ajustado a area util, ja descontada a margem interna.
        inner_w = box[2] - box[0] - 2 * pad
        inner_h = box[3] - box[1] - 2 * pad
        size, lines = fit(
            text, inner_w, inner_h, measure,
            min_size=cfg.min_font_pt, max_size=cfg.max_font_pt,
        )

        font = fonts.load(cfg.font_family, size)
        line_h = measure("Ag", size)[1] * 1.15
        top = box[1] + pad + max(0, (inner_h - line_h * len(lines)) / 2)

        for i, line in enumerate(lines):
            lw = measure(line, size)[0]
            cx = box[0] + pad + (inner_w - lw) / 2
            draw.text((cx, top + i * line_h), line, font=font, fill=_TEXT)

    return canvas
