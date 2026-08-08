"""Resolucao e cache de fontes para o render em PIL.

Carregar uma fonte e caro e o ajuste de corpo testa varios tamanhos por
balao, entao sem cache o mesmo arquivo seria aberto dezenas de vezes por
pagina.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import ImageFont

# Nome de familia -> arquivo, para as fontes que acompanham o Windows.
_FILES = {
    "segoe ui": "segoeui.ttf",
    "segoe ui semibold": "seguisb.ttf",
    "arial": "arial.ttf",
    "calibri": "calibri.ttf",
    "verdana": "verdana.ttf",
    "tahoma": "tahoma.ttf",
    "malgun gothic": "malgun.ttf",  # tem hangul, util para depurar o original
}

_FALLBACKS = ("segoeui.ttf", "arial.ttf", "tahoma.ttf")


@lru_cache(maxsize=256)
def load(family: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [_FILES.get(family.strip().lower(), f"{family.replace(' ', '').lower()}.ttf"), *_FALLBACKS]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def measurer(family: str):
    """Devolve a funcao `measure` que o `textfit` espera, para esta familia."""

    def measure(text: str, size: int) -> tuple[float, float]:
        font = load(family, size)
        ascent, descent = font.getmetrics()
        return (font.getlength(text), float(ascent + descent))

    return measure
